"""Choosing platforms by declared capability, so one test file fits any platform set.

A cross-cutting test must state a rule about the emulator, not about a television that
happens to be in the build running it. Everything here answers "which platform can do X"
from descriptor data, so the same file passes whether the build ships one platform or
eight, and `needs()` skips a case the build has no platform for.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path

from tvemu.platforms import platform_descriptor, platform_ids
from tvemu.platforms.common import mdns
from tvemu.platforms.common import profile as common


# Test-only platforms. They sort after every real one, so they are never a build's default
# and are only ever selected by a capability no shipped television has.
STUB_IDS = ("stubtv", "stubtext")


def install_fixtures() -> None:
    """Register the stub platforms, once, for the lifetime of the test process.

    They are registered at import rather than per test so the capability constants below
    can see them: a build whose one television types with per-character keypresses would
    otherwise skip every rule about the shared text API, which it still ships.
    """
    import tvemu.platforms as registry

    extra = str(Path(__file__).parent / "extra")
    if extra not in registry.__path__:
        registry.__path__.append(extra)
        registry._registry.cache_clear()
    missing = [stub for stub in STUB_IDS if registry._only is not None
               and stub not in registry._only]
    if missing:
        # A build preview restricts the registry to that build's platforms. These are
        # scaffolding rather than televisions, so they stay available regardless.
        registry.restrict_to({*registry._only, *missing})


install_fixtures()


def first_platform(predicate) -> str | None:
    """The first platform in display order whose descriptor satisfies `predicate`."""
    return next((pid for pid in platform_ids() if predicate(platform_descriptor(pid))), None)


def needs(platform_id: str | None, what: str) -> str:
    """`platform_id`, or skip the test when this build ships no platform with `what`."""
    if platform_id is None:
        raise unittest.SkipTest(f"this build ships no platform with {what}")
    return platform_id


NO_KEYBOARD = first_platform(lambda d: d.keyboard is None)
# A platform with no keyboard whose own wire still produces text keys, so the refusal
# is out of scope rather than unknown.
TEXT_KEY_PREFIXES = first_platform(lambda d: d.keyboard is None and d.text_key_prefixes)
TEXT_API = first_platform(lambda d: d.keyboard is not None and d.keyboard.text_api)
LITERAL_KEYS = first_platform(lambda d: d.keyboard is not None and d.keyboard.literal_prefix)
VOICE_STREAM = first_platform(lambda d: d.voice is not None and d.voice.mode == "stream")
NO_VOICE = first_platform(lambda d: d.voice is None)
MULTI_MODE = first_platform(lambda d: len(d.access_modes) > 1)


def closed_access_mode(platform_id: str):
    """A mode of this platform whose own data refuses remote control, or None."""
    descriptor = platform_descriptor(platform_id)
    return next((mode for mode in descriptor.access_modes
                 if mode.control_status >= 400
                 or any(status >= 400 for _, status in mode.control_statuses)), None)


@dataclass(frozen=True)
class StubMDNSProfile(common.CapturedProfile):
    """A captured profile that advertises over mDNS, built rather than loaded.

    `common/mdns.py` is shared code, so its encoding is tested against a synthetic device.
    That keeps the coverage in a build whose platforms happen not to use mDNS, and stops
    one platform's capture from being load-bearing for a shared codec.
    """

    bonjour: dict = field(default_factory=dict)

    def ssdp_location(self, host: str, service_port: int) -> str:
        return f"http://{host}:{service_port}/dd.xml"

    @property
    def mdns_service_type(self) -> tuple[bytes, ...]:
        return tuple(item.encode() for item in self.bonjour["service_type"])

    @property
    def mdns_instance(self) -> bytes:
        return self.bonjour["instance"].encode()

    @property
    def mdns_port(self) -> int:
        return self.bonjour["port"]

    @property
    def mdns_txt(self) -> tuple[bytes, ...]:
        return self.bonjour["txt"]

    def mdns_target(self, host: str) -> str:
        return host.replace(".", "-") + ".local"

    def mdns_advertisements(self, host: str, service_port: int
                            ) -> tuple[mdns.MDNSAdvertisement, ...]:
        return (mdns.MDNSAdvertisement(self.mdns_service_type, self.mdns_instance,
                                       self.mdns_target(host), self.mdns_port, self.mdns_txt),)


def mdns_profile() -> StubMDNSProfile:
    """A device whose instance name contains a dot, which is the interesting case."""
    return StubMDNSProfile(
        id="stub-mdns-tv", display_name="Stub TV", model_name="Stub", model_number="ST-1",
        serial_number="STUB0000001", udn="uuid:00000000-0000-1000-8000-020000000001",
        software_version="1.0.0", source={}, observed_open_ports=(),
        protocols=(common.ProtocolBinding(id="control", port=8080, primary=True),
                   common.ProtocolBinding(id="bonjour", port=0)),
        search_target="urn:stub:service:tv:1", ssdp_headers=(), documents={},
        bonjour={"instance": "Stub TV.local-1", "service_type": ("_stub-tv._tcp", "local"),
                 "port": 39187, "txt": (b"v=1", b"m=ST-1")})


def install_stub_platform() -> str:
    """The id of the minimal stub platform, for a test that needs a second television.

    Switching between platforms is shared machinery, so it must stay under test in a build
    that ships a single television. `install_fixtures` already registered it.
    """
    install_fixtures()
    return "stubtv"


def remove_stub_platform() -> None:
    """Kept so a test can pair it with `install_stub_platform` in `addCleanup`.

    The fixtures stay registered for the whole process; unregistering between tests would
    invalidate the capability constants computed at import.
    """
    return None


def discovery_protocols(descriptor) -> tuple[str, ...]:
    """Protocol ids that answer on a multicast group rather than a bound port."""
    from tvemu.platforms.base import DISCOVERY_KINDS

    return tuple(spec.id for spec in descriptor.protocols if spec.kind in DISCOVERY_KINDS)


def quiet_protocols(descriptor) -> dict[str, bool]:
    """Every discovery protocol switched off.

    Multicast privileges are not guaranteed on a test host, so responders stay off. Built
    from the descriptor rather than written out, because which ids exist is platform data.
    """
    return {protocol_id: False for protocol_id in discovery_protocols(descriptor)}


def control_protocol(descriptor) -> str | None:
    """The protocol over which remote keys arrive, or None if the platform declares none."""
    return next((spec.id for spec in descriptor.protocols if spec.control), None)


def stub_profiles_on(port: int):
    """A `load_profiles` replacement that pins the stub platform to `port`.

    Patched over `StubTVAdapter.load_profiles` to make a switch fail on a port a test has
    already taken, which is how "a failed switch restores the platform that was serving"
    is exercised without depending on any real device's captured port map.
    """
    def load_profiles(self=None):
        from tvemu.platforms.stubtv.adapter import stub_profile

        return {"stub-tv": stub_profile(port)}
    return load_profiles


def stub_adapter_class():
    """The stub's adapter class, importable only once the stub is installed."""
    from tvemu.platforms.stubtv.adapter import StubTVAdapter

    return StubTVAdapter


