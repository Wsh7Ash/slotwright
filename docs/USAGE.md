# Usage — slotwright

## Commands

| Command | Purpose |
|---|---|
| `slotwright layout FILE [--contract NAME] [--struct NAME] [--json]` | print the slot map |
| `slotwright diff OLD NEW [--contract NAME] [--fail-on-breaking] [--json]` | classify an upgrade |
| `slotwright contracts FILE [--json]` | list contracts, kinds, bases and lines |
| `slotwright explain {packing,upgrades,gaps}` | print one rule explanation |
| `slotwright demo [--json]` | run the built-in vault example |

When `--contract` is omitted, `layout` and `contracts` use the last contract in the file. `diff` takes the contract name from the old file and requires the new file to declare a contract with the same name.

## Reading a layout

```text
slot  offset  bytes  type         name   declared in
0     0       20     address      owner  Vault:6
0     20      1      bool         paused Vault:7
1     0       12     uint96       feeBps Vault:8
```

- `slot` — zero-based storage slot.
- `offset` — byte offset inside the slot.
- `bytes` — bytes covered by the variable; for structs and arrays this is the whole block.
- `declared in` — contract and line, useful when a base contract contributes state.

## Diff kinds

| Kind | Severity | Meaning |
|---|---|---|
| `appended` | safe | new variable uses bytes no old variable used |
| `gap-consumed` | safe | new variable uses reserved `__gap` space and the gap shrank to match |
| `inserted` | breaking | new variable reuses storage that held another variable |
| `moved` | breaking | an existing variable changed slot or offset |
| `type-changed` | breaking | same name, different declared type |
| `size-changed` | breaking | same type, different slot footprint |
| `removed` | breaking | variable removed from the middle |
| `removed-tail` | safe | the last variable was removed |
| `gap-shrunk` | breaking | gap shrank by more slots than new variables consumed |
| `gap-grown` | warning | gap was enlarged |

## CI integration

```yaml
- name: Storage layout gate
  run: |
    pip install -e .
    slotwright diff contracts/Vault.old.sol contracts/Vault.sol --fail-on-breaking
```

Commit the previous version of the contract alongside the new one (or generate it from the release tag) so the diff has both sides.

## What the diff does not know

- Proxy admin slots and implementation slots written outside the source.
- Diamond storage structs selected via a hash (`keccak256("diamond.storage")`), unless the struct itself is declared and passed explicitly with `layout --struct`.
- Imported base contracts (the file must declare the full hierarchy).
- Values written through `assembly`.

## Type support

Supported: `bool`, `address`, `address payable`, `bytesN`, `uintN`/`intN`, `bytes`, `string`, `mapping(K => V)`, fixed and dynamic arrays, `struct`, `enum`, function types, and identifiers (assumed to be contract/interface addresses).

Unsupported: user-defined value types with a non-address representation, `mapping` keys that affect layout (they do not), and recursive structs (rejected with an error).
