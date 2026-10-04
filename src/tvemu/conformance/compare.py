"""Exact comparison of served bytes with captured bytes, excused only where a profile says.

Structural equality is not enough: whitespace, escaping, key order, separators and text
encoding are what a driver actually parses, so everything outside a declared runtime
substitution is compared byte for byte. A substitution is honoured by masking exactly the
span of its field on both sides and comparing what remains.

Three kinds of substitution path exist in profiles, and each has one masker here:

- a placeholder such as ``{host}``, written literally into the capture where the set's own
  address or a generated value stood;
- a JSON path such as ``id``, ``device.ip``, ``result[0].uri`` or ``audio/volume`` (a dot
  separates keys, ``[n]`` indexes an array, and every other character belongs to the key);
- a response header name such as ``Set-Cookie``, whose value the emulator issues live.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
# What a placeholder may stand for: one token of an address, id or path, never markup.
PLACEHOLDER_VALUE = rb"[^\s\"'<>]{1,255}?"
# Headers the transport writes on every response. Their absence from a capture says nothing
# about the set, so they are neither required nor reported as extra.
TRANSPORT_HEADERS = frozenset({"date", "content-length", "transfer-encoding", "connection",
                               "keep-alive"})
MASK = b"\x00masked\x00"
WINDOW = 40


@dataclass
class Outcome:
    """The verdict on one output step."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    used: set[str] = field(default_factory=set)

    @property
    def ok(self) -> bool:
        return not self.problems


# ── JSON spans ───────────────────────────────────────────────────────────────────────────


@dataclass
class _Node:
    start: int
    end: int
    # object: key -> (member start, member end, value node); array: list of nodes.
    members: dict[str, tuple[int, int, "_Node"]] | None = None
    items: list["_Node"] | None = None


class _Scanner:
    """A JSON reader that remembers where every value sits in the raw bytes."""

    def __init__(self, data: bytes):
        self.data = data
        self.at = 0

    def parse(self) -> _Node:
        self._space()
        node = self._value()
        self._space()
        if self.at != len(self.data):
            raise ValueError(f"trailing bytes at offset {self.at}")
        return node

    def _space(self) -> None:
        while self.at < len(self.data) and self.data[self.at] in b" \t\r\n":
            self.at += 1

    def _value(self) -> _Node:
        if self.at >= len(self.data):
            raise ValueError("unexpected end of JSON")
        char = self.data[self.at:self.at + 1]
        if char == b"{":
            return self._object()
        if char == b"[":
            return self._array()
        if char == b'"':
            start = self.at
            self._string()
            return _Node(start, self.at)
        start = self.at
        while self.at < len(self.data) and self.data[self.at] not in b",]} \t\r\n":
            self.at += 1
        json.loads(self.data[start:self.at])  # rejects anything that is not a scalar
        return _Node(start, self.at)

    def _string(self) -> str:
        start = self.at
        self.at += 1
        while True:
            if self.at >= len(self.data):
                raise ValueError("unterminated JSON string")
            char = self.data[self.at]
            if char == 0x5C:
                self.at += 2
                continue
            self.at += 1
            if char == 0x22:
                return json.loads(self.data[start:self.at])

    def _expect(self, char: bytes) -> None:
        if self.data[self.at:self.at + 1] != char:
            raise ValueError(f"expected {char!r} at offset {self.at}")
        self.at += 1

    def _object(self) -> _Node:
        start = self.at
        self.at += 1
        members: dict[str, tuple[int, int, _Node]] = {}
        self._space()
        if self.data[self.at:self.at + 1] == b"}":
            self.at += 1
            return _Node(start, self.at, members=members)
        while True:
            self._space()
            member_start = self.at
            key = self._string()
            self._space()
            self._expect(b":")
            self._space()
            value = self._value()
            members.setdefault(key, (member_start, value.end, value))
            self._space()
            if self.data[self.at:self.at + 1] == b",":
                self.at += 1
                continue
            self._expect(b"}")
            return _Node(start, self.at, members=members)

    def _array(self) -> _Node:
        start = self.at
        self.at += 1
        items: list[_Node] = []
        self._space()
        if self.data[self.at:self.at + 1] == b"]":
            self.at += 1
            return _Node(start, self.at, items=items)
        while True:
            self._space()
            items.append(self._value())
            self._space()
            if self.data[self.at:self.at + 1] == b",":
                self.at += 1
                continue
            self._expect(b"]")
            return _Node(start, self.at, items=items)


