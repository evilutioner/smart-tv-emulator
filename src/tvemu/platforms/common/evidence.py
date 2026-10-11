"""Immutable observations captured from physical televisions.

A capture is evidence, not an emulated device.  Profiles may reference a complete capture,
while an incomplete capture remains useful to the contract without becoming selectable in
the dashboard.  Every exchange keeps the ordered wire steps and the original payload bytes;
the contract parsers inspect those bytes, and the emulator replays them unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


@dataclass(frozen=True)
class EvidenceRef:
    """A claim's precise source."""

    kind: str                 # capture | probe | client-contract
    capture: str = ""
    exchange: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in ("capture", "probe", "client-contract"):
            raise ValueError(f"Unknown evidence kind: {self.kind}")
        if self.kind == "capture" and (not self.capture or not self.exchange):
            raise ValueError("Capture evidence names both a capture and an exchange")
        if self.kind != "capture" and not self.detail:
            raise ValueError(f"{self.kind} evidence needs a source detail")


@dataclass(frozen=True)
class Step:
    """One ordered frame in an exchange."""

    direction: str            # in | out, from the emulator's point of view
    metadata: dict[str, Any]
    payload_name: str = ""
    payload: bytes | None = None
    # One exchange can contain different message operations in each direction (for example
    # a WebSocket request and its response). HTTP usually inherits the exchange operation.
    operation_id: str = ""

    def __post_init__(self) -> None:
        if self.direction not in ("in", "out"):
            raise ValueError("An evidence step direction must be in or out")


@dataclass(frozen=True)
class Exchange:
    id: str
    operation_id: str
    transport: str
    steps: tuple[Step, ...]

    def outputs(self) -> tuple[Step, ...]:
        return tuple(step for step in self.steps if step.direction == "out")

    def response(self) -> Step:
        outputs = self.outputs()
        if len(outputs) != 1:
            raise ValueError(f"{self.id}: a replay exchange needs exactly one output step")
        return outputs[0]


@dataclass(frozen=True)
class Capture:
    """One immutable observation session against one physical television."""

    id: str
    device: dict[str, Any]
    source: dict[str, Any]
    platform: dict[str, Any]
    exchanges: dict[str, Exchange]

    def exchange(self, exchange_id: str) -> Exchange:
        try:
            return self.exchanges[exchange_id]
        except KeyError as exc:
            raise ValueError(f"Capture {self.id}: unknown exchange {exchange_id!r}") from exc

    def payload(self, exchange_id: str) -> bytes:
        step = self.exchange(exchange_id).response()
        if step.payload is None:
            raise ValueError(f"Capture {self.id}: {exchange_id} has no response payload")
        return step.payload

    def content_type(self, exchange_id: str) -> str:
        headers = self.exchange(exchange_id).response().metadata.get("headers", {})
        if not isinstance(headers, dict):
            return ""
        return next((str(value).partition(";")[0].strip()
                     for name, value in headers.items()
                     if str(name).lower() == "content-type"), "")


def load_captures(package: str) -> dict[str, Capture]:
    root = files(package).joinpath("evidence")
    if not root.is_dir():
        return {}
    result: dict[str, Capture] = {}
    for directory in sorted((item for item in root.iterdir() if item.is_dir()),
                            key=lambda item: item.name):
        capture = _load_capture(directory)
        if capture.id in result:
            raise ValueError(f"Duplicate capture id: {capture.id}")
        result[capture.id] = capture
    return result


def load_capture(package: str, capture_id: str) -> Capture:
    captures = load_captures(package)
    try:
        return captures[capture_id]
    except KeyError as exc:
        raise ValueError(f"{package}: unknown capture {capture_id!r}") from exc


def _load_capture(directory) -> Capture:
    manifest = directory.joinpath("capture.json")
    if not manifest.is_file():
        raise ValueError(f"Capture {directory.name}: capture.json is missing")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    capture_id = data.get("id", directory.name) if isinstance(data, dict) else directory.name
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"Capture {capture_id}: unsupported schema_version")
    if capture_id != directory.name:
        raise ValueError(f"Capture {capture_id}: id must match its directory")
    device = data.get("device")
    source = data.get("source")
    platform = data.get("platform", {})
    rows = data.get("exchanges")
    if not isinstance(device, dict) or not device:
        raise ValueError(f"Capture {capture_id}: device must be a non-empty object")
    if not isinstance(source, dict) or not source.get("kind"):
        raise ValueError(f"Capture {capture_id}: source provenance is required")
    if not isinstance(platform, dict):
        raise ValueError(f"Capture {capture_id}: platform must be an object")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Capture {capture_id}: exchanges must be a non-empty list")
    exchanges: dict[str, Exchange] = {}
    for row in rows:
        exchange = _load_exchange(directory, capture_id, row)
        if exchange.id in exchanges:
            raise ValueError(f"Capture {capture_id}: duplicate exchange {exchange.id}")
        exchanges[exchange.id] = exchange
    return Capture(capture_id, dict(device), dict(source), dict(platform), exchanges)


def _load_exchange(directory, capture_id: str, row: Any) -> Exchange:
    if not isinstance(row, dict):
        raise ValueError(f"Capture {capture_id}: an exchange must be an object")
    exchange_id = _required_string(row, "id", capture_id)
    operation_id = _required_string(row, "operation_id", capture_id)
    transport = _required_string(row, "transport", capture_id)
    rows = row.get("steps")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Capture {capture_id}: {exchange_id} needs ordered steps")
    steps = []
    for number, item in enumerate(rows):
        if not isinstance(item, dict):
            raise ValueError(f"Capture {capture_id}: {exchange_id} step {number} is invalid")
        direction = _required_string(item, "direction", capture_id)
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"Capture {capture_id}: {exchange_id} metadata must be an object")
        _validate_metadata(capture_id, exchange_id, transport, direction, metadata)
        payload_name = item.get("payload", "")
        if not isinstance(payload_name, str) or "/" in payload_name or "\\" in payload_name:
            raise ValueError(f"Capture {capture_id}: {exchange_id} has an invalid payload path")
        payload = directory.joinpath(payload_name).read_bytes() if payload_name else None
        step_operation = item.get("operation_id", "")
        if not isinstance(step_operation, str):
            raise ValueError(f"Capture {capture_id}: {exchange_id} operation_id must be a string")
        steps.append(Step(direction, dict(metadata), payload_name, payload, step_operation))
    return Exchange(exchange_id, operation_id, transport, tuple(steps))


def _required_string(data: dict[str, Any], name: str, owner: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Capture {owner}: {name} must be a non-empty string")
    return value


def _validate_metadata(capture_id: str, exchange_id: str, transport: str,
                       direction: str, metadata: dict[str, Any]) -> None:
    owner = f"Capture {capture_id}: {exchange_id}"
    if transport in ("http", "https") and direction == "in":
        if not isinstance(metadata.get("method"), str) or not isinstance(metadata.get("path"), str):
            raise ValueError(f"{owner} HTTP input needs method and path")
    if transport in ("http", "https") and direction == "out":
        status = metadata.get("status")
        headers = metadata.get("headers")
        if type(status) is not int or not 100 <= status <= 599:
            raise ValueError(f"{owner} HTTP output needs a valid status")
        if (not isinstance(headers, dict)
                or not all(isinstance(name, str) and isinstance(value, str)
                           for name, value in headers.items())):
            raise ValueError(f"{owner} HTTP output headers must be a string map")
