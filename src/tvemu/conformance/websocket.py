"""The WebSocket driver: one real upgrade, then every captured frame in captured order.

A capture records frames, not how to reach them, so a platform describes each WebSocket
channel it speaks in its own `platforms/<id>/conformance/__init__.py`:

    CHANNELS = {
        "<channel>": {                       # the `channel` its evidence steps carry
            "path": "/…",                    # the upgrade path
            "protocols": ["…"],              # Sec-WebSocket-Protocol offered, if any
            "opening": ["<exchange id>"],    # exchanges every session replays first
            "masks": {"<step operation_id>": ["<json path>", …]},
            "inputs": {"<step operation_id>": ["<json path>", …]},
        },
    }
    def materialise(channel, step, received) -> dict[path, value]: …

`opening` is the captured handshake a session needs before anything else (an authentication
round, say); its outputs are compared too. `masks` names the emulator-owned values in those
outputs -- a random challenge, an uptime -- the only differences allowed there, since a
profile's substitutions cover replays and an opening exchange is not one. `inputs` names the
client-owned values in a captured client frame that must be recomputed for this session, and
`materialise` computes them from the frames received so far. A captured client frame is sent
byte for byte except at exactly those paths.

The description is plain data so a platform that ships without this harness carries nothing
that imports it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Callable

import aiohttp

from tvemu.platforms.common.evidence import Exchange, Step

from . import compare


@dataclass(frozen=True)
class Channel:
    id: str
    path: str
    protocols: tuple[str, ...] = ()
    opening: tuple[str, ...] = ()
    masks: dict[str, tuple[str, ...]] = field(default_factory=dict)
    inputs: dict[str, tuple[str, ...]] = field(default_factory=dict)
    materialise: Callable[[str, Step, list[bytes]], dict[str, Any]] | None = None


def platform_package(platform_id: str):
    """A platform's `conformance` package, or None for one that ships none.

    Besides `CHANNELS` and `materialise` it may set `COVERAGE = "complete"`: every replay of
    every profile is covered, so a replay left uncovered later is a regression, not a TODO.
    """
    name = f"tvemu.platforms.{platform_id}.conformance"
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name in (name, f"tvemu.platforms.{platform_id}"):
            return None
        raise


def channels(platform_id: str) -> dict[str, Channel]:
    """The WebSocket channels a platform describes, or {} for one that describes none."""
    name = f"tvemu.platforms.{platform_id}.conformance"
    module = platform_package(platform_id)
    rows = getattr(module, "CHANNELS", {})
    materialise = getattr(module, "materialise", None)
    found = {}
    for channel_id, row in rows.items():
        unknown = set(row) - {"path", "protocols", "opening", "masks", "inputs"}
        if unknown or not isinstance(row.get("path"), str) or not row["path"].startswith("/"):
            raise ValueError(f"{name}: channel {channel_id} is malformed")
        inputs = {key: tuple(paths) for key, paths in row.get("inputs", {}).items()}
        if inputs and materialise is None:
            raise ValueError(f"{name}: channel {channel_id} declares inputs but no materialise")
        found[channel_id] = Channel(
            channel_id, row["path"], tuple(row.get("protocols", ())),
            tuple(row.get("opening", ())),
            {key: tuple(paths) for key, paths in row.get("masks", {}).items()},
            inputs, materialise)
    return found


def channel_of(exchange: Exchange) -> str:
    return str(exchange.steps[0].metadata.get("channel", ""))


def replay_gap(exchange: Exchange, channel: Channel | None) -> str:
    """Why a WebSocket exchange cannot run, or "" when it can.

    What the evidence lacks comes first: no channel description can make up for a frame
    the capture never kept.
    """
    missing = [index for index, step in enumerate(exchange.steps)
               if step.direction == "in" and step.payload is None]
    if missing:
        return ("the capture keeps no client frame for step "
                f"{', '.join(map(str, missing))}, only its metadata, so nothing can be sent")
    unkept = [index for index, step in enumerate(exchange.steps)
              if step.direction == "out" and step.payload is None]
    if unkept:
        return f"the capture keeps no server frame for step {', '.join(map(str, unkept))}"
    if channel is None:
        return (f"no WebSocket channel description for {channel_of(exchange)!r} in this "
                f"platform's conformance package")
    return ""


def _outgoing(channel: Channel, step: Step, received: list[bytes]) -> bytes:
    """The captured client frame, with only its declared client-owned values recomputed."""
    paths = channel.inputs.get(step.operation_id, ())
    if not paths:
        return step.payload
    values = channel.materialise(channel.id, step, received)
    if set(values) != set(paths):
        raise ValueError(f"materialise returned {sorted(values)} for {step.operation_id}, "
                         f"which declares {sorted(paths)}")
    data = step.payload
    for path, value in values.items():
        data = compare.replace_json_value(
            data, path, json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())
    return data


async def run(url: str, authority: str, channel: Channel, exchanges: list[Exchange],
              substitutions: dict[str, tuple[str, ...]], values: dict[str, str],
              timeout: float, tls: bool) -> tuple[list[str], list[str]]:
    """Send and expect every step of `exchanges` over one session; (problems, notes)."""
    problems: list[str] = []
    notes: list[str] = []
    received: list[bytes] = []
    client_timeout = aiohttp.ClientWSTimeout(ws_receive=timeout, ws_close=timeout)
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, protocols=channel.protocols,
                                      headers={"Host": authority}, ssl=False if tls else None,
                                      timeout=client_timeout, autoping=True) as socket:
            for exchange in exchanges:
                masks = substitutions.get(exchange.id, ())
                for index, step in enumerate(exchange.steps):
                    where = f"{exchange.id} step {index}"
                    if step.direction == "in":
                        frame = _outgoing(channel, step, received)
                        try:
                            await socket.send_str(frame.decode("utf-8"))
                        except UnicodeDecodeError:
                            await socket.send_bytes(frame)
                        continue
                    message = await socket.receive(timeout)
                    if message.type == aiohttp.WSMsgType.TEXT:
                        data = message.data.encode("utf-8")
                    elif message.type == aiohttp.WSMsgType.BINARY:
                        data = message.data
                    else:
                        problems.append(f"{where}: expected a frame, the socket gave "
                                        f"{message.type.name}")
                        return problems, notes
                    received.append(data)
                    declared = masks + channel.masks.get(step.operation_id, ())
                    outcome = compare.Outcome()
                    compare.compare_body(step.payload, data, declared, values, outcome)
                    problems += [f"{where}: {problem}" for problem in outcome.problems]
                    notes += [f"{where}: {note}" for note in outcome.notes]
    return problems, notes