def json_path(path: str) -> tuple[str | int, ...]:
    """``result[0][0].volume`` -> ("result", 0, 0, "volume"); ``audio/volume`` is one key."""
    segments: list[str | int] = []
    for part in path.split("."):
        match = re.fullmatch(r"([^\[\]]*)((?:\[\d+\])*)", part)
        if match is None or (not match.group(1) and not match.group(2)):
            raise ValueError(f"malformed JSON path {path!r}")
        if match.group(1):
            segments.append(match.group(1))
        segments.extend(int(index) for index in re.findall(r"\[(\d+)\]", match.group(2)))
    return tuple(segments)


def _locate(root: _Node, segments: tuple[str | int, ...]
            ) -> tuple[int, int, bool] | None:
    """The span to mask: (start, end, is_whole_member), or None when the path is absent.

    A value is masked in place. A key present on one side only is masked as its whole member
    together with one separating comma, so the surrounding serialisation still compares.
    """
    node, parent, key = root, None, None
    for segment in segments:
        parent, key = node, segment
        if isinstance(segment, int):
            if node.items is None or segment >= len(node.items):
                return None
            node = node.items[segment]
        else:
            if node.members is None or segment not in node.members:
                return None
            node = node.members[segment][2]
    if parent is not None and isinstance(key, str):
        start, end, _ = parent.members[key]
        return start, end, True
    return node.start, node.end, False


def _member_with_comma(data: bytes, start: int, end: int) -> tuple[int, int]:
    """Widen a member span over the comma that separates it from a neighbour."""
    after = end
    while after < len(data) and data[after] in b" \t\r\n":
        after += 1
    if after < len(data) and data[after:after + 1] == b",":
        return start, after + 1
    before = start - 1
    while before >= 0 and data[before] in b" \t\r\n":
        before -= 1
    if before >= 0 and data[before:before + 1] == b",":
        return before, end
    return start, end


def _mask_json(expected: bytes, observed: bytes, paths: list[str], outcome: Outcome
               ) -> tuple[bytes, bytes]:
    try:
        expected_root = _Scanner(expected).parse()
        observed_root = _Scanner(observed).parse()
    except (ValueError, UnicodeDecodeError) as exc:
        outcome.problems.append(f"JSON substitutions {paths} need JSON on both sides: {exc}")
        return expected, observed
    cuts: dict[str, list[tuple[int, int, bytes]]] = {"expected": [], "observed": []}
    for path in paths:
        segments = json_path(path)
        found_expected = _locate(expected_root, segments)
        found_observed = _locate(observed_root, segments)
        if found_expected is None and found_observed is None:
            outcome.problems.append(f"declared substitution {path!r} is on neither side")
            continue
        for side, found, data in (("expected", found_expected, expected),
                                  ("observed", found_observed, observed)):
            if found is None:
                continue
            start, end, member = found
            other = found_observed if side == "expected" else found_expected
            if member and other is None:
                # Only this side carries the key: drop the whole member.
                start, end = _member_with_comma(data, start, end)
                cuts[side].append((start, end, b""))
            elif member:
                # Both sides carry the key: mask its value, keeping the key bytes compared.
                node = _value_node(expected_root if side == "expected" else observed_root,
                                   segments)
                cuts[side].append((node.start, node.end, MASK))
            else:
                cuts[side].append((start, end, MASK))
        if found_expected is not None and found_observed is not None:
            before = _slice(expected, expected_root, segments)
            after = _slice(observed, observed_root, segments)
            if before != after:
                outcome.used.add(path)
            else:
                outcome.notes.append(f"substitution {path!r} served the captured value")
        else:
            outcome.used.add(path)
    return _cut(expected, cuts["expected"]), _cut(observed, cuts["observed"])


def _value_node(root: _Node, segments: tuple[str | int, ...]) -> _Node:
    node = root
    for segment in segments:
        node = node.items[segment] if isinstance(segment, int) else node.members[segment][2]
    return node


def _slice(data: bytes, root: _Node, segments: tuple[str | int, ...]) -> bytes:
    node = _value_node(root, segments)
    return data[node.start:node.end]


def _cut(data: bytes, cuts: list[tuple[int, int, bytes]]) -> bytes:
    """Apply non-overlapping replacements, outermost first when two nest."""
    result = data
    kept: list[tuple[int, int, bytes]] = []
    for start, end, replacement in sorted(cuts, key=lambda cut: (cut[0], -cut[1])):
        if kept and start < kept[-1][1]:
            continue  # nested inside a span already masked
        kept.append((start, end, replacement))
    for start, end, replacement in reversed(kept):
        result = result[:start] + replacement + result[end:]
    return result


def replace_json_value(data: bytes, path: str, value: bytes) -> bytes:
    """`data` with the value at `path` replaced by `value`, every other byte kept."""
    root = _Scanner(data).parse()
    segments = json_path(path)
    if _locate(root, segments) is None:
        raise ValueError(f"{path!r} is not in the captured frame")
    node = _value_node(root, segments)
    return data[:node.start] + value + data[node.end:]


