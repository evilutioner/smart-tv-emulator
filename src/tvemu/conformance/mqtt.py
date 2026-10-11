"""The MQTT driver: real client sessions against a broker the television runs.

On a set that is an MQTT broker, one captured exchange is rarely self-contained: a query is
answered only on a paired session subscribed to its data topic, a token is presented on a
second connection, a toast goes to the client that asked while another one's PIN is up. A
platform describes how each replay is reached in its own `platforms/<id>/conformance/`:

    MQTT = {
        "protocol": "<protocol id>",     # the listener the broker runs on
        "tls": True,                      # whether a client speaks TLS to it
        "default": [["a", "<exchange>"], …, ["a", "*"]],
        "scripts": {"<exchange>": [["a", "<exchange>"], ["b", "*"], …]},
        "masks": {"<step operation_id>": ["<json path>", …]},
    }
    def mqtt_values(session, step, received, screen) -> dict[str, str | None]: …

A script is the ordered list of captured exchanges a replay needs, each on a named session,
with `*` standing for the replay itself. Every exchange in it is sent and compared, so the
pairing a query depends on is proved every time it runs. `masks` names the emulator-owned
values in an output -- a token, an issue time -- the only differences allowed in an exchange
that is not itself the replay.

Steps carry their packet in `metadata.packet`: CONNECT, SUBSCRIBE (`topics`), PUBLISH
(`topic` and the payload) and DISCONNECT in; CONNACK (`code`), SUBACK (`codes`) and PUBLISH
out, or `none` for an answer that never came. `<client id>` in a topic is the session's own
client id. `mqtt_values` gives what the client owned and the capture could not keep: the
client id, username and password of a CONNECT, and any `{placeholder}` in a published
payload. It sees what each session has received so far and what the television shows.
"""
from __future__ import annotations

import asyncio
import ssl
from dataclasses import dataclass, field
from typing import Any, Callable

from tvemu.platforms.common.evidence import Capture, Step

from . import compare

CLIENT_ID = "<client id>"
TARGET = "*"
# How long an answer that never came is waited for. The emulator answers in the same loop
# turn, so a short window proves silence; the capture records how long the set was given.
QUIET = 0.3

CONNECT, CONNACK, PUBLISH, SUBSCRIBE, SUBACK, PINGRESP, DISCONNECT = 1, 2, 3, 8, 9, 13, 14
NAMES = {CONNECT: "CONNECT", CONNACK: "CONNACK", PUBLISH: "PUBLISH", SUBACK: "SUBACK",
         PINGRESP: "PINGRESP"}


@dataclass(frozen=True)
class Description:
    protocol: str
    tls: bool
    default: tuple[tuple[str, str], ...]
    scripts: dict[str, tuple[tuple[str, str], ...]]
    masks: dict[str, tuple[str, ...]]
    values: Callable[..., dict[str, Any]]

    def script(self, exchange_id: str) -> tuple[tuple[str, str], ...]:
        """The replay's script, with `*` resolved to the replay itself."""
        rows = self.scripts.get(exchange_id, self.default)
        return tuple((session, exchange_id if item == TARGET else item)
                     for session, item in rows)


def description(module) -> Description | None:
    """A platform's MQTT description, or None for one that declares none."""
    row = getattr(module, "MQTT", None)
    if row is None:
        return None
    name = getattr(module, "__name__", "conformance package")
    values = getattr(module, "mqtt_values", None)
    if (not isinstance(row, dict) or set(row) - {"protocol", "tls", "default", "scripts",
                                                  "masks"}
            or not isinstance(row.get("protocol"), str) or values is None):
        raise ValueError(f"{name}: MQTT is malformed or has no mqtt_values")

    def script(rows: Any) -> tuple[tuple[str, str], ...]:
        if (not isinstance(rows, list) or not rows
                or not all(isinstance(item, list) and len(item) == 2 for item in rows)
                or sum(item[1] == TARGET for item in rows) != 1):
            raise ValueError(f"{name}: an MQTT script lists [session, exchange] pairs and "
                             f"names the replay as {TARGET!r} exactly once")
        return tuple((str(session), str(item)) for session, item in rows)

    return Description(
        row["protocol"], bool(row.get("tls")), script(row.get("default")),
        {key: script(rows) for key, rows in row.get("scripts", {}).items()},
        {key: tuple(paths) for key, paths in row.get("masks", {}).items()}, values)


