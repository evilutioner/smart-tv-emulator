"""Captured Roku device profiles and their wire-level artifacts."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from tvemu.platforms.common import profile as common


@dataclass(frozen=True)
class RokuProfile(common.CapturedProfile):
    """Roku serves captured HTTP documents keyed by request path.

    A replay named by an ecp-2 request instead (`query-apps`) is a document the set carried
    inside its envelope, kept apart because the two wires do not always carry the same bytes.
    """

    http_content_types: dict[str, str]
    ecp2_documents: dict[str, tuple[bytes, str]]

    @property
    def server(self) -> str:
        for name, value in self.ssdp_headers:
            if name.lower() == "server":
                return value
        raise ValueError(f"Profile {self.id} has no SSDP Server header")

    def ssdp_location(self, host: str, service_port: int) -> str:
        return f"http://{host}:{service_port}/"

    def document_content_type(self, route: str) -> str:
        return self.http_content_types.get(route, "text/xml")


def _envelope_document(capture, exchange_id: str, profile_id: str) -> tuple[bytes, str]:
    frame = json.loads(capture.payload(exchange_id))
    data, content_type = frame.get("content-data"), frame.get("content-type")
    if not isinstance(data, str) or not isinstance(content_type, str):
        raise ValueError(f"Profile {profile_id}: {exchange_id} carries no ecp-2 document")
    return base64.b64decode(data, validate=True), content_type


def _load_profile(directory) -> RokuProfile:
    reference = common.profile_capture(directory, __package__)
    profile_id, capture, replay = reference.id, reference.capture, reference.replays
    if reference.substitutions:
        raise ValueError(f"Profile {profile_id}: Roku replays allow no runtime substitutions")
    ssdp = capture.platform.get("ssdp")
    if not isinstance(ssdp, dict):
        raise ValueError(f"Profile {profile_id}: ssdp.response_headers must be a list")
    headers = common.parse_ssdp_headers(ssdp.get("response_headers"), profile_id,
                                        "ssdp.response_headers")

    if "/" not in replay:
        raise ValueError(f"Profile {profile_id}: replays must include /")
    documents: dict[str, bytes] = {}
    ecp2_documents: dict[str, tuple[bytes, str]] = {}
    for name, exchange_id in replay.items():
        transport = capture.exchange(exchange_id).transport
        if name.startswith("/") and transport == "http":
            documents[name] = capture.payload(exchange_id)
        elif name.startswith("query-") and transport == "websocket":
            ecp2_documents[name] = _envelope_document(capture, exchange_id, profile_id)
        else:
            raise ValueError(f"Profile {profile_id}: {name} cannot replay {exchange_id}")
    content_types = {route: capture.content_type(exchange_id)
                     for route, exchange_id in replay.items()
                     if route in documents and capture.content_type(exchange_id)}

    return RokuProfile(
        **common.capture_identity_fields(capture, profile_id),
        search_target=common.require_string(ssdp, "search_target", profile_id),
        ssdp_headers=headers,
        documents=documents,
        capture_id=capture.id,
        runtime_substitutions=reference.substitutions,
        http_content_types=dict(content_types),
        ecp2_documents=ecp2_documents,
    )


def load_profiles() -> dict[str, RokuProfile]:
    return common.load_profiles(__package__, _load_profile, "Roku")
