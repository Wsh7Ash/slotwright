# Security policy

## Scope

slotwright is a static analyser for Solidity source files. It reads text, computes storage layouts and prints a report. It does not compile, deploy, sign transactions or connect to a node.

## Authorized use

Only analyse contracts you are allowed to inspect. A layout map can reveal implementation details of a deployed protocol; treat outputs from unreleased contracts as confidential until the deployment is public.

## Reporting a vulnerability

Open a private GitHub security advisory or email the maintainer listed on the GitHub profile. Include the source file that reproduces the miscomputed layout: an incorrect `SAFE` verdict is a security-relevant bug for this project.

## What a SAFE verdict does and does not mean

`SAFE` means the two files you passed have compatible layouts under the rules in `docs/USAGE.md`. It is not an audit. The analyser cannot see:

- storage written through `assembly`/`sstore` or unstructured-storage hashing;
- variables in imported base contracts whose files could not be resolved (listed under `unresolved_imports`);
- proxy admin, implementation or beacon slots;
- compiler-level packing changes across Solidity versions;
- runtime behaviour, access control or upgrade authorization.

Treat the verdict as one input to review and verify with `solc --storage-layout` and a fork-based upgrade test before touching a live proxy.
