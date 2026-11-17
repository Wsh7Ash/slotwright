"""Text rendering for layouts and upgrade diffs."""

from __future__ import annotations

from .diff import DiffResult
from .layout import Layout

HEADERS = ("slot", "offset", "bytes", "type", "name", "declared in")


def render_layout(layout: Layout) -> str:
    rows: list[list[str]] = []
    for entry in layout.entries:
        rows.append(
            [
                str(entry.slot),
                str(entry.offset),
                str(entry.size),
                entry.type_str,
                entry.name,
                f"{entry.contract}:{entry.line}",
            ]
        )
    widths = [len(header) for header in HEADERS]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    out = [
        f"Storage layout: {layout.contract} ({layout.total_slots} slot"
        f"{'' if layout.total_slots == 1 else 's'})",
        "",
        line(HEADERS),
        line(tuple("-" * width for width in widths)),
    ]
    if not rows:
        out.append("(no persistent state variables)")
    for row in rows:
        out.append(line(tuple(row)))
    if layout.skipped:
        names = ", ".join(sorted(f"{decl.name}" for decl in layout.skipped))
        out.extend(["", f"Not in storage (constant/immutable/transient): {names}"])
    return "\n".join(out)


def render_diff(result: DiffResult) -> str:
    out = [
        f"Upgrade diff: {result.contract}",
        f"old: {result.old_slots} slot(s)   new: {result.new_slots} slot(s)",
        "",
    ]
    if not result.changes:
        out.append("No storage changes.")
        return "\n".join(out)
    width = max(len(change.kind) for change in result.changes)
    for change in result.changes:
        out.append(
            f"{change.severity.upper():<8} {change.kind:<{width}}  "
            f"{change.name}: {change.detail}"
        )
    out.extend(["", f"Verdict: {result.verdict}"])
    return "\n".join(out)
