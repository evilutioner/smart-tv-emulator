"""Byte spans of leaf elements in a captured XML document, without re-serialising it.

The emulator replays capture bytes, so a field it writes live has to be replaced in place:
parsing and re-serialising would change quoting, whitespace and declaration bytes a driver
may compare. The conformance harness masks the same span on both sides.

A path names elements below the document's root, joined by dots, as the IR does
(`ecp-setting-mode` in a Roku device-info, `device.UDN` in a UPnP description). Only a leaf
that occurs once is addressable: an element that repeats or carries children is refused
rather than guessed at.
"""
from __future__ import annotations

import re

_ROOT = re.compile(rb"<([A-Za-z_][\w.:-]*)[^>]*>")


def _root_content(data: bytes) -> tuple[int, int]:
    for match in _ROOT.finditer(data):
        close = data.rfind(b"</" + match.group(1) + b">")
        if close < match.end():
            raise ValueError(f"XML root <{match.group(1).decode()}> is not closed")
        return match.end(), close
    raise ValueError("not an XML document")


def text_span(data: bytes, path: str) -> tuple[int, int] | None:
    """The bytes between the tags of the one leaf element at `path`, or None if absent."""
    start, end = _root_content(data)
    for segment in path.split("."):
        name = re.escape(segment.encode())
        opens = list(re.finditer(rb"<" + name + rb"(?:\s[^>]*?)?(/?)>", data[start:end]))
        if not opens:
            return None
        if len(opens) > 1:
            raise ValueError(f"XML element {segment!r} occurs {len(opens)} times")
        tag = opens[0]
        if tag.group(1):
            raise ValueError(f"XML element {segment!r} is an empty-element tag")
        inner = start + tag.end()
        close = data.find(b"</" + segment.encode() + b">", inner, end)
        if close < 0:
            raise ValueError(f"XML element {segment!r} is not closed")
        start, end = inner, close
    if b"<" in data[start:end]:
        raise ValueError(f"XML element {path!r} is not a leaf")
    return start, end


def replace_text(data: bytes, path: str, value: str) -> bytes:
    """`data` with the text of the leaf at `path` replaced by `value`, escaped."""
    span = text_span(data, path)
    if span is None:
        raise ValueError(f"XML element {path!r} is absent")
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return data[:span[0]] + escaped.encode() + data[span[1]:]
