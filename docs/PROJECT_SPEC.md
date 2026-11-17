# Project spec — slotwright

## Name

slotwright

## Category

web3-security

## Target user

A Solidity developer or reviewer preparing an upgrade to a proxy-backed contract, who needs to prove that no existing storage moved.

## Problem

Storage layout correctness is the most common way an otherwise correct upgrade destroys state. The authoritative answer requires `solc --storage-layout` plus the exact source tree, and reviewers rarely run it before approving a proxy upgrade.

## Solution

An offline scanner that derives the layout from source with Solidity's documented packing rules, then diffs two versions and returns `SAFE` or `BREAKING` with the specific variable that moved and the storage it now overlaps.

## Core workflow

1. `slotwright layout Vault.sol` to see the current map.
2. Edit the contract.
3. `slotwright diff Vault.old.sol Vault.sol --fail-on-breaking` in CI.
4. Fix any `inserted`, `moved` or `gap-shrunk` finding.

## Must-have features

- contract and inheritance scanning without a compiler;
- Solidity packing rules for value types, structs, arrays, mappings;
- exclusion of constants, immutables and transient variables;
- diff with safe/breaking classification;
- storage-gap consumption rules;
- text and JSON output; CI exit code;
- offline, stdlib only.

## Nice-to-have features

- import resolution;
- `solc --storage-layout` JSON as an input;
- diamonds/unstructured storage namespaces.

## Stack

Python 3.12+, standard library only, pytest for tests.

## Test strategy

Unit tests for the scanner (comments, strings, attributes, inheritance), for the allocator (packing boundaries, blocks, nested structs, arrays) and for every diff kind. CLI tests cover output formats and exit codes. All fixtures are inline strings so tests run without the filesystem except `tmp_path` for CLI inputs.

## Demo/result strategy

Three example contracts: the baseline, a safe upgrade that consumes the storage gap, and an unsafe upgrade that inserts `uint128 pendingFees` and shifts `feeBps`. The observed outputs are stored in `results/` and quoted in the README.

## Safety considerations

Read-only static analysis. No network, no execution of Solidity, no private keys, no chain RPC. Example sources contain no secrets.

## Definition of done

- tests green;
- `layout` and `diff` produce the documented output on the examples;
- `--fail-on-breaking` returns 1 on the unsafe example;
- README, docs and RESULTS written from observed runs;
- git repository committed and published.
