"""Storage layout computation for a scanned Solidity file.

Implements the packing rules described in the Solidity documentation:

* value types smaller than 32 bytes are packed into the current slot;
* a value that would cross a slot boundary starts the next slot;
* structs, fixed arrays, dynamic arrays and mappings start a new slot;
* struct fields and array elements are packed with the same rules;
* constants, immutables and transient variables occupy no persistent slot.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .parser import Contract, ParseError, Source, StructDef, VarDecl

WORD = 32
DYNAMIC_TYPES = {"string", "bytes"}
FIXED_ARRAY_RE = re.compile(r"^(.*)\[(\d+)\]$")
DYNAMIC_ARRAY_RE = re.compile(r"^(.*)\[\]$")
BYTES_N_RE = re.compile(r"^bytes(\d+)$")
INT_RE = re.compile(r"^(u?int)(\d*)$")
FUNCTION_RE = re.compile(r"^function\b")


@dataclass(frozen=True)
class TypeInfo:
    kind: str  # value | struct | mapping | dynamic | array
    size: int  # bytes for value types, total bytes for packed arrays
    slots: int  # slots covered by the whole value
    label: str


@dataclass(frozen=True)
class SlotEntry:
    slot: int
    offset: int
    size: int
    slots: int
    type_str: str
    name: str
    contract: str
    line: int
    kind: str

    @property
    def end_slot(self) -> int:
        return self.slot + self.slots


@dataclass(frozen=True)
class Layout:
    contract: str
    entries: tuple[SlotEntry, ...]
    total_slots: int
    skipped: tuple[VarDecl, ...]

    def by_name(self) -> dict[str, SlotEntry]:
        return {entry.name: entry for entry in self.entries}

    def find(self, name: str) -> SlotEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


class Resolver:
    """Sizes Solidity type strings, resolving structs and enums by name."""

    def __init__(self, structs: dict[str, StructDef], enums: set[str]):
        self.structs = structs
        self.enums = enums
        self._memo: dict[str, int] = {}
        self._stack: set[str] = set()

    def resolve(self, type_str: str) -> TypeInfo:
        type_str = " ".join(type_str.split())
        key = type_str

        match = DYNAMIC_ARRAY_RE.match(type_str)
        if match:
            return TypeInfo("dynamic", WORD, 1, type_str)

        match = FIXED_ARRAY_RE.match(type_str)
        if match:
            inner = self.resolve(match.group(1))
            count = int(match.group(2))
            if count <= 0:
                raise ParseError(f"array of length {count} is not valid: {type_str}")
            if inner.kind == "value":
                total = inner.size * count
                return TypeInfo(
                    "array", total, math.ceil(total / WORD), type_str
                )
            if inner.kind == "array" and inner.size:
                total = inner.size * count
                return TypeInfo("array", total, math.ceil(total / WORD), type_str)
            return TypeInfo("array", inner.slots * count * WORD, inner.slots * count, type_str)

        if type_str.startswith("mapping"):
            return TypeInfo("mapping", WORD, 1, type_str)

        if type_str in DYNAMIC_TYPES:
            return TypeInfo("dynamic", WORD, 1, type_str)

        if type_str in self.structs:
            slots = self.struct_slots(type_str)
            return TypeInfo("struct", slots * WORD, slots, type_str)

        if type_str in self.enums:
            # Solidity stores enums in the smallest integer type that fits, which
            # is one byte for the up-to-256-member enums seen in practice.
            return TypeInfo("value", 1, 1, type_str)

        match = BYTES_N_RE.match(type_str)
        if match:
            size = int(match.group(1))
            if not 1 <= size <= 32:
                raise ParseError(f"invalid bytes size in {type_str}")
            return TypeInfo("value", size, 1, type_str)

        match = INT_RE.match(type_str)
        if match:
            bits = int(match.group(2)) if match.group(2) else 256
            if bits % 8 or not 8 <= bits <= 256:
                raise ParseError(f"invalid integer width in {type_str}")
            return TypeInfo("value", bits // 8, 1, type_str)

        if type_str == "bool":
            return TypeInfo("value", 1, 1, type_str)
        if type_str == "address" or type_str == "address payable":
            return TypeInfo("value", 20, 1, type_str)
        if FUNCTION_RE.match(type_str):
            # address (20 bytes) + function selector (4 bytes)
            return TypeInfo("value", 24, 1, type_str)
        if type_str in {"byte"}:
            return TypeInfo("value", 1, 1, type_str)

        if re.match(r"^[A-Za-z_$][\w$.]*$", type_str):
            # Imported contract, interface or user-defined value type. There is
            # no import graph here, so assume the common case: a 20-byte address.
            return TypeInfo("value", 20, 1, type_str)

        raise ParseError(f"unsupported type '{key}'")

    def struct_slots(self, name: str) -> int:
        if name in self._memo:
            return self._memo[name]
        if name in self._stack:
            raise ParseError(f"recursive struct '{name}' cannot be laid out")
        struct = self.structs[name]
        self._stack.add(name)
        try:
            allocator = _Allocator()
            for field_decl in struct.fields:
                info = self.resolve(field_decl.type_str)
                allocator.place(info)
            slots = allocator.end_slot
        finally:
            self._stack.discard(name)
        if slots == 0:
            slots = 0  # an empty struct is not legal Solidity
        self._memo[name] = slots
        return slots


class _Allocator:
    """Places values into slots following the packing rules."""

    def __init__(self) -> None:
        self.slot = 0
        self.offset = 0

    @property
    def end_slot(self) -> int:
        return self.slot + (1 if self.offset else 0)

    def place(self, info: TypeInfo) -> tuple[int, int]:
        if info.kind == "value" and info.size <= WORD:
            if self.offset + info.size > WORD:
                self.slot += 1
                self.offset = 0
            position = (self.slot, self.offset)
            self.offset += info.size
            return position
        if self.offset:
            self.slot += 1
            self.offset = 0
        position = (self.slot, 0)
        self.slot += max(info.slots, 1)
        return position


def _collect_types(source: Source, order: list[str]) -> tuple[dict[str, StructDef], set[str]]:
    structs: dict[str, StructDef] = {}
    enums: set[str] = set()
    for name in order:
        contract = source.contracts[name]
        for struct in contract.structs:
            structs.setdefault(struct.name, struct)
        enums.update(contract.enums)
    return structs, enums


def linearize(source: Source, contract_name: str) -> list[str]:
    """Base-ward-to-derived order, matching Solidity's C3 result for acyclic trees.

    Full C3 linearization with conflicting diamond orders is not implemented; the
    documented behaviour is depth-first, left-to-right, duplicate names once.
    """

    if contract_name not in source.contracts:
        raise ParseError(f"unknown contract '{contract_name}'")

    order: list[str] = []
    seen: set[str] = set()

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in stack:
            raise ParseError("inheritance cycle: " + " -> ".join(stack + (name,)))
        contract = source.contracts.get(name)
        if contract is None:
            # A base declared in an imported file: no variables are available.
            return
        for base in contract.bases:
            visit(base, stack + (name,))
        if name not in seen:
            seen.add(name)
            order.append(name)

    visit(contract_name, ())
    return order


def build_layout(source: Source, contract_name: str) -> Layout:
    order = linearize(source, contract_name)
    structs, enums = _collect_types(source, order)
    resolver = Resolver(structs, enums)
    allocator = _Allocator()
    entries: list[SlotEntry] = []
    skipped: list[VarDecl] = []

    for name in order:
        contract: Contract = source.contracts[name]
        for decl in contract.vars:
            if not decl.occupies_storage:
                skipped.append(decl)
                continue
            info = resolver.resolve(decl.type_str)
            slot, offset = allocator.place(info)
            entries.append(
                SlotEntry(
                    slot=slot,
                    offset=offset,
                    size=info.size,
                    slots=info.slots if info.kind != "value" else 1,
                    type_str=decl.type_str,
                    name=decl.name,
                    contract=decl.contract,
                    line=decl.line,
                    kind=info.kind,
                )
            )
    return Layout(
        contract=contract_name,
        entries=tuple(entries),
        total_slots=allocator.end_slot,
        skipped=tuple(skipped),
    )


def layout_struct(source: Source, contract_name: str, struct_name: str) -> Layout:
    """Expose a struct's internal field placement, mainly for debugging."""

    order = linearize(source, contract_name)
    structs, enums = _collect_types(source, order)
    resolver = Resolver(structs, enums)
    if struct_name not in structs:
        raise ParseError(f"unknown struct '{struct_name}'")
    allocator = _Allocator()
    entries: list[SlotEntry] = []
    for field_decl in structs[struct_name].fields:
        info = resolver.resolve(field_decl.type_str)
        slot, offset = allocator.place(info)
        entries.append(
            SlotEntry(
                slot=slot,
                offset=offset,
                size=info.size,
                slots=info.slots if info.kind != "value" else 1,
                type_str=field_decl.type_str,
                name=field_decl.name,
                contract=field_decl.contract,
                line=field_decl.line,
                kind=info.kind,
            )
        )
    return Layout(
        contract=f"{contract_name}.{struct_name}",
        entries=tuple(entries),
        total_slots=allocator.end_slot,
        skipped=(),
    )
