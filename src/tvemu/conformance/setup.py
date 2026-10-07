"""Named setup hooks: the state a captured request presumes, reached over the real wire.

A captured request to a paired route carries no credential, or carries it as a placeholder
such as ``{token}``: the value belonged to the client that made the capture and is gone. A
platform says how a fresh adapter reaches that state in its own
`platforms/<id>/conformance/__init__.py`:

    SETUPS = {
        "<name>": {"provides": ["token", …]},  # the placeholders this hook fills
    }
    DEFAULT_SETUP = "<name>"   # for a paired route, or a placeholder no exchange names a hook for
    async def setup(name, client) -> dict:
        return {"values": {"token": "…"}, "headers": {"X-Token": "…"}}

`headers` may instead be a function ``(method, path) -> {name: value}`` for a scheme that
signs each request, such as HTTP Digest. A profile's conformance data names another hook for
one exchange under ``setup``.

The hook runs against the case's own fresh adapter before the captured request is sent. It
may send requests over the real listeners (`client.request`), read what the television shows
(`client.screen()`, the pairing panel the dashboard renders, where a PIN appears) and reuse
the captured client requests (`client.capture`). It never calls a handler and never sets
adapter state directly, so a hook that passes proves the pairing works as well.

What it returns is applied in one way everywhere: `values` fill the placeholders of the
captured request -- path, header values and body -- and render the same placeholders in the
expected answer, and `headers` are added to the request wherever the capture kept no header
of that name.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from tvemu.platforms.common.evidence import Capture

from . import http

HeaderSource = Callable[[str, str], dict[str, str]]


@dataclass(frozen=True)
class Hook:
    name: str
    provides: frozenset[str]


@dataclass
class Prepared:
    """What a hook established: placeholder values, and the headers each request gains."""

    values: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] | HeaderSource = field(default_factory=dict)

    def headers_for(self, method: str, path: str) -> dict[str, str]:
        return self.headers(method, path) if callable(self.headers) else dict(self.headers)


def hooks(module) -> tuple[dict[str, Hook], str]:
    """The setup hooks a platform's conformance package declares, and its default one."""
    name = getattr(module, "__name__", "conformance package")
    rows = getattr(module, "SETUPS", {})
    if rows and not callable(getattr(module, "setup", None)):
        raise ValueError(f"{name}: SETUPS declared without a setup function")
    found = {}
    for hook, row in rows.items():
        provides = row.get("provides", []) if isinstance(row, dict) else None
        if (not isinstance(provides, list) or not all(isinstance(item, str) for item in provides)
                or set(row) - {"provides"}):
            raise ValueError(f"{name}: setup {hook} is malformed")
        found[hook] = Hook(hook, frozenset(provides))
    default = getattr(module, "DEFAULT_SETUP", "")
    if default and default not in found:
        raise ValueError(f"{name}: DEFAULT_SETUP {default!r} is not in SETUPS")
    return found, default


class Client:
    """What a setup hook may touch: the real listeners, the screen and the capture."""

    def __init__(self, adapter, capture: Capture, protocol: str, authority: str,
                 timeout: float):
        self.adapter = adapter
        self.capture = capture
        self.protocol = protocol
        self.authority = authority
        self.timeout = timeout

    async def request(self, method: str, path: str, *, headers: dict[str, str] | None = None,
                      body: bytes = b"", protocol: str = "") -> http.HTTPResponse:
        """One HTTP request to a listener of this adapter, by default the case's own."""
        protocol = protocol or self.protocol
        if protocol not in self.adapter.bound:
            await self.adapter.start_protocol(protocol)
        host, port = self.adapter.bound[protocol]
        tls = self.adapter.listeners[protocol].ssl_context is not None
        payload = http.raw_request(method, path, self.authority, headers or {}, body)
        return await http.send(host, port, payload, tls=tls, timeout=self.timeout,
                               head=method == "HEAD")

    def screen(self) -> dict[str, Any]:
        """The pairing panel, as the dashboard shows it: where a television's PIN appears."""
        return dict(self.adapter.core.pairing or {})


def prepared(result: Any, hook: str) -> Prepared:
    if not isinstance(result, dict) or set(result) - {"values", "headers"}:
        raise ValueError(f"setup {hook} returned {type(result).__name__}, not "
                         f"{{'values': …, 'headers': …}}")
    values = result.get("values", {})
    headers = result.get("headers", {})
    if not isinstance(values, dict) or not all(isinstance(value, str)
                                               for value in values.values()):
        raise ValueError(f"setup {hook}: values must map placeholder names to strings")
    if not (callable(headers) or isinstance(headers, dict)):
        raise ValueError(f"setup {hook}: headers must be a map or a function")
    return Prepared(dict(values), headers)
