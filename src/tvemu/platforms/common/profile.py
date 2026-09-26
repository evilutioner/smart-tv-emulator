"""Shared loading and validation for captured device profiles."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any, Callable, TypeVar

from .ssdp import SSDPAdvertisement
from .evidence import Capture, load_capture


@dataclass(frozen=True)
class ProtocolBinding:
    """One protocol a captured device exposes, with the port it was captured on.

    `port` is 0 for a protocol that answers on a fixed well-known group (SSDP, mDNS).
    `default` overrides the platform's `ProtocolSpec` default for this device only, because
    two sticks of the same platform can ship with different protocols switched on. `warm_up`
    names another protocol whose launch request opens this port: a device may start its
    control API on demand rather than at boot.
    """

    id: str
    port: int = 0
    primary: bool = False
    default: bool | None = None
    warm_up: str = ""


@dataclass(frozen=True)
class CapturedProfile:
    """Identity and wire artifacts captured from one physical device."""

    id: str
    display_name: str
    model_name: str
    model_number: str
    serial_number: str
    udn: str
    software_version: str
    source: dict[str, Any]
    observed_open_ports: tuple[dict[str, Any], ...]
    protocols: tuple[ProtocolBinding, ...]
    search_target: str
    ssdp_headers: tuple[tuple[str, str], ...]
    documents: dict[str, bytes]
    # Evidence is independent of runtime configuration: a profile names the capture whose
    # exchanges it replays. Only the test stubs, which replay nothing, leave it blank.
    capture_id: str = field(default="", kw_only=True)
    runtime_substitutions: dict[str, tuple[str, ...]] = field(default_factory=dict,
                                                               kw_only=True)

    def document(self, name: str) -> bytes | None:
        return self.documents.get(name)

    def binding(self, protocol_id: str) -> ProtocolBinding | None:
        return next((item for item in self.protocols if item.id == protocol_id), None)

    def substitutions_for(self, name: str) -> tuple[str, ...]:
        return self.runtime_substitutions.get(name, ())

    @property
    def primary(self) -> ProtocolBinding:
        return next(item for item in self.protocols if item.primary)

    def ssdp_location(self, host: str, service_port: int) -> str:
        raise NotImplementedError

    def ssdp_advertisements(self, host: str, service_port: int) -> tuple[SSDPAdvertisement, ...]:
        """The search targets this device answers. One stack unless a platform says otherwise."""
        return (SSDPAdvertisement(self.search_target, self.ssdp_headers,
                                  self.ssdp_location(host, service_port)),)

    def summary(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.display_name,
            "model_name": self.model_name,
            "model_number": self.model_number,
            "serial": self.serial_number,
            "udn": self.udn,
            "software_version": self.software_version,
            "source": dict(self.source),
            "observed_open_ports": [dict(item) for item in self.observed_open_ports],
            "captured_routes": sorted(self.documents),
            "protocols": [{"id": item.id, "port": item.port, "primary": item.primary,
                           "default": item.default, "warm_up": item.warm_up}
                          for item in self.protocols],
            "primary_protocol": self.primary.id,
        }
        if self.capture_id:
            result["capture"] = self.capture_id
            result["runtime_substitutions"] = {
                name: list(paths) for name, paths in self.runtime_substitutions.items()
            }
        return result


@dataclass(frozen=True)
class ProfileReference:
    """A schema-v3 profile: the capture it replays and the runtime intent laid over it.

    `replays` maps the names a platform's handlers ask for to exchanges of `capture`.
    `substitutions` lists, per replay name, the only fields a handler may write live.
    `runtime` holds what is emulator-owned rather than measured -- a token, a representative
    application list, a block inherited from a sibling set -- each with its own provenance.
    """

    id: str
    capture: Capture
    replays: dict[str, str]
    substitutions: dict[str, tuple[str, ...]]
    runtime: dict[str, Any]

    def payload(self, name: str) -> bytes:
        return self.capture.payload(self.replays[name])

    def documents(self) -> dict[str, bytes]:
        """Every replay that carries a body, keyed by the name its handler asks for."""
        return {name: step.payload for name, exchange_id in self.replays.items()
                if (step := self.capture.exchange(exchange_id).response()).payload is not None}

    def expect_substitutions(self, expected: dict[str, tuple[str, ...]]) -> None:
        """Refuse a profile whose declared live writes differ from what the handlers do."""
        if self.substitutions != expected:
            raise ValueError(f"Profile {self.id}: runtime substitutions do not match handlers")


# Discovery a capture states instead of evidencing: `none` is an observation (the set was
# searched and answered nothing), `pending` is a gap somebody still has to fill on the set.
DISCOVERY_STATEMENTS = ("none", "pending")


def profile_capture(directory, package: str) -> ProfileReference:
    """Load a schema-v3 profile and the independent capture it replays."""
    data = json.loads(directory.joinpath("profile.json").read_text(encoding="utf-8"))
    profile_id = data.get("id", directory.name) if isinstance(data, dict) else directory.name
    if not isinstance(data, dict) or data.get("schema_version") != 3:
        raise ValueError(f"Profile {profile_id}: schema_version 3 is required")
    if profile_id != directory.name:
        raise ValueError(f"Profile {profile_id}: id must match its directory")
    capture_id = require_string(data, "capture", profile_id)
    replays = data.get("replays")
    if (not isinstance(replays, dict) or not replays
            or not all(isinstance(name, str) and name and isinstance(exchange, str) and exchange
                       for name, exchange in replays.items())):
        raise ValueError(f"Profile {profile_id}: replays must map names to exchanges")
    capture = load_capture(package, capture_id)
    for exchange_id in replays.values():
        capture.exchange(exchange_id).response()
    substitutions = data.get("substitutions", {})
    if (not isinstance(substitutions, dict)
            or not all(name in replays and isinstance(paths, list) and paths
                       and all(isinstance(path, str) and path for path in paths)
                       for name, paths in substitutions.items())):
        raise ValueError(f"Profile {profile_id}: substitutions must name replay fields")
    runtime = data.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError(f"Profile {profile_id}: runtime must be an object")
    # A selectable device needs enough evidence to advertise itself and bind its protocol.
    for name in ("display_name", "model_name", "model_number", "serial_number", "udn",
                 "software_version"):
        require_string(capture.device, name, profile_id)
    protocols = capture.platform.get("protocols")
    if not isinstance(protocols, list) or not protocols:
        raise ValueError(f"Profile {profile_id}: capture has no protocol evidence")
    if not has_discovery_evidence(capture):
        raise ValueError(f"Profile {profile_id}: capture has no discovery evidence")
    return ProfileReference(profile_id, capture, dict(replays),
                            {name: tuple(paths) for name, paths in substitutions.items()},
                            dict(runtime))


def has_discovery_evidence(capture: Capture) -> bool:
    """A discovery protocol was captured, or the capture says why there is none."""
    protocols = capture.platform.get("protocols") or []
    if any(isinstance(item, dict) and item.get("id") in ("ssdp", "mdns", "bonjour")
           for item in protocols):
        return True
    statement = capture.platform.get("discovery")
    if not isinstance(statement, dict) or not isinstance(statement.get("detail"), str) \
            or not statement["detail"]:
        return False
    # TODO(discovery): `pending` is a gap, not an observation. It exists while a capture's
    # discovery answer is still to be recorded off the physical set, as that capture's own
    # `platform.discovery.detail` says. Delete the value once no capture states it.
    return statement.get("status") in DISCOVERY_STATEMENTS


def capture_identity_fields(capture: Capture, profile_id: str) -> dict[str, Any]:
    """CapturedProfile arguments sourced from evidence rather than profile configuration."""
    data = {"id": profile_id, **capture.device, "source": capture.source,
            "observed_open_ports": capture.platform.get("observed_open_ports", []),
            "protocols": capture.platform.get("protocols", [])}
    return identity_fields(data, profile_id)


def optional_dict(data: dict[str, Any], name: str, profile_id: str) -> dict[str, Any] | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Profile {profile_id}: {name} must be an object")
    return value


def parse_protocols(data: dict[str, Any], profile_id: str) -> tuple[ProtocolBinding, ...]:
    """Parse the protocols a captured device exposes, in the order the capture listed them."""
    for removed in ("service", "discovery"):
        if removed in data:
            raise ValueError(f"Profile {profile_id}: {removed!r} was replaced by 'protocols'")
    items = data.get("protocols")
    if not isinstance(items, list) or not items:
        raise ValueError(f"Profile {profile_id}: protocols must be a non-empty list")
    bindings: list[ProtocolBinding] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Profile {profile_id}: invalid protocol entry")
        protocol_id = require_string(item, "id", profile_id)
        if any(binding.id == protocol_id for binding in bindings):
            raise ValueError(f"Profile {profile_id}: duplicate protocol {protocol_id}")
        port = item.get("port", 0)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError(f"Profile {profile_id}: {protocol_id} port must be a valid port")
        for name in ("primary", "default"):
            if name in item and type(item[name]) is not bool:
                raise ValueError(f"Profile {profile_id}: {protocol_id} {name} must be a boolean")
        warm_up = item.get("warm_up", "")
        if not isinstance(warm_up, str):
            raise ValueError(f"Profile {profile_id}: {protocol_id} warm_up must be a string")
        bindings.append(ProtocolBinding(protocol_id, port, bool(item.get("primary", False)),
                                        item.get("default"), warm_up))
    primaries = [binding.id for binding in bindings if binding.primary]
    if len(primaries) != 1:
        raise ValueError(f"Profile {profile_id}: exactly one protocol must be primary; "
                         f"found {len(primaries)}")
    declared = {binding.id for binding in bindings}
    for binding in bindings:
        if binding.warm_up and binding.warm_up not in declared:
            raise ValueError(f"Profile {profile_id}: {binding.id} warms up from "
                             f"{binding.warm_up!r}, which this device does not expose")
    return tuple(bindings)


@dataclass(frozen=True)
class SSDPStack:
    """One SSDP server a captured set runs, replaying the header list it really sent.

    Its `location_protocol` names the bound protocol whose port serves `location_path`.
    """

    id: str
    location_protocol: str
    location_path: str
    udn: str
    search_targets: tuple[str, ...]
    query_aliases: tuple[str, ...]
    response_headers: tuple[tuple[str, str], ...]

    def headers_for(self, target: str) -> tuple[tuple[str, str], ...]:
        """The captured headers for one target; `{location}` and `{date}` stay for the responder."""
        usn = self.udn if target.startswith("uuid:") else f"{self.udn}::{target}"
        return tuple((name, value.replace("{st}", target).replace("{usn}", usn))
                     for name, value in self.response_headers)


def parse_ssdp_stack_headers(items: Any, profile_id: str,
                             stack_id: str) -> tuple[tuple[str, str], ...]:
    """The ordered header list a stack replays; `{st}` and `{usn}` are resolved per target."""
    if not isinstance(items, list) or not items:
        raise ValueError(f"Profile {profile_id}: ssdp stack {stack_id} needs response_headers")
    headers: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Profile {profile_id}: invalid SSDP header in stack {stack_id}")
        name = require_string(item, "name", profile_id)
        value = item.get("value")
        if not isinstance(value, str):
            raise ValueError(f"Profile {profile_id}: SSDP header values must be strings")
        if "{" in value and value not in ("{location}", "{date}", "{st}", "{usn}"):
            raise ValueError(f"Profile {profile_id}: unsupported SSDP placeholder in {name}")
        headers.append((name, value))
    return tuple(headers)


def parse_ssdp_stacks(ssdp: dict[str, Any], bindings: set[str],
                      profile_id: str) -> tuple[SSDPStack, ...]:
    """The SSDP servers a capture measured, or () for a profile using the synthesized default."""
    entries = ssdp.get("stacks")
    if entries is None:
        return ()
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"Profile {profile_id}: ssdp.stacks must be a non-empty list")
    stacks = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Profile {profile_id}: each ssdp stack must be an object")
        stack_id = require_string(entry, "id", profile_id)
        location = require_string(entry, "location_protocol", profile_id)
        if location not in bindings:
            raise ValueError(f"Profile {profile_id}: ssdp stack {stack_id} advertises "
                             f"{location}, which this device does not expose")
        targets = entry.get("search_targets")
        if (not isinstance(targets, list) or not targets
                or not all(isinstance(item, str) and item for item in targets)):
            raise ValueError(f"Profile {profile_id}: ssdp stack {stack_id} needs search_targets")
        aliases = entry.get("query_aliases", [])
        if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
            raise ValueError(f"Profile {profile_id}: invalid query aliases in stack {stack_id}")
        stacks.append(SSDPStack(
            stack_id, location, require_string(entry, "location_path", profile_id),
            require_string(entry, "udn", profile_id), tuple(targets), tuple(aliases),
            parse_ssdp_stack_headers(entry.get("response_headers"), profile_id, stack_id)))
    primary = ssdp.get("primary_stack")
    # The stack whose description a client is meant to fetch is listed first.
    order = sorted(stacks, key=lambda stack: stack.id != primary)
    if primary and order[0].id != primary:
        raise ValueError(f"Profile {profile_id}: primary_stack {primary!r} is not a declared stack")
    return tuple(order)


def parse_txt_records(items: Any, profile_id: str) -> tuple[bytes, ...]:
    if not isinstance(items, list):
        raise ValueError(f"Profile {profile_id}: TXT records must be a list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Profile {profile_id}: invalid TXT record")
        name = require_string(item, "name", profile_id)
        value = item.get("value")
        if "=" in name or not isinstance(value, str):
            raise ValueError(f"Profile {profile_id}: invalid TXT record")
        encoded = f"{name}={value}".encode()
        if len(encoded) > 255:
            raise ValueError(f"Profile {profile_id}: TXT record is too long")
        result.append(encoded)
    return tuple(result)


def parse_properties(value: Any, profile_id: str, *, limit: int = 256) -> dict[str, str]:
    if (not isinstance(value, dict) or len(value) > limit
            or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())):
        raise ValueError(f"Profile {profile_id}: properties must be a string map")
    return dict(value)


def require_string(data: dict[str, Any], name: str, profile_id: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Profile {profile_id}: {name} must be a non-empty string")
    return value


def require_port(data: dict[str, Any], name: str, profile_id: str) -> int:
    value = data.get(name)
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError(f"Profile {profile_id}: {name} must be a valid port")
    return value


def require_captured_source(data: dict[str, Any], profile_id: str) -> dict[str, Any]:
    source = data.get("source")
    if not isinstance(source, dict) or source.get("kind") != "captured":
        raise ValueError(f"Profile {profile_id}: only captured profiles are accepted")
    return dict(source)


def parse_ports(data: dict[str, Any], profile_id: str) -> tuple[dict[str, Any], ...]:
    ports = data.get("observed_open_ports", [])
    if not isinstance(ports, list) or not all(isinstance(item, dict) for item in ports):
        raise ValueError(f"Profile {profile_id}: observed_open_ports must be a list")
    return tuple(dict(item) for item in ports)


def parse_ssdp_headers(items: Any, profile_id: str,
                       source_name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(items, list):
        raise ValueError(f"Profile {profile_id}: {source_name} must be a list")
    headers: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Profile {profile_id}: invalid SSDP header")
        name = require_string(item, "name", profile_id)
        value = item.get("value")
        if not isinstance(value, str):
            raise ValueError(f"Profile {profile_id}: SSDP header values must be strings")
        if "{" in value and value not in ("{location}", "{date}"):
            raise ValueError(f"Profile {profile_id}: unsupported SSDP placeholder in {name}")
        headers.append((name, value))
    return tuple(headers)


def identity_fields(data: dict[str, Any], profile_id: str) -> dict[str, Any]:
    """The `CapturedProfile` identity arguments every platform parses the same way."""
    return {
        "id": require_string(data, "id", profile_id),
        "display_name": require_string(data, "display_name", profile_id),
        "model_name": require_string(data, "model_name", profile_id),
        "model_number": require_string(data, "model_number", profile_id),
        "serial_number": require_string(data, "serial_number", profile_id),
        "udn": require_string(data, "udn", profile_id),
        "software_version": require_string(data, "software_version", profile_id),
        "source": require_captured_source(data, profile_id),
        "observed_open_ports": parse_ports(data, profile_id),
        "protocols": parse_protocols(data, profile_id),
    }


P = TypeVar("P", bound=CapturedProfile)


def load_profiles(package: str, loader: Callable[[Any], P], label: str) -> dict[str, P]:
    root = files(package).joinpath("profiles")
    profiles: dict[str, P] = {}
    for directory in sorted((item for item in root.iterdir() if item.is_dir()),
                            key=lambda item: item.name):
        profile = loader(directory)
        if profile.id in profiles:
            raise ValueError(f"Duplicate {label} profile id: {profile.id}")
        profiles[profile.id] = profile
    if not profiles:
        raise ValueError(f"No captured {label} device profiles are installed")
    return profiles
