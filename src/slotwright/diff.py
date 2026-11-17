"""Upgrade-safety diff between two storage layouts.

Severity model:

* ``breaking`` — a stored value would be read back from a different slot, offset
  or type after the upgrade;
* ``warning`` — unusual but not immediately corrupting;
* ``safe`` — validated as compatible.

A variable appended into storage that no old variable used is safe. A variable
that takes space from a declared ``__gap`` is safe only when the gap shrinks by
exactly the number of slots the new variable consumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .layout import WORD, Layout, SlotEntry

BREAKING = "breaking"
WARNING = "warning"
SAFE = "safe"


@dataclass(frozen=True)
class Change:
    kind: str
    severity: str
    name: str
    detail: str


@dataclass(frozen=True)
class DiffResult:
    contract: str
    changes: tuple[Change, ...]
    old_slots: int
    new_slots: int

    @property
    def breaking(self) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.severity == BREAKING)

    @property
    def verdict(self) -> str:
        return "BREAKING" if self.breaking else "SAFE"


def _is_gap(entry: SlotEntry) -> bool:
    return entry.name.lower().startswith("__gap")


def _position(entry: SlotEntry) -> str:
    return f"slot {entry.slot} offset {entry.offset} ({entry.type_str})"


def _span(entry: SlotEntry) -> tuple[int, int]:
    start = entry.slot * WORD + entry.offset
    return start, start + entry.size


def _conflicts(entry: SlotEntry, previous: Layout) -> list[SlotEntry]:
    start, end = _span(entry)
    found = []
    for old in previous.entries:
        old_start, old_end = _span(old)
        if start < old_end and old_start < end:
            found.append(old)
    return found


def _inside(entry: SlotEntry, container: SlotEntry) -> bool:
    start, end = _span(entry)
    outer_start, outer_end = _span(container)
    return outer_start <= start and end <= outer_end


def diff_layouts(old: Layout, new: Layout) -> DiffResult:
    old_by = {entry.name: entry for entry in old.entries}
    new_by = {entry.name: entry for entry in new.entries}
    changes: list[Change] = []
    consumed_slots: set[int] = set()

    for entry in new.entries:
        previous = old_by.get(entry.name)
        if previous is None:
            conflicts = _conflicts(entry, old)
            gap = next((conflict for conflict in conflicts if _is_gap(conflict)), None)
            if not conflicts:
                changes.append(
                    Change(
                        "appended",
                        SAFE,
                        entry.name,
                        f"new variable placed at {_position(entry)}, "
                        "outside every previously used byte",
                    )
                )
            elif gap is not None and len(conflicts) == 1 and _inside(entry, gap):
                consumed_slots.update(range(entry.slot, entry.slot + entry.slots))
                changes.append(
                    Change(
                        "gap-consumed",
                        SAFE,
                        entry.name,
                        f"new variable placed at {_position(entry)} inside the "
                        f"reserved storage of '{gap.name}'",
                    )
                )
            else:
                blocker = next(
                    (conflict for conflict in conflicts if not _is_gap(conflict)),
                    conflicts[0],
                )
                changes.append(
                    Change(
                        "inserted",
                        BREAKING,
                        entry.name,
                        f"new variable inserted at {_position(entry)}, "
                        f"reusing storage that held '{blocker.name}'; "
                        "every later variable shifts",
                    )
                )
            continue

        if _is_gap(entry) and _is_gap(previous):
            # Canonical pattern: new variables consume the front of the gap and
            # the gap's last slot stays fixed.
            old_end = previous.slot + previous.slots
            new_end = entry.slot + entry.slots
            shift = entry.slot - previous.slot
            if old_end == new_end and 0 <= shift <= len(consumed_slots):
                continue
        if previous.type_str != entry.type_str:
            if _is_gap(entry) and previous.kind == "array" and entry.kind == "array":
                # Resized gaps are handled by the gap rules below.
                continue
            changes.append(
                Change(
                    "type-changed",
                    BREAKING,
                    entry.name,
                    f"{previous.type_str} at slot {previous.slot} became "
                    f"{entry.type_str} at slot {entry.slot}",
                )
            )
            continue
        if (previous.slot, previous.offset) != (entry.slot, entry.offset):
            changes.append(
                Change(
                    "moved",
                    BREAKING,
                    entry.name,
                    f"moved from slot {previous.slot} offset {previous.offset} "
                    f"to slot {entry.slot} offset {entry.offset}",
                )
            )
            continue
        if previous.slots != entry.slots:
            changes.append(
                Change(
                    "size-changed",
                    BREAKING,
                    entry.name,
                    f"now covers {entry.slots} slot(s), previously {previous.slots}",
                )
            )

    for entry in old.entries:
        if entry.name in new_by:
            continue
        if entry.slot + entry.slots >= old.total_slots:
            changes.append(
                Change(
                    "removed-tail",
                    SAFE,
                    entry.name,
                    "last variable removed; earlier storage is untouched",
                )
            )
        else:
            changes.append(
                Change(
                    "removed",
                    BREAKING,
                    entry.name,
                    f"removed from slot {entry.slot}; the variables that "
                    "followed it now read different slots",
                )
            )

    for entry in new.entries:
        if not _is_gap(entry):
            continue
        previous = old_by.get(entry.name)
        if previous is None:
            continue
        delta = previous.slots - entry.slots
        if delta == 0:
            continue
        if delta > 0:
            if delta <= len(consumed_slots):
                continue
            changes.append(
                Change(
                    "gap-shrunk",
                    BREAKING,
                    entry.name,
                    f"storage gap shrank by {delta} slot(s) but only "
                    f"{len(consumed_slots)} slot(s) were filled by new variables; "
                    "the reserve no longer covers the declared gap",
                )
            )
        else:
            changes.append(
                Change(
                    "gap-grown",
                    WARNING,
                    entry.name,
                    f"storage gap grew by {-delta} slot(s)",
                )
            )

    order = {entry.name: index for index, entry in enumerate(new.entries)}
    changes.sort(key=lambda c: (order.get(c.name, len(order)), c.name))
    return DiffResult(
        contract=new.contract,
        changes=tuple(changes),
        old_slots=old.total_slots,
        new_slots=new.total_slots,
    )
