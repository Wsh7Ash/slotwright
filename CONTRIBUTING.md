# Contributing

## Setup

```shell
pip install -e ".[dev]"
```

## Running tests

```shell
PYTHONPATH=src python -m pytest tests/ -v
```

## Adding a type

1. Add the sizing branch in `Resolver.resolve()` in `src/slotwright/layout.py`.
2. If the type is packed rather than block-placed, return `kind="value"` with a byte size.
3. Add a case to `tests/test_layout.py` that checks slot, offset and size together.
4. Update the type table in `docs/USAGE.md`.

## Adding a diff finding

1. Emit a `Change(kind, severity, name, detail)` in `src/slotwright/diff.py`.
2. Add the kind to the table in `docs/USAGE.md` and to `render.py` only if it needs special formatting.
3. Add a test in `tests/test_diff.py` asserting both the finding and the verdict.

## Design rules

- Keep the runtime stdlib-only; the tool must run without installing anything.
- Never guess silently: an unsupported construct should either be documented as a limitation or raise `ParseError`.
- A `safe` verdict is a claim; every safe path needs a test with a counterexample next to it.