# ── a minimal MQTT 3.1.1 codec, the client's half ────────────────────────────────────────


def _length(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value % 128, value // 128
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _string(value: str | bytes) -> bytes:
    data = value.encode() if isinstance(value, str) else value
    return len(data).to_bytes(2, "big") + data


def _packet(kind: int, body: bytes, flags: int = 0) -> bytes:
    return bytes([kind << 4 | flags]) + _length(len(body)) + body


def connect_packet(client_id: str, username: str | None, password: str | None) -> bytes:
    flags = (0x80 if username is not None else 0) | (0x40 if password is not None else 0) | 0x02
    body = _string("MQTT") + bytes([4, flags]) + (0).to_bytes(2, "big") + _string(client_id)
    if username is not None:
        body += _string(username)
    if password is not None:
        body += _string(password)
    return _packet(CONNECT, body)


def subscribe_packet(packet_id: int, topics: list[str]) -> bytes:
    body = packet_id.to_bytes(2, "big") + b"".join(_string(topic) + b"\x00" for topic in topics)
    return _packet(SUBSCRIBE, body, 0x02)


def publish_packet(topic: str, payload: bytes) -> bytes:
    return _packet(PUBLISH, _string(topic) + payload)


@dataclass
class Packet:
    kind: int
    body: bytes

    def publish(self) -> tuple[str, bytes]:
        size = int.from_bytes(self.body[:2], "big")
        return self.body[2:2 + size].decode("utf-8"), self.body[2 + size:]


def _decode(buffer: bytes) -> tuple[Packet | None, bytes]:
    if len(buffer) < 2:
        return None, buffer
    value, shift, offset = 0, 0, 1
    while True:
        if offset >= len(buffer):
            return None, buffer
        byte = buffer[offset]
        value |= (byte & 0x7F) << shift
        offset += 1
        if not byte & 0x80:
            break
        shift += 7
    if len(buffer) < offset + value:
        return None, buffer
    return Packet(buffer[0] >> 4, buffer[offset:offset + value]), buffer[offset + value:]


# ── one client session ───────────────────────────────────────────────────────────────────


@dataclass
class Session:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    client_id: str
    buffer: bytes = b""
    packet_id: int = 0
    received: list[tuple[str, bytes]] = field(default_factory=list)

    async def next(self, timeout: float) -> Packet | None:
        """The next packet that is not a ping answer, or None when none comes in time."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            packet, self.buffer = _decode(self.buffer)
            if packet is not None:
                if packet.kind == PINGRESP:
                    continue
                if packet.kind == PUBLISH:
                    self.received.append(packet.publish())
                return packet
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            try:
                data = await asyncio.wait_for(self.reader.read(65536), remaining)
            except asyncio.TimeoutError:
                return None
            if not data:
                raise ConnectionError("the broker closed the session")
            self.buffer += data

    async def close(self) -> None:
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, ssl.SSLError, OSError):
            pass


async def run(host: str, port: int, tls: bool, capture: Capture,
              script: tuple[tuple[str, str], ...],
              substitutions: dict[str, tuple[str, ...]], spec: Description,
              screen: Callable[[], dict], values: dict[str, str],
              timeout: float) -> tuple[list[str], list[str]]:
    """Run a replay's script over real sessions; (problems, notes).

    `substitutions` are the profile's, by exchange: a replay keeps its own wherever it runs
    in a script, since what the emulator writes live there is the same whether it is the
    case's subject or a step on the way to another one.
    """
    problems: list[str] = []
    notes: list[str] = []
    sessions: dict[str, Session] = {}

    def received() -> dict[str, list[tuple[str, bytes]]]:
        return {label: list(item.received) for label, item in sessions.items()}

    async def open_session(label: str, step: Step) -> None:
        given = spec.values(label, step, received(), screen())
        context = None
        if tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=context), timeout)
        if label in sessions:
            await sessions[label].close()
        sessions[label] = Session(reader, writer, given["client_id"])
        writer.write(connect_packet(given["client_id"], given.get("username"),
                                    given.get("password")))

    def render(text: str, session: Session, step: Step) -> str:
        text = text.replace(CLIENT_ID, session.client_id)
        if compare.PLACEHOLDER.search(text):
            given = spec.values(label, step, received(), screen())
            for name, value in given.items():
                if value is not None:
                    text = text.replace(f"{{{name}}}", value)
        left = compare.PLACEHOLDER.findall(text)
        if left:
            raise ValueError(f"client-owned {', '.join(left)} left unfilled")
        return text

    try:
        for label, exchange_id in script:
            exchange = capture.exchange(exchange_id)
            masks = substitutions.get(exchange_id, ())
            for index, step in enumerate(exchange.steps):
                where = f"{exchange_id} step {index}"
                packet = step.metadata.get("packet")
                if step.direction == "in":
                    if packet == "CONNECT":
                        await open_session(label, step)
                        continue
                    session = sessions[label]
                    if packet == "SUBSCRIBE":
                        session.packet_id += 1
                        session.writer.write(subscribe_packet(
                            session.packet_id,
                            [render(topic, session, step) for topic in step.metadata["topics"]]))
                    elif packet == "PUBLISH":
                        payload = (step.payload or b"").decode("utf-8")
                        session.writer.write(publish_packet(
                            render(step.metadata["topic"], session, step),
                            render(payload, session, step).encode("utf-8")))
                    elif packet == "DISCONNECT":
                        session.writer.write(_packet(DISCONNECT, b""))
                    else:
                        raise ValueError(f"{where}: no client packet {packet!r}")
                    await session.writer.drain()
                    continue
                session = sessions[label]
                if packet == "none":
                    found = await session.next(QUIET)
                    if found is not None:
                        problems.append(f"{where}: expected nothing, the broker sent "
                                        f"{_describe(found)}")
                    continue
                found = await session.next(timeout)
                if found is None:
                    problems.append(f"{where}: expected {packet}, nothing arrived")
                    return problems, notes
                problems += [f"{where}: {problem}" for problem in
                             _compare(step, found, session, masks + spec.masks.get(
                                 step.operation_id, ()), values, notes, where)]
    except (OSError, ConnectionError, asyncio.TimeoutError) as exc:
        problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        for session in sessions.values():
            await session.close()
    return problems, notes


def _describe(packet: Packet) -> str:
    if packet.kind == PUBLISH:
        topic, payload = packet.publish()
        return f"PUBLISH {topic} {payload[:60]!r}"
    return NAMES.get(packet.kind, f"packet type {packet.kind}")


def _compare(step: Step, found: Packet, session: Session, masks: tuple[str, ...],
             values: dict[str, str], notes: list[str], where: str) -> list[str]:
    packet = step.metadata["packet"]
    if NAMES.get(found.kind) != packet:
        return [f"expected {packet}, observed {_describe(found)}"]
    if packet == "CONNACK":
        code = found.body[1] if len(found.body) > 1 else None
        return [] if code == step.metadata["code"] else [
            f"CONNACK code: expected {step.metadata['code']}, observed {code}"]
    if packet == "SUBACK":
        codes = list(found.body[2:])
        return [] if codes == step.metadata["codes"] else [
            f"SUBACK codes: expected {step.metadata['codes']}, observed {codes}"]
    topic, payload = found.publish()
    problems = []
    expected_topic = step.metadata["topic"].replace(CLIENT_ID, session.client_id)
    if topic != expected_topic:
        problems.append(f"topic: expected {expected_topic!r}, observed {topic!r}")
    outcome = compare.Outcome()
    compare.compare_body(step.payload, payload, masks, values, outcome)
    notes += [f"{where}: {note}" for note in outcome.notes]
    return problems + outcome.problems
