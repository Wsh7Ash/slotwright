# Changelog

## 0.2.0 — 2026-11-17
- Relative import resolution: `import "./Base.sol"`, `import "Base.sol"` and `from "..."` forms are followed and merged (contracts, in-contract and file-level structs/enums)
- Unresolved imports (missing files, URLs, package scopes) are reported in `--json` output and on stderr instead of aborting
- Import cycles are handled without infinite recursion
- 55 tests (3 new)

## 0.1.0 — 2026-11-17
- Initial release
- Solidity scanner: contracts, inheritance, state variables, structs, enums
- Packing-aware storage allocator (value types, structs, fixed/dynamic arrays, mappings)
- Exclusion of constant, immutable and transient variables
- Upgrade diff with appended/inserted/moved/type-changed/removed classification
- Storage-gap consumption rules (`gap-consumed`, `gap-shrunk`, `gap-grown`)
- Text and JSON output, `--fail-on-breaking` CI gate
- `layout`, `diff`, `contracts`, `explain`, `demo` commands
