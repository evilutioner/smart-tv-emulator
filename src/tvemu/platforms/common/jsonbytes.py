"""Where every value of a JSON document sits in its raw bytes.

A captured frame is replayed byte for byte, so a field a handler writes live is spliced into
the captured bytes rather than re-serialised: separators, key order and escaping stay the
set's own. The conformance harness masks the same spans when it compares.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class Node:
    start: int
    end: int
    # object: key -> (member start, member end, value node); array: list of nodes.
    members: dict[str, tuple[int, int, "Node"]] | None = None
    items: list["Node"] | None = None


class Scanner:
    """A JSON reader that remembers where every value sits in the raw bytes."""

    def __init__(self, data: bytes):
        self.data = data
        self.at = 0

    def parse(self) -> Node:
        self._space()
        node = self._value()
        self._space()
        if self.at != len(self.data):
            raise ValueError(f"trailing bytes at offset {self.at}")
        return node

    def _space(self) -> None:
        while self.at < len(self.data) and self.data[self.at] in b" \t\r\n":
            self.at += 1

    def _value(self) -> Node:
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
            return Node(start, self.at)
        start = self.at
        while self.at < len(self.data) and self.data[self.at] not in b",]} \t\r\n":
            self.at += 1
        json.loads(self.data[start:self.at])  # rejects anything that is not a scalar
        return Node(start, self.at)

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

    def _object(self) -> Node:
        start = self.at
        self.at += 1
        members: dict[str, tuple[int, int, Node]] = {}
        self._space()
        if self.data[self.at:self.at + 1] == b"}":
            self.at += 1
            return Node(start, self.at, members=members)
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
            return Node(start, self.at, members=members)

    def _array(self) -> Node:
        start = self.at
        self.at += 1
        items: list[Node] = []
        self._space()
        if self.data[self.at:self.at + 1] == b"]":
            self.at += 1
            return Node(start, self.at, items=items)
        while True:
            self._space()
            items.append(self._value())
            self._space()
            if self.data[self.at:self.at + 1] == b",":
                self.at += 1
                continue
            self._expect(b"]")
            return Node(start, self.at, items=items)


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


def locate(root: Node, segments: tuple[str | int, ...]
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


def value_node(root: Node, segments: tuple[str | int, ...]) -> Node:
    node = root
    for segment in segments:
        node = node.items[segment] if isinstance(segment, int) else node.members[segment][2]
    return node


def replace_json_value(data: bytes, path: str, value: bytes) -> bytes:
    """`data` with the value at `path` replaced by `value`, every other byte kept."""
    root = Scanner(data).parse()
    segments = json_path(path)
    if locate(root, segments) is None:
        raise ValueError(f"{path!r} is not in the captured frame")
    node = value_node(root, segments)
    return data[:node.start] + value + data[node.end:]
