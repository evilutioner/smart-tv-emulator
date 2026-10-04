"""A deliberately small HTTP/1.1 client that keeps every byte a server sent.

aiohttp's client folds header case, merges repeats and decodes bodies; a conformance check
needs the opposite. This speaks one request per connection over a real socket and returns
the status, the header list in arrival order and spelling, and the undecoded body.
"""
from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass

from tvemu.platforms.common.evidence import Step

# Request headers the harness writes itself, because their captured values name the
# physical set's socket rather than the one under test.
OWNED_REQUEST_HEADERS = frozenset({"host", "content-length", "connection"})


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    reason: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


def request_bytes(step: Step, authority: str) -> bytes:
    """The captured request as it goes on the wire, addressed to the advertised endpoint."""
    method = step.metadata["method"]
    path = step.metadata["path"]
    body = step.payload or b""
    lines = [f"{method} {path} HTTP/1.1", f"Host: {authority}"]
    captured = step.metadata.get("headers", {})
    if isinstance(captured, dict):
        lines += [f"{name}: {value}" for name, value in captured.items()
                  if name.lower() not in OWNED_REQUEST_HEADERS]
    if body or method in ("POST", "PUT", "PATCH"):
        lines.append(f"Content-Length: {len(body)}")
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


async def send(host: str, port: int, payload: bytes, *, tls: bool, timeout: float,
               head: bool = False) -> HTTPResponse:
    context = None
    if tls:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=context), timeout)
    try:
        writer.write(payload)
        await writer.drain()
        return await asyncio.wait_for(_read_response(reader, head), timeout)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, ssl.SSLError):
            pass


async def _read_response(reader: asyncio.StreamReader, head: bool) -> HTTPResponse:
    status_line = (await reader.readline()).decode("latin-1").rstrip("\r\n")
    parts = status_line.split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise ValueError(f"not an HTTP status line: {status_line!r}")
    headers: list[tuple[str, str]] = []
    while True:
        line = (await reader.readline()).decode("latin-1").rstrip("\r\n")
        if not line:
            break
        name, _, value = line.partition(":")
        headers.append((name, value.strip()))
    lookup = {name.lower(): value for name, value in headers}
    if head:
        body = b""
    elif lookup.get("transfer-encoding", "").lower() == "chunked":
        body = await _chunked(reader)
    elif "content-length" in lookup:
        body = await reader.readexactly(int(lookup["content-length"]))
    else:
        body = await reader.read()
    return HTTPResponse(int(parts[1]), parts[2] if len(parts) > 2 else "", tuple(headers), body)


async def _chunked(reader: asyncio.StreamReader) -> bytes:
    body = b""
    while True:
        size = int((await reader.readline()).split(b";")[0].strip() or b"0", 16)
        if size == 0:
            while (await reader.readline()).strip():
                pass
            return body
        body += await reader.readexactly(size)
        await reader.readline()
