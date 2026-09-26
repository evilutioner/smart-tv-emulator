"""Declared reply types: what a route answers with, and how that firmware serialises it.

A handler never builds a `web.Response` itself. It returns `style.ok(value)` or raises
`WireError`, and the platform's own `ReplyStyle` decides the bytes. The style is platform data
in the same sense a `ProtocolSpec` is: a television that writes JSON with spaces, or names a
charset, or answers an unknown route with an HTML crash page, says so here rather than hiding
the fact inside a handler. Nothing is normalised into a house style -- the observed difference
is the product.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable

from aiohttp import web


class WireError(Exception):
    """A refusal, before it is rendered onto any particular wire.

    `status` is the status the emulated firmware answers with, which is not always the status
    HTTP would suggest: a set that returns 200 with a failure envelope, or 403 for an unknown
    route, carries that here and an `ErrorFormat` renders it.
    """

    def __init__(self, status: int, detail: str = "", payload: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(detail or str(status))
        self.status = status
        self.detail = detail
        self.payload = payload or {}
        # A refusal that has to name something: the methods a route does allow, the Digest
        # challenge a set answers an unauthenticated request with.
        self.headers = headers or {}


@dataclass(frozen=True)
class ReplyStyle:
    """One serialisation family of one platform.

    `separators` is `None` for a device whose firmware writes JSON with the default spacing,
    and `(",", ":")` for one that writes it compactly. Two families on the same television is
    ordinary: the difference is observable on the wire, so it is declared rather than smoothed.
    """

    id: str
    content_type: str
    separators: tuple[str, str] | None = None
    charset: str = ""
    headers: tuple[tuple[str, str], ...] = ()

    def encode(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode()
        return json.dumps(value, separators=self.separators).encode()

    def ok(self, value: Any = b"", status: int = 200, content_type: str = "",
           headers: dict[str, str] | None = None) -> web.Response:
        """One reply in this family.

        `content_type` overrides the family's for a route whose captured type is per-device
        data rather than a platform trait -- one television answers a route with an image
        where the rest of its family answers XML. It is a parameter rather than a header
        because aiohttp refuses a response that carries both.
        """
        merged = dict(self.headers)
        merged.update(headers or {})
        if "Content-Type" in merged:
            raise ValueError("Content-Type is the style's to set: pass content_type instead")
        return web.Response(body=self.encode(value), status=status,
                            content_type=content_type or self.content_type,
                            charset=self.charset or None, headers=merged or None)


@dataclass(frozen=True)
class ErrorFormat:
    """How one platform renders a `WireError` onto one of its wires.

    `render` returns the body value; `status` may differ from the error's own, for a firmware
    that reports failure inside a 200 envelope. A platform with two wires -- an HTTP surface and
    a WebSocket one, say -- declares two formats and neither has to know about the other.
    """

    style: ReplyStyle
    render: Callable[[WireError], Any]
    status: Callable[[WireError], int] = field(default=lambda error: error.status)

    def response(self, error: WireError) -> web.Response:
        return self.style.ok(self.render(error), status=self.status(error),
                             headers=error.headers or None)


TEXT = ReplyStyle("text", "text/plain", charset="utf-8")
# aiohttp's own refusal body, reproduced so a handler can raise instead of constructing one.
STATUS_LINE = ErrorFormat(TEXT, lambda error: f"{error.status}: {HTTPStatus(error.status).phrase}")
XML = ReplyStyle("xml", "text/xml")
JSON_COMPACT = ReplyStyle("json-compact", "application/json", separators=(",", ":"))
JSON_SPACED = ReplyStyle("json-spaced", "application/json")


def missing_capture(core, operation: str, profile_id: str, transport: str, peer: str,
                    detail: str, status: int = 501, request_id: str = "") -> WireError:
    """The refusal for a route this capture has no fixture for.

    Every platform reached the same conclusion independently -- a fabricated answer is worse
    than an honest refusal -- so the event record lives here once instead of three times.
    """
    core.record("unsupported", operation, transport=transport, peer=peer, status=status,
                detail=f"{detail}: {profile_id}", request_id=request_id)
    return WireError(status, detail)
