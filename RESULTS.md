# Results — slotwright

## Environment
- OS: Windows (MSYS2/Git Bash)
- Runtime: Python 3.14.3
- Dependency manager: pip (stdlib-only runtime)
- Test runner: pytest 9.1.1

## Validation performed
- install: PASS (`PYTHONPATH=src python -c "import slotwright, slotwright.cli"` printed `import ok 0.1.0`)
- build: PASS (no build step; package imports and CLI runs)
- unit tests: PASS (55 passed)
- integration tests: PASS (CLI `layout`, `diff`, `contracts`, `demo` run on the example sources)
- lint: N/A (no linter configured for this stdlib-only project)
- type check: N/A (no type checker in scope for this run)
- demo run: PASS (layout of VaultV1, safe gap-consuming upgrade, breaking insert)

## Commands executed
```shell
cd projects/2026-11-17/slotwright
PYTHONPATH=src python -m pytest tests/ -v
PYTHONPATH=src python -m slotwright layout examples/VaultV1.sol
PYTHONPATH=src python -m slotwright diff examples/VaultV1.sol examples/VaultV2_good.sol
PYTHONPATH=src python -m slotwright diff examples/VaultV1.sol examples/VaultV2_bad.sol --fail-on-breaking
```

## Observed result

Layout (excerpt, full output in `results/layout-v1.txt`):

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

Safe upgrade — a new variable consumes the first gap slot and the gap shrinks from 8 to 7. Exit code 0 from `--fail-on-breaking`:

```text
Upgrade diff: Vault
old: 12 slot(s)   new: 12 slot(s)

SAFE     gap-consumed  lastSynced: new variable placed at slot 4 offset 0 (uint256) inside the reserved storage of '__gap'

Verdict: SAFE
```

Unsafe upgrade — `uint128 pendingFees` inserted after `paused`. Exit code 1 with `--fail-on-breaking`:

```text
Upgrade diff: Vault
old: 12 slot(s)   new: 12 slot(s)

BREAKING inserted  pendingFees: new variable inserted at slot 1 offset 0 (uint128), reusing storage that held 'feeBps'; every later variable shifts
BREAKING moved     feeBps: moved from slot 1 offset 0 to slot 1 offset 16

Verdict: BREAKING
```

Note the subtlety the diff catches: `totalDeposits` and `balances` happen not to move in this example because of packing, but `feeBps` does (offset 0 → 16), which is still a breaking change.

## Generated artifacts
- `results/layout-v1.txt`
- `results/diff-good.txt`
- `results/diff-bad.txt`
- `results/validation.log` (captured pytest run)

## Known limitations
- One file at a time; relative imports are not resolved.
- Depth-first linearization with de-duplication rather than full C3 for conflicting diamond orders.
- User-defined value types and imported contract types are assumed to be 20-byte addresses.
- Initializers and assembly `sstore` are not analysed.
- Enums are modelled as one byte.
