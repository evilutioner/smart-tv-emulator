"""Exact comparison of served bytes with captured bytes, excused only where a profile says.

Structural equality is not enough: whitespace, escaping, key order, separators and text
encoding are what a driver actually parses, so everything outside a declared runtime
substitution is compared byte for byte. A substitution is honoured by masking exactly the
span of its field on both sides and comparing what remains.

Four kinds of substitution path exist in profiles, and each has one masker here:

- a placeholder such as ``{host}``, written literally into the capture where the set's own
  address or a generated value stood;
- a JSON path such as ``id``, ``device.ip``, ``result[0].uri`` or ``audio/volume`` (a dot
  separates keys, ``[n]`` indexes an array, and every other character belongs to the key),
  or, in an XML body, the dotted element path of a leaf below the root (``device.UDN``);
- a response header name such as ``Set-Cookie``, whose value the emulator issues live;
- ``outer::inner``, a field of a document the set carried base64-encoded in the JSON string
  at ``outer`` (``content-data::ecp-setting-mode``): the two documents are decoded and
  compared with ``inner`` masked, and the encoded string is excused only by that comparison.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field

from tvemu.platforms.common.jsonbytes import (
    Node as _Node, Scanner as _Scanner, json_path, locate as _locate, replace_json_value,
    value_node as _value_node,
)
from tvemu.platforms.common.xmlbytes import value_span as _xml_text_span, expand_empty_leaf

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
    # Set by a caller comparing one frame of several: a declared path this frame lacks on
    # both sides is collected here, and the caller decides whether any frame carried it.
    absent: set[str] | None = None

    @property
    def ok(self) -> bool:
        return not self.problems


# ── JSON spans ───────────────────────────────────────────────────────────────────────────


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
    drops: dict[str, list[tuple[int, int]]] = {"expected": [], "observed": []}
    for path in paths:
        segments = json_path(path)
        found_expected = _locate(expected_root, segments)
        found_observed = _locate(observed_root, segments)
        if found_expected is None and found_observed is None:
            if outcome.absent is not None:
                outcome.absent.add(path)
            else:
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
                drops[side].append((start, end))
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
    for side, data in (("expected", expected), ("observed", observed)):
        cuts[side] += [(start, end, b"") for start, end in _dropped(data, drops[side])]
    return _cut(expected, cuts["expected"]), _cut(observed, cuts["observed"])


def _dropped(data: bytes, members: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Member spans to delete, neighbours joined first so each run gives up one comma."""
    runs: list[list[int]] = []
    for start, end in sorted(members):
        if runs and not data[runs[-1][1]:start].strip(b" \t\r\n,"):
            runs[-1][1] = max(runs[-1][1], end)
        else:
            runs.append([start, end])
    return [_member_with_comma(data, start, end) for start, end in runs]


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


# ── XML leaves ──────────────────────────────────────────────────────────────────────────


def _is_xml(data: bytes) -> bool:
    return data.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<")


def _mask_xml(expected: bytes, observed: bytes, paths: list[str], outcome: Outcome
              ) -> tuple[bytes, bytes]:
    # Empty-element and populated spellings are both measured representations of a leaf.
    # Normalize only explicitly declared leaves; attributes and neighbouring bytes stay exact.
    for path in paths:
        try:
            expected = expand_empty_leaf(expected, path)
            observed = expand_empty_leaf(observed, path)
        except ValueError as exc:
            outcome.problems.append(f"XML substitution {path!r}: {exc}")
    cuts: dict[str, list[tuple[int, int, bytes]]] = {"expected": [], "observed": []}
    for path in paths:
        try:
            found_expected = _xml_text_span(expected, path)
            found_observed = _xml_text_span(observed, path)
        except ValueError as exc:
            outcome.problems.append(f"XML substitution {path!r}: {exc}")
            continue
        if found_expected is None and found_observed is None:
            if outcome.absent is not None:
                outcome.absent.add(path)
            else:
                outcome.problems.append(f"declared substitution {path!r} is on neither side")
            continue
        if found_expected is None or found_observed is None:
            # An element is written in place, never added or dropped.
            side = "observed" if found_expected is None else "expected"
            outcome.problems.append(f"XML substitution {path!r} is only on the {side} side")
            continue
        cuts["expected"].append((*found_expected, MASK))
        cuts["observed"].append((*found_observed, MASK))
        if expected[slice(*found_expected)] != observed[slice(*found_observed)]:
            outcome.used.add(path)
        else:
            outcome.notes.append(f"substitution {path!r} served the captured value")
    return _cut(expected, cuts["expected"]), _cut(observed, cuts["observed"])


# ── base64 documents inside JSON ─────────────────────────────────────────────────────────


def _mask_encoded(expected: bytes, observed: bytes, paths: list[str],
                  values: dict[str, str], outcome: Outcome) -> tuple[bytes, bytes]:
    inner: dict[str, list[str]] = {}
    for path in paths:
        outer, _, rest = path.partition("::")
        inner.setdefault(outer, []).append(rest)
    try:
        roots = (_Scanner(expected).parse(), _Scanner(observed).parse())
    except (ValueError, UnicodeDecodeError) as exc:
        outcome.problems.append(f"substitutions {paths} need JSON on both sides: {exc}")
        return expected, observed
    cuts: list[list[tuple[int, int, bytes]]] = [[], []]
    for outer, fields in inner.items():
        segments = json_path(outer)
        nodes = [_locate(root, segments) for root in roots]
        if nodes[0] is None and nodes[1] is None:
            for rest in fields:
                if outcome.absent is not None:
                    outcome.absent.add(f"{outer}::{rest}")
                else:
                    outcome.problems.append(
                        f"declared substitution {outer + '::' + rest!r} is on neither side")
            continue
        documents = []
        for side, (root, data) in enumerate(zip(roots, (expected, observed))):
            node = _value_node(root, segments) if nodes[side] is not None else None
            try:
                text = json.loads(data[node.start:node.end]) if node else None
                documents.append(base64.b64decode(text, validate=True))
            except (ValueError, TypeError, binascii.Error) as exc:
                documents.append(None)
                outcome.problems.append(f"{outer}: not a base64 document "
                                        f"({'expected' if side == 0 else 'observed'}): {exc}")
            if node:
                cuts[side].append((node.start, node.end, MASK))
        if None in documents:
            continue
        nested = Outcome()
        compare_body(documents[0], documents[1], tuple(fields), values, nested)
        outcome.problems += [f"{outer}: {problem}" for problem in nested.problems]
        outcome.notes += [f"{outer}: {note}" for note in nested.notes]
        outcome.used |= {f"{outer}::{rest}" for rest in nested.used}
    return _cut(expected, cuts[0]), _cut(observed, cuts[1])


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
    encoded = [path for path in paths if "::" in path]
    paths = [path for path in paths if "::" not in path]
    left, right = expected, observed
    if encoded:
        left, right = _mask_encoded(left, right, encoded, values, outcome)
    if paths:
        mask = _mask_xml if _is_xml(left) else _mask_json
        left, right = mask(left, right, paths, outcome)
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

