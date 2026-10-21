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


def expand_empty_leaf(data: bytes, path: str) -> bytes:
    """Expand one declared empty leaf, preserving everything outside that element."""
    if ".@" in path:
        return data
    start, end = _root_content(data)
    for index, segment in enumerate(path.split(".")):
        name = re.escape(segment.encode())
        matches = list(re.finditer(rb"<" + name + rb"(?:\s[^>]*?)?(/?)>", data[start:end]))
        if not matches:
            return data
        if len(matches) != 1:
            raise ValueError(f"XML element {segment!r} occurs {len(matches)} times")
        tag = matches[0]
        if tag.group(1):
            if index != len(path.split(".")) - 1:
                raise ValueError("An empty element cannot contain a child path")
            absolute_start, absolute_end = start + tag.start(), start + tag.end()
            opening = data[absolute_start:absolute_end - 2].rstrip() + b">"
            return data[:absolute_start] + opening + b"</" + segment.encode() + b">" + data[absolute_end:]
        inner = start + tag.end()
        close = data.find(b"</" + segment.encode() + b">", inner, end)
        if close < 0:
            raise ValueError(f"XML element {segment!r} is not closed")
        start, end = inner, close
    return data


def value_span(data: bytes, path: str) -> tuple[int, int] | None:
    """A leaf text span, or one explicitly addressed XML attribute (`path.@name`)."""
    if ".@" not in path:
        return text_span(data, path)
    parent, attribute = path.rsplit(".@", 1)
    start, end = _root_content(data)
    opening_start = opening_end = 0
    for segment in parent.split("."):
        name = re.escape(segment.encode())
        matches = list(re.finditer(rb"<" + name + rb"(?:\s[^>]*?)?(/?)>", data[start:end]))
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError(f"XML element {segment!r} occurs {len(matches)} times")
        tag = matches[0]
        opening_start, opening_end = start + tag.start(), start + tag.end()
        if tag.group(1):
            if segment != parent.split(".")[-1]:
                raise ValueError("An empty element cannot contain a child path")
            start = end = opening_end
        else:
            start = opening_end
            end = data.find(b"</" + segment.encode() + b">", start, end)
            if end < 0:
                raise ValueError(f"XML element {segment!r} is not closed")
    match = re.search(rb"\s" + re.escape(attribute.encode()) + rb"\s*=\s*([\"'])(.*?)\1",
                      data[opening_start:opening_end], re.S)
    return ((opening_start + match.start(2), opening_start + match.end(2)) if match else None)


def replace_value(data: bytes, path: str, value: str) -> bytes:
    """Replace a declared XML value; attributes retain their original quoting."""
    expanded = expand_empty_leaf(data, path)
    if value == "" and expanded != data:
        return data
    data = expanded
    span = value_span(data, path)
    if span is None:
        raise ValueError(f"XML value {path!r} is absent")
    escaped = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
    return data[:span[0]] + escaped.encode() + data[span[1]:]
