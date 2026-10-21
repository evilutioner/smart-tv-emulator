"""Replaying a captured raw TCP session over a real socket.

A `tcp` exchange is an ordered list of byte steps on one connection. Each `in` step is written
as captured; each `out` step is read back, exactly as many bytes as the capture holds, and
compared byte for byte. A protocol on raw TCP has no framing this driver could know, so the
captured lengths are the framing.

Two step metadata keys let an encrypted session run too, mirroring the WebSocket driver:

- an `out` step's `masks`, a list of `[offset, length]` ranges, names emulator-owned bytes
  -- a public key the set draws at start-up, an IV -- the only bytes allowed to differ;
- an `in` step marked `"materialise": true` carries client-owned bytes, such as a key the
  client drew, and the platform's conformance package computes them for this session:

      def materialise_stream(step, received, state) -> bytes: …

  `received` is every `out` step observed so far, `state` a dict the function keeps across
  the steps of one session.

A step that waits on the viewer -- an Allow prompt on screen -- is reached by the case's setup
hook, which answers the prompt the way the dashboard does.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from tvemu.platforms.common.evidence import Exchange, Step

Materialise = Callable[[Step, list[bytes], dict[str, Any]], bytes]


def masks(step: Step) -> list[tuple[int, int]]:
    rows = step.metadata.get("masks", [])
    if (not isinstance(rows, list)
            or not all(isinstance(row, list) and len(row) == 2
                       and all(type(value) is int and value >= 0 for value in row)
                       for row in rows)):
        raise ValueError("masks must be [offset, length] pairs")
    return [(offset, length) for offset, length in rows]


def masked(data: bytes, ranges: list[tuple[int, int]]) -> bytes:
    out = bytearray(data)
    for offset, length in ranges:
        out[offset:offset + length] = bytes(len(out[offset:offset + length]))
    return bytes(out)


async def run(host: str, port: int, exchange: Exchange, timeout: float,
              materialise: Materialise | None = None) -> tuple[list[str], list[str]]:
    """(problems, notes) for one exchange replayed on a fresh connection."""
    problems: list[str] = []
    received: list[bytes] = []
    state: dict[str, Any] = {}
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    try:
        for index, step in enumerate(exchange.steps):
            payload = step.payload or b""
            if step.direction == "in":
                if step.metadata.get("materialise"):
                    if materialise is None:
                        raise ValueError(f"{exchange.id}: step {index} needs "
                                         "materialise_stream, which the platform lacks")
                    payload = materialise(step, received, state)
                writer.write(payload)
                await writer.drain()
                continue
            try:
                observed = await asyncio.wait_for(reader.readexactly(len(payload)), timeout)
            except asyncio.IncompleteReadError as error:
                observed = error.partial
            except asyncio.TimeoutError:
                observed = b""
            received.append(observed)
            ranges = masks(step)
            if len(observed) != len(payload) or masked(observed, ranges) != masked(payload,
                                                                                  ranges):
                problems.append(f"{exchange.id}: step {index}: expected {payload.hex(' ')}, "
                                f"observed {observed.hex(' ') or 'nothing'}")
                break
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
    return problems, []
