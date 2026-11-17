# slotwright

## Storage layout maps and upgrade diffs for Solidity contracts

Upgrading a proxy-backed contract is safe only when every existing state variable keeps its slot and byte offset. A single variable inserted in the middle silently relocates everything after it, and the next read returns another variable's bytes. **slotwright** reads Solidity sources offline, computes the storage layout with Solidity's packing rules, and diffs two versions of a contract into a `SAFE` or `BREAKING` verdict with a CI-gateable exit code.

- **Problem:** layout checks are done by hand or not at all, because they need a compiler and a deployed fork.
- **Solution:** a stdlib-only scanner that maps slots from source, then classifies appends, inserts, moves, retypes and storage-gap changes.
- **Audience:** Solidity developers and reviewers preparing upgradeable contracts (UUPS/Transparent proxy, diamonds) for an upgrade.

## Quick start

```shell
pip install -e .

# map a contract's storage
slotwright layout examples/VaultV1.sol

# compare two versions; exit 1 if existing storage moved
slotwright diff examples/VaultV1.sol examples/VaultV2_bad.sol --fail-on-breaking

# machine-readable output
slotwright diff old.sol new.sol --json
```

## What it reports

```text
Storage layout: VaultV1 (12 slots)

slot  offset  bytes  type                         name           declared in
----  ------  -----  ---------------------------  -------------  -----------
0     0       20     address                      owner          VaultV1:6
0     20      1      bool                         paused         VaultV1:7
1     0       12     uint96                       feeBps         VaultV1:8
2     0       32     uint256                      totalDeposits  VaultV1:9
3     0       32     mapping(address => uint256)  balances       VaultV1:10
4     0       256    uint256[8]                   __gap          VaultV1:11
```

```text
Upgrade diff: Vault
old: 12 slot(s)   new: 12 slot(s)

BREAKING inserted  pendingFees: new variable inserted at slot 1 offset 0 (uint128), reusing storage that held 'feeBps'; every later variable shifts
BREAKING moved     feeBps: moved from slot 1 offset 0 to slot 1 offset 16

Verdict: BREAKING
```

## Features

- **Solidity packing rules**: value types pack in declaration order; a value that would cross a 32-byte boundary starts the next slot; structs, fixed arrays, dynamic arrays and mappings start a new slot.
- **Structs, arrays and inheritance**: struct fields are laid out recursively, `uint32[4]` is recognised as one packed slot, and base-contract variables come first.
- **Constants excluded**: `constant`, `immutable` and `transient` variables are listed separately and occupy no persistent slot.
- **Upgrade diff**: classifies `appended`, `inserted`, `moved`, `type-changed`, `size-changed`, `removed`, `removed-tail`, `gap-consumed`, `gap-shrunk` and `gap-grown`.
- **Storage-gap awareness**: consuming a `__gap` array is safe only when the gap shrinks by exactly the number of slots filled.
- **Text and JSON**: readable table for review, JSON for tooling, `--fail-on-breaking` for CI.
- **No network, no compiler, no dependencies**: pure standard library.

## Architecture

```text
examples/*.sol ──► parser.py ──► Contract / VarDecl / StructDef
                                   │
                     layout.py ◄───┘ (packing + inheritance)
                        │
                     Layout (SlotEntry[])
                        │
                     diff.py ──► Change[] ──► render.py / JSON
                        │
                     cli.py ──► exit code (0 ok / 1 gate / 2 error)
```

- `parser.py` masks comments and string literals, walks contract bodies at brace depth one, and records declarations with line numbers. Function bodies are skipped.
- `layout.py` sizes type strings (`uintN`, `bytesN`, `address`, `bool`, `enum`, `struct`, arrays, `mapping`) and places them with a slot allocator.
- `diff.py` compares entries by name and byte span, including the `__gap` rules.
- `cli.py` exposes `layout`, `diff`, `contracts`, `explain` and `demo`.

See `docs/ARCHITECTURE.md` for details and `docs/USAGE.md` for the rule table.

## Requirements

- Python 3.12+
- No third-party runtime dependencies

## Installation

```shell
git clone https://github.com/Wsh7Ash/slotwright
cd slotwright
pip install -e ".[dev]"
```

## Usage

```shell
# which contracts are in this file?
slotwright contracts src/Vault.sol

# layout of a specific contract, or of a struct's fields
slotwright layout src/Vault.sol --contract Vault
slotwright layout src/Vault.sol --struct Position

# diff and gate a deployment pipeline
slotwright diff build/Vault.old.sol build/Vault.new.sol --fail-on-breaking

# rule explanations
slotwright explain packing
slotwright explain upgrades
slotwright explain gaps
```

Exit codes: `0` success, `1` gate failure (`--fail-on-breaking`), `2` parse/read error.

## Configuration

There is no config file. All input comes from arguments, which keeps the tool usable inside any CI job without state.

## Testing

```shell
PYTHONPATH=src python -m pytest tests/ -v
```

52 tests cover the scanner, packing rules, inheritance, the diff classifier and the CLI exit codes. `results/validation.log` holds the captured run.

## Project structure

```text
slotwright/
├─ src/slotwright/{parser,layout,diff,render,cli}.py
├─ tests/{test_parser,test_layout,test_diff,test_cli}.py
├─ examples/{VaultV1,VaultV2_good,VaultV2_bad}.sol
├─ docs/{ARCHITECTURE,USAGE,PROJECT_SPEC}.md
├─ results/{layout-v1,diff-good,diff-bad}.txt
├─ RESULTS.md
└─ .github/workflows/ci.yml
```

## Limitations

- Single file at a time: imports are not resolved. A base contract imported from another file is treated as contributing no storage; pass the file that declares the full hierarchy instead.
- Inheritance uses depth-first, left-to-right linearization with duplicates removed. Conflicting diamond orders (needing full C3) are not modelled.
- Initializers are ignored, so an explicit `assembly { sstore(...) }` or unstructured-storage hash cannot be seen.
- Imported contract/interface types and user-defined value types are assumed to be 20-byte addresses unless a struct or enum with the same name is declared in the scanned file.
- Enums are sized as one byte.
- No storage snapshot from a node is read; the layout is derived from source only.

## Roadmap

- Resolve relative imports to cover multi-file inheritance.
- Read `solc --storage-layout` JSON as a second input format and diff source-derived layouts against compiler output.
- Report explicit storage-slot collisions for unstructured storage namespaces.

## Security notes

slotwright performs static analysis of files you provide. It executes nothing, makes no network calls and never connects to a chain. Treat a `SAFE` verdict as one input to review, not a guarantee: the limitations above describe what it cannot see.

## License

MIT — see `LICENSE`.