# ── placeholders ─────────────────────────────────────────────────────────────────────────


def _placeholders(expected: bytes, observed: bytes, names: list[str],
                  values: dict[str, str], outcome: Outcome) -> tuple[bytes, bytes]:
    """Match the observed bytes against the capture with each placeholder filled in.

    A placeholder whose value the harness knows (the advertised host) is rendering rather
    than masking: captures write the set's address that way everywhere, headers included, and
    it must be filled with exactly the advertised value whether or not a profile declares it.
    Any other placeholder stands for one token, and only where the profile declares it.
    """
    tokens = set(names) | {f"{{{name}}}" for name in values}
    pattern = b""
    last = 0
    for match in PLACEHOLDER.finditer(expected.decode("latin-1")):
        if match.group(0) not in tokens:
            continue
        pattern += re.escape(expected[last:match.start()])
        name = match.group(0)[1:-1]
        known = values.get(name)
        pattern += re.escape(known.encode()) if known is not None else PLACEHOLDER_VALUE
        if match.group(0) in names:
            outcome.used.add(match.group(0))
        last = match.end()
    if last == 0:
        return expected, observed
    pattern += re.escape(expected[last:])
    if re.fullmatch(pattern, observed, re.DOTALL):
        return observed, observed
    return expected, observed


# ── bodies and headers ───────────────────────────────────────────────────────────────────


def first_difference(expected: bytes, observed: bytes) -> str:
    """Where two byte strings part, with a bounded window of each."""
    offset = next((index for index, (left, right) in enumerate(zip(expected, observed))
                   if left != right), min(len(expected), len(observed)))
    start = max(0, offset - WINDOW // 2)

    def window(data: bytes) -> str:
        return repr(data[start:offset + WINDOW // 2])

    return (f"first difference at byte {offset} (expected {len(expected)} bytes, observed "
            f"{len(observed)}): expected {window(expected)}, observed {window(observed)}")


def compare_body(expected: bytes | None, observed: bytes, substitutions: tuple[str, ...],
                 values: dict[str, str], outcome: Outcome,
                 headers: frozenset[str] = frozenset()) -> None:
    """Compare one payload, masking only the declared spans.

    `headers` are the lower-cased names of the captured response headers; a substitution
    naming one of them masks that header and never a body field.
    """
    expected = expected if expected is not None else b""
    placeholders = [path for path in substitutions if PLACEHOLDER.fullmatch(path)]
    paths = [path for path in substitutions
             if path not in placeholders and path.lower() not in headers]
    left, right = expected, observed
    if paths:
        left, right = _mask_json(left, right, paths, outcome)
    present = [name for name in placeholders if name.encode() in left]
    left, right = _placeholders(left, right, present, values, outcome)
    if left != right:
        outcome.problems.append("body: " + first_difference(left, right))


def header_substitutions(substitutions: tuple[str, ...],
                         headers: dict[str, str]) -> set[str]:
    """Declared paths that name a captured response header, lower-cased."""
    names = {name.lower() for name in headers}
    return {path.lower() for path in substitutions if path.lower() in names}


def compare_headers(expected: dict[str, str], observed: list[tuple[str, str]],
                    substitutions: tuple[str, ...], values: dict[str, str],
                    outcome: Outcome) -> None:
    """Every captured header must arrive with its captured value.

    A capture records the headers its tool kept, not necessarily every header the set sent,
    so a served header the capture does not name is reported as a note rather than a fault.
    """
    masked = header_substitutions(substitutions, expected)
    placeholders = [path for path in substitutions if PLACEHOLDER.fullmatch(path)]
    seen: dict[str, list[str]] = {}
    for name, value in observed:
        seen.setdefault(name.lower(), []).append(value)
    for name, value in expected.items():
        key = name.lower()
        if key not in seen:
            outcome.problems.append(f"header {name}: missing")
            continue
        if key in masked:
            outcome.used.add(name)
            continue
        got = seen[key][0]
        left, right = value.encode("latin-1"), got.encode("latin-1")
        present = [token for token in placeholders if token.encode() in left]
        left, right = _placeholders(left, right, present, values, outcome)
        if left != right:
            outcome.problems.append(f"header {name}: expected {value!r}, observed {got!r}")
    declared = {name.lower() for name in expected}
    extra = [name for name, _ in observed
             if name.lower() not in declared and name.lower() not in TRANSPORT_HEADERS]
    if extra:
        outcome.notes.append(f"served headers the capture does not record: {', '.join(extra)}")


def unaccounted(substitutions: tuple[str, ...], outcome: Outcome) -> list[str]:
    """Declared substitutions this output never exercised."""
    return [path for path in substitutions if path not in outcome.used]

