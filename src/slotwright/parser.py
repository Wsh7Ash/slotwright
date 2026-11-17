"""Solidity source scanning for storage layout.

Only the declarations that influence storage layout are read: contract headers
and their inheritance lists, top-level state variables, struct definitions and
enum names. Function and modifier bodies are skipped wholesale, which keeps the
scanner small and predictable.

This is a scanner, not a compiler. It does not resolve imports, evaluate
expressions, or type-check. Those limits are documented in docs/USAGE.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class ParseError(Exception):
    """The source could not be read as a Solidity file."""


IDENT = re.compile(r"^[A-Za-z_$][\w$]*$")
CONTRACT_RE = re.compile(
    r"\b(?:abstract\s+)?(contract|library|interface)\s+([A-Za-z_$][\w$]*)"
    r"\s*(?:is\s+([^{]*?))?\s*\{"
)
ATTRIBUTE_RE = re.compile(
    r"\b(public|private|internal|external|constant|immutable|transient|virtual)\b"
)
OVERRIDE_RE = re.compile(r"\boverride\s*(?:\([^)]*\))?")
SKIP_FIRST_WORDS = {
    "using",
    "event",
    "error",
    "type",
    "function",
    "modifier",
    "constructor",
    "receive",
    "fallback",
    "if",
    "for",
    "while",
    "return",
    "emit",
    "assembly",
}


@dataclass(frozen=True)
class VarDecl:
    """A state variable or struct field declaration."""

    name: str
    type_str: str
    contract: str
    line: int
    is_constant: bool = False
    is_immutable: bool = False
    is_transient: bool = False

    @property
    def occupies_storage(self) -> bool:
        return not (self.is_constant or self.is_immutable or self.is_transient)


@dataclass(frozen=True)
class StructDef:
    name: str
    contract: str
    fields: tuple[VarDecl, ...]
    line: int


@dataclass(frozen=True)
class Contract:
    name: str
    kind: str
    bases: tuple[str, ...]
    vars: tuple[VarDecl, ...]
    structs: tuple[StructDef, ...]
    enums: tuple[str, ...]
    line: int


@dataclass
class Source:
    path: str
    contracts: dict[str, Contract] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def require(self, name: str | None) -> Contract:
        if name is None:
            if not self.order:
                raise ParseError("no contracts found")
            # Default to the last contract declared in the file.
            return self.contracts[self.order[-1]]
        try:
            return self.contracts[name]
        except KeyError:
            known = ", ".join(self.order) or "none"
            raise ParseError(f"contract '{name}' not found (known: {known})") from None


def mask_source(src: str) -> str:
    """Blank comments and string contents while preserving offsets and lines.

    Scanning the masked text means braces and semicolons inside comments,
    strings or initializers cannot confuse the declaration walker.
    """

    out = list(src)
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            end = src.find("\n", i)
            if end == -1:
                end = n
            for k in range(i, end):
                out[k] = " "
            i = end
        elif ch == "/" and i + 1 < n and src[i + 1] == "*":
            found = src.find("*/", i + 2)
            end = n if found == -1 else found + 2
            for k in range(i, end):
                if src[k] != "\n":
                    out[k] = " "
            i = end
        elif ch in {'"', "'"}:
            quote = ch
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == quote:
                    j += 1
                    break
                j += 1
            stop = min(j - 1, n)
            for k in range(i + 1, stop):
                if src[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def _line_index(src: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(src):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def _matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for i in range(open_index, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ParseError(f"unbalanced braces starting at offset {open_index}")


def _line_at_statement(
    body: str, body_offset: int, stmt_start: int, starts: list[int]
) -> int:
    """Line of the first non-blank character of a statement, not of the newline before it."""

    tail = body[stmt_start:]
    lead = len(tail) - len(tail.lstrip())
    return _line_of(starts, body_offset + stmt_start + lead)


def _cut_initializer(decl: str) -> str:
    """Drop `= ...` at bracket depth zero, ignoring `=>`, `>=`, `==` and friends."""

    parens = 0
    brackets = 0
    for i, ch in enumerate(decl):
        if ch == "(":
            parens += 1
        elif ch == ")":
            parens -= 1
        elif ch == "[":
            brackets += 1
        elif ch == "]":
            brackets -= 1
        elif ch == "=" and parens == 0 and brackets == 0:
            prev = decl[i - 1] if i else ""
            nxt = decl[i + 1] if i + 1 < len(decl) else ""
            if prev in "=!<>+-*/%&|^" or nxt == "=":
                continue
            return decl[:i]
    return decl


def _parse_decl(
    text: str, contract: str, line: int, *, is_field: bool = False
) -> VarDecl | None:
    decl = _cut_initializer(text).strip()
    if not decl:
        return None
    lowered = decl.split(None, 1)[0]
    if lowered in SKIP_FIRST_WORDS:
        return None
    if lowered in {"struct", "enum"}:
        return None

    is_constant = bool(re.search(r"\bconstant\b", decl))
    is_immutable = bool(re.search(r"\bimmutable\b", decl))
    is_transient = bool(re.search(r"\btransient\b", decl))
    if not is_field:
        decl = OVERRIDE_RE.sub(" ", decl)
        decl = ATTRIBUTE_RE.sub(" ", decl)
    decl = " ".join(decl.split())

    parts = decl.split(" ")
    if len(parts) < 2:
        return None
    name = parts[-1]
    if not IDENT.match(name):
        return None
    type_str = " ".join(parts[:-1]).strip()
    if not type_str:
        return None
    return VarDecl(
        name=name,
        type_str=type_str,
        contract=contract,
        line=line,
        is_constant=is_constant,
        is_immutable=is_immutable,
        is_transient=is_transient,
    )


def _parse_fields(
    body: str, contract: str, starts: list[int], body_offset: int
) -> tuple[VarDecl, ...]:
    fields: list[VarDecl] = []
    depth = 0
    start = 0
    for i, ch in enumerate(body):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            line = _line_at_statement(body, body_offset, start, starts)
            decl = _parse_decl(body[start:i], contract, line, is_field=True)
            if decl is not None:
                fields.append(decl)
            start = i + 1
    return tuple(fields)


def _split_bases(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    bases: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in raw:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            bases.append("".join(current))
            current = []
        else:
            current.append(ch)
    bases.append("".join(current))
    cleaned = []
    for base in bases:
        name = base.split("(")[0].strip()
        if name:
            cleaned.append(name)
    return tuple(cleaned)


def parse_source(text: str, path: str = "<memory>") -> Source:
    masked = mask_source(text)
    starts = _line_index(text)
    source = Source(path=path)

    rows: list[tuple[re.Match[str], int]] = []
    for match in CONTRACT_RE.finditer(masked):
        # Skip matches that start inside an already-consumed contract body.
        if rows and match.start() < rows[-1][1]:
            continue
        try:
            close = _matching_brace(masked, match.end() - 1)
        except ParseError as exc:
            raise ParseError(f"{path}: {exc}") from None
        rows.append((match, close))

    for match, close in rows:
        kind = match.group(1)
        name = match.group(2)
        bases = _split_bases(match.group(3))
        header_line = _line_of(starts, match.start())
        body_start = match.end()  # just after '{'
        body = masked[body_start:close]

        variables: list[VarDecl] = []
        structs: list[StructDef] = []
        enums: list[str] = []

        i = 0
        stmt_start = 0
        while i < len(body):
            ch = body[i]
            if ch == "{":
                header = body[stmt_start:i].strip()
                end = _matching_brace(body, i)
                words = header.split()
                if words and words[0] == "struct" and len(words) >= 2:
                    struct_line = _line_at_statement(
                        body, body_start, stmt_start, starts
                    )
                    fields = _parse_fields(
                        body[i + 1 : end], name, starts, body_start + i + 1
                    )
                    structs.append(
                        StructDef(
                            name=words[1],
                            contract=name,
                            fields=fields,
                            line=struct_line,
                        )
                    )
                elif words and words[0] == "enum" and len(words) >= 2:
                    enums.append(words[1])
                i = end + 1
                stmt_start = i
                continue
            if ch == ";":
                line = _line_at_statement(body, body_start, stmt_start, starts)
                decl = _parse_decl(body[stmt_start:i], name, line)
                if decl is not None:
                    variables.append(decl)
                stmt_start = i + 1
            elif ch == "}":
                break
            i += 1

        contract = Contract(
            name=name,
            kind=kind,
            bases=bases,
            vars=tuple(variables),
            structs=tuple(structs),
            enums=tuple(enums),
            line=header_line,
        )
        if name in source.contracts:
            raise ParseError(f"{path}: duplicate contract '{name}'")
        source.contracts[name] = contract
        source.order.append(name)

    if not source.order:
        raise ParseError(f"{path}: no contracts, libraries or interfaces found")
    return source


def parse_file(path: str | Path) -> Source:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"cannot read {p}: {exc}") from None
    return parse_source(text, str(p))
