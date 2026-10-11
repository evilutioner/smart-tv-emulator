"""Roku platform adapter lifecycle."""
from __future__ import annotations

from tvemu.core import Core
from tvemu.platforms.base import (
    AccessMode, ApplicationSpec, ApplicationSurface, KeyboardSpec, PlatformDescriptor,
    ProtocolSpec,
)
from tvemu.platforms.common import BaseAdapter, SSDPResponder

from .ecp import ECP
from .profile import RokuProfile, load_profiles

ROKU_KEYS = (
    "Home", "Back", "Up", "Down", "Left", "Right", "Select", "Info",
    "VolumeUp", "VolumeDown", "VolumeMute", "Power", "PowerOn", "PowerOff",
    "ChannelUp", "ChannelDown", "Rev", "Play", "Fwd", "InstantReplay",
    "Search", "Enter", "Backspace", "FindRemote", "InputTuner", "InputHDMI1",
    "InputHDMI2", "InputHDMI3", "InputHDMI4", "InputAV1",
)

# Settings › System › Advanced system settings › Control by mobile apps › Network access.
# Roku exposes four values; the emulator reproduces the wire behaviour of each one.
ROKU_ACCESS_MODES = (
    AccessMode(
        id="enabled",
        label="Enabled — apps on this network",
        summary=("Default network access: ECP answers clients on the TV's own network and "
                 "refuses the rest."),
        status_label="Service available",
        off_subnet_status=403,
    ),
    AccessMode(
        id="permissive",
        label="Permissive — apps on any network",
        summary="ECP answers clients on any network, including other subnets.",
        status_label="Permissive",
        off_subnet_status=0,
    ),
    AccessMode(
        id="limited",
        label="Limited — authenticated apps only",
        summary=("Only an authenticated ecp-2 session may press keys or ask about channels "
                 "and playback. Plain HTTP ECP refuses keys and every query except "
                 "device-info and active-app; the device documents and discovery keep "
                 "working."),
        status_label="Limited",
        badge="neutral",
        control_statuses=(("http", 403), ("ws", 200)),
        query_statuses=(("http", 403), ("ws", 200)),
        off_subnet_status=403,
        detail="Rejected by Limited network access: an authenticated session is required",
        refusal_body="ECP command not allowed in Limited mode.",
    ),
    AccessMode(
        id="disabled",
        label="Disabled — no plain HTTP control",
        summary=("Plain HTTP ECP refuses every command with 401 and no body, before reading "
                 "it. The device documents, discovery and an authenticated ecp-2 session "
                 "keep working, as a TCL on 15.3.4 did."),
        status_label="HTTP control disabled",
        badge="bad",
        control_statuses=(("http", 401), ("ws", 200)),
        command_statuses=(("http", 401),),
        off_subnet_status=403,
        detail="Rejected by Disabled network access: only an authenticated session is served",
    ),
)

ROKU_PROTOCOLS = (
    ProtocolSpec("ecp", "ECP", "http",
                 "External Control Protocol over HTTP, plus the authenticated ecp-2 WebSocket.",
                 control=True, scheme="http", protocol_label="ECP / ecp-2", transport="http"),
    ProtocolSpec("ssdp", "SSDP", "ssdp",
                 "Answers roku:ecp M-SEARCH probes on 239.255.255.250:1900."),
)

ROKU = PlatformDescriptor(
    id="roku",
    display_name="Roku",
    order=10,
    default_device_profile="tcl-roku-tv-32s357",
    protocol_label="ECP / ecp-2",
    default_port=8060,
    keys=ROKU_KEYS,
    transports=("http", "ws"),
    limitations=(
        "The selected identity and discovery documents come from a physical capture. "
        "Only information endpoints present in that selected capture are served, and the "
        "channel list and foreground channel are the captured ones rather than live state. "
        "ECP channel launches are accepted and observed, but no Cast, playback, or rendered "
        "screen is emulated."
    ),
    service_scheme="http",
    discovery_label="SSDP roku:ecp",
    access_modes=ROKU_ACCESS_MODES,
    protocols=ROKU_PROTOCOLS,
    # ECP sends text as one Lit_<char> keypress at a time and has no keyboard-status API, so
    # the set never reports a field type and the dashboard offers no selector.
    keyboard=KeyboardSpec(label="On-screen keyboard", literal_prefix="Lit_",
                          delete_key="Backspace", enter_key="Enter"),
    # ECP ignores case in every key name: hardware answers `home`, `HOME`, `Lit_a` and
    # `LIT_a` alike. It matters because the reference driver spells the prefix `LIT_`.
    fold_key_case=True,
    # A TCL on 15.3.4 answered 202 for releasing a key nobody pressed, over HTTP and ecp-2.
    unheld_release_status=202,
    applications=ApplicationSpec(
        label="Roku channels",
        surfaces=(ApplicationSurface("ecp", "ECP"),),
    ),
)


class RokuAdapter(BaseAdapter):
    descriptor = ROKU

    def __init__(self, core: Core):
        super().__init__(core)
        self.profile: RokuProfile
        self.ecp = ECP(core, lambda: self.profile)
        self.register_protocol("ecp", app=self.ecp.app, disconnect=self.ecp.disconnect)
        self.register_protocol("ssdp", responder=SSDPResponder(core, lambda: self.profile,
                                                               event_prefix="ssdp"))

    def surface(self):
        return self.ecp.surface()

    def load_profiles(self) -> dict[str, RokuProfile]:
        return load_profiles()

    async def disconnect_clients(self, detail: str | None = None) -> None:
        await self.ecp.disconnect(detail)