def undeclared_live_paths(claims, body: bytes, captured: bytes | None,
                          content_type: str = "application/json"
                          ) -> tuple[frozenset[str], frozenset[str]]:
    """Where a served body and its claims disagree about what the emulator writes live.

    Every path the emulator adds to a replayed capture is claimed with `scope="served"`,
    because a driver reading the capture alone would never see it. Two sets come back, and
    either being non-empty is a fault: paths served but claimed nowhere, and claims of a live
    field the body no longer carries.
    """
    from tvemu.platforms.common.evidence import EvidenceRef
    from tvemu.platforms.common.ir import parse_payload, paths_of

    probe = EvidenceRef("probe", detail="a live response")

    def paths(raw: bytes | None) -> frozenset[str]:
        return frozenset(paths_of(parse_payload(raw, content_type, probe))) if raw else frozenset()

    added = paths(body) - paths(captured)
    declared = frozenset(claim.path for claim in claims.claims
                         if getattr(claim, "scope", "") == "served")
    under = lambda path, name: path == name or path.startswith(f"{name}.")  # noqa: E731
    honoured = frozenset(name for name in declared if any(under(path, name) for path in added))
    undeclared = frozenset(path for path in added
                           if not any(under(path, name) for name in declared))
    return undeclared, declared - honoured
