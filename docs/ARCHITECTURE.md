# Architecture — slotwright

## Overview

slotwright is a four-stage pipeline with no runtime dependencies:

```text
source text
   │
   ├─ parser.py   mask comments/strings, walk contract bodies, collect declarations
   │
   ├─ layout.py   size types, linearize inheritance, allocate slots
   │
   ├─ diff.py     compare two Layout objects into Change records
   │
   └─ render.py / cli.py   text or JSON, exit code
```

## Scanner

`mask_source()` replaces comments and the contents of string literals with spaces while preserving character offsets and newlines. All later scanning runs over the masked text, so a `{`, `;` or `//` inside a string cannot break the declaration walker.

Contract headers are found with a regular expression, and the body is delimited by brace matching. Inside a body, the walker tracks a single depth level:

- `{` at body level starts a nested block. `struct` and `enum` headers are recorded; every other block (functions, modifiers, constructors, `receive`) is skipped to its closing brace.
- `;` at body level ends a declaration, which is split into type and name after removing `public/private/internal/external`, `constant/immutable/transient`, `virtual` and `override(...)`.
- Initializers are cut at the first `=` that is not part of `=>`, `==`, `>=`, `<=` or a compound assignment.

Line numbers come from a precomputed line-start index and point at the first non-blank character of the declaration.

## Type sizing

`Resolver` maps a type string to `TypeInfo(kind, size, slots)`:

| Type | kind | size | slots |
|---|---|---|---|
| `uint8`..`uint256`, `int8`..`int256` | value | bits/8 | 1 |
| `bool` | value | 1 | 1 |
| `address`, `address payable` | value | 20 | 1 |
| `bytes1`..`bytes32` | value | N | 1 |
| `bytes`, `string`, `T[]` | dynamic | 32 | 1 |
| `mapping(K => V)` | mapping | 32 | 1 |
| `enum E` | value | 1 | 1 |
| `struct S` | struct | slots·32 | fields packed |
| `T[N]` | array | N·sizeof(T) or N·slots(T)·32 | packed or multiplied |

Struct sizes are memoized and recursion is rejected.

## Slot allocation

`_Allocator` keeps a current slot and byte offset:

- value: if `offset + size > 32`, advance one slot and reset the offset; record `(slot, offset)` and advance the offset;
- everything else: if the offset is non-zero, advance one slot; record `(slot, 0)` and advance by the value's slot count.

`Layout.total_slots` is the allocator's end position, so a layout whose last slot is half used still counts one slot.

## Inheritance

`linearize()` walks base contracts depth-first in declaration order, appending each contract after its bases and de-duplicating names. For acyclic trees this matches the base-ward-to-derived order Solidity produces. Conflicting diamond orders are out of scope.

## Diff

`diff_layouts(old, new)`:

1. New variables are classified by byte span. No overlap with old storage → `appended`. Fully inside an old `__gap` → `gap-consumed` (and the covered slots are remembered). Otherwise → `inserted`.
2. Existing variables keep their name but may be `type-changed`, `moved` or `size-changed`.
3. Removed variables are `removed-tail` when they end at the old layout's last slot, otherwise `removed`.
4. Gaps are compared last: the canonical "consume the front, keep the end fixed" pattern is accepted; a shrink larger than the consumed slot count is `gap-shrunk`; growth is a `gap-grown` warning.

Any `breaking` change makes the verdict `BREAKING`.

## CLI

`cli.py` uses argparse subcommands. Errors (`ParseError`) print to stderr and return `2`; the only non-zero success-path code is `1` from `--fail-on-breaking`.

## Design decisions

- **No compiler dependency** keeps the tool usable in review environments where `solc` is not installed.
- **Masking rather than tokenizing** is enough for declarations and avoids a full Solidity grammar.
- **Byte-span overlap** for new variables is what makes "fits in the free half of the last slot" safe while "reuses a live variable's bytes" is not.
- **Gap rules as data, not heuristics on names only**: a variable called `__gap` that is not an array is still treated as reserved storage, which is conservative.
