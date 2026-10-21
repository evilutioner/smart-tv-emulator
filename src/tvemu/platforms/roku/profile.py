"""Captured Roku device profiles and their wire-level artifacts."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from tvemu.platforms.common import profile as common


# What the handlers write live into a replayed document, by replay name: the set reports its
# own network-access value in device-info, so the emulator reports the selected mode.
# Each replay that carries device-info, with the path prefix that reaches inside it: over
# ecp-2 the document is base64 in the envelope's content-data.
DEVICE_INFO = {"/query/device-info": "", "query-device-info": "content-data::"}
LIVE = ("ecp-setting-mode",)
# Device-info fields whose value per state of the set is device data. A profile writes one
# live only where its `runtime` gives the measured value for every state: a stick in standby
# has not been measured, so its power-mode stays the captured one.
STATES = {"power-mode": ("on", "standby")}


def _live_states(runtime: dict, profile_id: str) -> dict[str, dict[str, str]]:
    states = {}
    for field, names in STATES.items():
        declared = runtime.get(field)
        if declared is None:
            continue
        if (not isinstance(declared, dict) or not isinstance(declared.get("source"), str)
                or not all(isinstance(declared.get(name), str) for name in names)):
            raise ValueError(f"Profile {profile_id}: runtime {field} needs "
                             f"{', '.join(names)} and a source")
        states[field] = {name: declared[name] for name in names}
    return states


@dataclass(frozen=True)
class RokuProfile(common.CapturedProfile):
    """Roku serves captured HTTP documents keyed by request path.

    A replay named by an ecp-2 request instead (`query-apps`) is a document the set carried
    inside its envelope, kept apart because the two wires do not always carry the same bytes.
    """

    # Per route, the Content-Type the set wrote (parameters and quoting included) and the
    # other headers it sent with the document. `Server` is not among them: the set puts it
    # on every reply, so the ECP surface writes it once for all of them.
    http_content_types: dict[str, str]
    http_headers: dict[str, tuple[tuple[str, str], ...]]
    # A route the set answered with something other than 200 -- a stick's 404 for the tuner
    # queries -- replays that status with the captured (empty) body.
    http_statuses: dict[str, int]
    ecp2_documents: dict[str, tuple[bytes, str]]
    # Per device-info field the profile writes from the set's state, the value per state.
    live_states: dict[str, dict[str, str]]
    ecp2_statuses: dict[str, int]
    notifications: dict[str, dict]
    runtime: dict
    native_text_document: bytes | None
    native_text_notifications: dict[str, dict]

    @property
    def server(self) -> str:
        for name, value in self.ssdp_headers:
            if name.lower() == "server":
                return value
        raise ValueError(f"Profile {self.id} has no SSDP Server header")

    def ssdp_location(self, host: str, service_port: int) -> str:
        return f"http://{host}:{service_port}/"

    def document_content_type(self, route: str, default: str = "text/xml") -> str:
        return self.http_content_types.get(route, default)

    def document_headers(self, route: str) -> dict[str, str]:
        return dict(self.http_headers.get(route, ()))

    def document_status(self, route: str) -> int:
        return self.http_statuses.get(route, 200)


def _envelope_document(capture, exchange_id: str, profile_id: str) -> tuple[bytes | None, str]:
    frame = json.loads(capture.payload(exchange_id))
    data, content_type = frame.get("content-data"), frame.get("content-type")
    if data is None and content_type is None:
        return None, ""
    if not isinstance(data, str) or not isinstance(content_type, str):
        raise ValueError(f"Profile {profile_id}: {exchange_id} carries no ecp-2 document")
    return base64.b64decode(data, validate=True), content_type


def _load_profile(directory) -> RokuProfile:
    reference = common.profile_capture(directory, __package__)
    profile_id, capture, replay = reference.id, reference.capture, reference.replays
    live_states = _live_states(reference.runtime, profile_id)
    expected = {
        name: tuple(prefix + field for field in (*LIVE, *live_states))
        for name, prefix in DEVICE_INFO.items()}
    for name in reference.replays:
        if name.startswith("notify."):
            expected[name] = ("timestamp", "param-channel-id", "param-channel-title")
    audio_state = reference.runtime.get("audio", {}).get("query_state")
    if audio_state:
        for name, prefix in (("/query/audio-device", ""), ("query-audio-device", "content-data::")):
            expected[name] = tuple(prefix + field for field in audio_state["fields"])
    if reference.runtime.get("textedit", {}).get("native"):
        expected["query-textedit-state"] = ("content-data::textedit-state",)
    reference.expect_substitutions(expected)
    ssdp = capture.platform.get("ssdp")
    if not isinstance(ssdp, dict):
        raise ValueError(f"Profile {profile_id}: ssdp.response_headers must be a list")
    headers = common.parse_ssdp_headers(ssdp.get("response_headers"), profile_id,
                                        "ssdp.response_headers")

    if "/" not in replay:
        raise ValueError(f"Profile {profile_id}: replays must include /")
    documents: dict[str, bytes] = {}
    ecp2_documents: dict[str, tuple[bytes, str]] = {}
    ecp2_statuses: dict[str, int] = {}
    notifications: dict[str, dict] = {}
    for name, exchange_id in replay.items():
        transport = capture.exchange(exchange_id).transport
        if name.startswith("/") and transport == "http":
            documents[name] = capture.payload(exchange_id)
        elif name.startswith("notify.") and transport == "websocket":
            event = name.removeprefix("notify.")
            candidates = [json.loads(step.payload) for step in capture.exchange(exchange_id).outputs()
                          if step.operation_id == "ecp-2." + event]
            if len(candidates) != 1:
                raise ValueError(f"Profile {profile_id}: {name} needs one captured notification")
            notifications[event] = candidates[0]
        elif transport == "websocket":
            ecp2_documents[name] = _envelope_document(capture, exchange_id, profile_id)
            ecp2_statuses[name] = int(json.loads(capture.payload(exchange_id))["status"])
        else:
            raise ValueError(f"Profile {profile_id}: {name} cannot replay {exchange_id}")
    content_types: dict[str, str] = {}
    http_headers: dict[str, tuple[tuple[str, str], ...]] = {}
    http_statuses: dict[str, int] = {}
    for route, exchange_id in replay.items():
        if route not in documents:
            continue
        answer = capture.exchange(exchange_id).response().metadata
        if answer["status"] != 200:
            http_statuses[route] = answer["status"]
        kept = []
        for name, value in answer["headers"].items():
            if name.lower() == "content-type":
                content_types[route] = value
            elif name.lower() != "server":
                kept.append((name, value))
        http_headers[route] = tuple(kept)

    native = reference.runtime.get("textedit", {}).get("native")
    native_document, native_notifications = None, {}
    if native:
        template = native["query_template"]
        raw = capture.exchange(template["exchange"]).steps[template["step"]].payload
        native_document = base64.b64decode(json.loads(raw)["content-data"], validate=True)
        for event, template in native["notification_templates"].items():
            raw = capture.exchange(template["exchange"]).steps[template["step"]].payload
            payload = json.loads(raw)
            if payload.get("notify") != event:
                raise ValueError(f"Profile {profile_id}: wrong native notification template")
            native_notifications[event] = payload

    return RokuProfile(
        **common.capture_identity_fields(capture, profile_id),
        search_target=common.require_string(ssdp, "search_target", profile_id),
        ssdp_headers=headers,
        documents=documents,
        capture_id=capture.id, label=reference.label,
        runtime_substitutions=reference.substitutions,
        http_content_types=content_types,
        http_headers=http_headers,
        http_statuses=http_statuses,
        ecp2_documents=ecp2_documents,
        live_states=live_states,
        ecp2_statuses=ecp2_statuses,
        notifications=notifications,
        runtime=reference.runtime,
        native_text_document=native_document,
        native_text_notifications=native_notifications,
    )


def load_profiles() -> dict[str, RokuProfile]:
    return common.load_profiles(__package__, _load_profile, "Roku")
