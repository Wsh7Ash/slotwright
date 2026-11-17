"""Command-line interface for slotwright."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .diff import diff_layouts
from .layout import build_layout, layout_struct
from .parser import ParseError, parse_file, parse_source
from .render import render_diff, render_layout

DEMO_V1 = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Vault {
    struct Position {
        uint128 size;
        uint64 openedAt;
        bool open;
    }

    address public owner;
    bool public paused;
    uint256 public totalDeposits;
    mapping(address => uint256) public balances;
    Position public position;
    uint256[4] public checkpoints;
    uint256[8] private __gap;
}
"""

DEMO_V2 = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract Vault {
    struct Position {
        uint128 size;
        uint64 openedAt;
        bool open;
    }

    address public owner;
    bool public paused;
    uint96 public feeBps;          // inserted: shifts totalDeposits and everything after
    uint256 public totalDeposits;
    mapping(address => uint256) public balances;
    Position public position;
    uint256[4] public checkpoints;
    uint256[8] private __gap;
    uint256 public lastSynced;     // appended: safe
}
"""


def _layout_payload(layout, source=None) -> dict:
    payload = {
        "contract": layout.contract,
        "total_slots": layout.total_slots,
        "entries": [
            {
                "slot": entry.slot,
                "offset": entry.offset,
                "bytes": entry.size,
                "slots": entry.slots,
                "kind": entry.kind,
                "type": entry.type_str,
                "name": entry.name,
                "contract": entry.contract,
                "line": entry.line,
            }
            for entry in layout.entries
        ],
        "not_in_storage": [decl.name for decl in layout.skipped],
    }
    if source is not None:
        payload["unresolved_imports"] = list(getattr(source, "unresolved_imports", []))
    return payload


def _diff_payload(result, old_source=None, new_source=None) -> dict:
    payload = {
        "contract": result.contract,
        "verdict": result.verdict,
        "old_slots": result.old_slots,
        "new_slots": result.new_slots,
        "changes": [
            {
                "kind": change.kind,
                "severity": change.severity,
                "name": change.name,
                "detail": change.detail,
            }
            for change in result.changes
        ],
    }
    unresolved = []
    for src in (old_source, new_source):
        if src is None:
            continue
        for item in getattr(src, "unresolved_imports", []):
            if item not in unresolved:
                unresolved.append(item)
    if unresolved:
        payload["unresolved_imports"] = unresolved
    return payload


def _emit(payload: dict, text: str, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=False))
    else:
        print(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slotwright",
        description=(
            "Map Solidity storage slots and diff two versions of a contract "
            "before an upgrade can silently corrupt state."
        ),
    )
    parser.add_argument("--version", action="version", version=f"slotwright {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    layout = sub.add_parser("layout", help="print the storage layout of a contract")
    layout.add_argument("file", help="Solidity source file")
    layout.add_argument("--contract", help="contract name (default: last in file)")
    layout.add_argument("--struct", help="print a struct's internal field layout")
    layout.add_argument("--json", action="store_true")

    diff = sub.add_parser("diff", help="compare the layouts of two versions")
    diff.add_argument("old", help="old Solidity source file")
    diff.add_argument("new", help="new Solidity source file")
    diff.add_argument("--contract", help="contract name (default: last in old file)")
    diff.add_argument("--json", action="store_true")
    diff.add_argument(
        "--fail-on-breaking",
        action="store_true",
        help="exit 1 when the new layout moves or changes existing storage",
    )

    contracts = sub.add_parser("contracts", help="list contracts found in a file")
    contracts.add_argument("file")
    contracts.add_argument("--json", action="store_true")

    demo = sub.add_parser("demo", help="run the built-in vault example")
    demo.add_argument("--json", action="store_true")

    explain = sub.add_parser("explain", help="explain the packing rules")
    explain.add_argument("topic", choices=["packing", "upgrades", "gaps"])
    return parser


EXPLANATIONS = {
    "packing": (
        "Value types smaller than 32 bytes share a slot in declaration order. "
        "bool, uint8 and address (20 bytes) fit together in one slot; a value "
        "that would cross the 32-byte boundary starts the next slot. Structs, "
        "fixed arrays, dynamic arrays and mappings always start a new slot."
    ),
    "upgrades": (
        "An upgrade is safe only when every pre-existing variable keeps its slot "
        "and offset. Appending new variables after the last slot is safe. "
        "Inserting, removing (except at the tail), reordering or retyping a "
        "variable in the middle relocates everything after it, so already "
        "written state is read back as a different value."
    ),
    "gaps": (
        "Inheritable contracts reserve space with a fixed array such as "
        "`uint256[N] private __gap`. A child contract can add state only by "
        "consuming that reserve, and the parent must shrink the gap by exactly "
        "the slots the child added. Shrinking it more, or growing the child "
        "beyond the reserve, breaks the layout."
    ),
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "explain":
        print(EXPLANATIONS[args.topic])
        return 0

    try:
        if args.command == "demo":
            old = parse_source(DEMO_V1, "<demo-v1>")
            new = parse_source(DEMO_V2, "<demo-v2>")
            old_layout = build_layout(old, "Vault")
            new_layout = build_layout(new, "Vault")
            result = diff_layouts(old_layout, new_layout)
            if args.json:
                print(
                    json.dumps(
                        {
                            "old": _layout_payload(old_layout),
                            "new": _layout_payload(new_layout),
                            "diff": _diff_payload(result),
                        },
                        indent=2,
                    )
                )
            else:
                print(render_layout(old_layout))
                print()
                print(render_diff(result))
            return 1 if result.breaking else 0

        if args.command == "contracts":
            source = parse_file(args.file)
            payload = [
                {
                    "name": name,
                    "kind": source.contracts[name].kind,
                    "bases": list(source.contracts[name].bases),
                    "line": source.contracts[name].line,
                }
                for name in source.order
            ]
            if args.json:
                out = {"contracts": payload}
                if source.imports:
                    out["imports"] = list(source.imports)
                if source.unresolved_imports:
                    out["unresolved_imports"] = list(source.unresolved_imports)
                print(json.dumps(out, indent=2))
            else:
                for item in payload:
                    bases = f" is {', '.join(item['bases'])}" if item["bases"] else ""
                    print(f"{item['name']} ({item['kind']}){bases}  line {item['line']}")
                if source.unresolved_imports:
                    print(
                        "unresolved imports: " + ", ".join(source.unresolved_imports),
                        file=sys.stderr,
                    )
            return 0

        if args.command == "layout":
            source = parse_file(args.file)
            contract = source.require(args.contract)
            if args.struct:
                layout = layout_struct(source, contract.name, args.struct)
            else:
                layout = build_layout(source, contract.name)
            _emit(_layout_payload(layout, source), render_layout(layout), args.json)
            return 0

        if args.command == "diff":
            old_source = parse_file(args.old)
            new_source = parse_file(args.new)
            name = old_source.require(args.contract).name
            old_layout = build_layout(old_source, name)
            new_layout = build_layout(new_source, name)
            result = diff_layouts(old_layout, new_layout)
            _emit(
                _diff_payload(result, old_source, new_source),
                render_diff(result),
                args.json,
            )
            return 1 if args.fail_on_breaking and result.breaking else 0

    except ParseError as exc:
        print(f"slotwright: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
