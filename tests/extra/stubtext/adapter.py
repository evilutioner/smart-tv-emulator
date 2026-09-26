"""A stub television with a text API, a streaming microphone and two launch surfaces."""
from __future__ import annotations

from aiohttp import web

from tvemu.core import Core
from tvemu.platforms.base import (
    ApplicationSpec, ApplicationSurface, ContentType, KeyboardSpec, PlatformDescriptor,
    ProtocolSpec, VoiceSpec,
)
from tvemu.platforms.common import BaseAdapter
from tvemu.platforms.common import profile as common

STUBTEXT = PlatformDescriptor(
    id="stubtext",
    display_name="Stub Text TV",
    # After the other stub, and after every real platform.
    order=9001,
    default_device_profile="stub-text-tv",
    protocol_label="Stub HTTP",
    default_port=0,
    keys=("Home", "Back", "Up", "Down", "Left", "Right", "Select", "Power"),
    transports=("http",),
    limitations="A test fixture. It answers nothing a real television would.",
    protocols=(
        ProtocolSpec("control", "Control", "http", "Accepts remote keys and text over HTTP.",
                     control=True, scheme="http", protocol_label="Stub HTTP",
                     transport="http"),
    ),
    # Whole strings over the wire, so this remote names no delete or submit key.
    keyboard=KeyboardSpec(label="Stub text input", text_api=True),
    voice=VoiceSpec(label="Stub voice input", mode="stream",
                    audio_format="PCM 16-bit mono · 8 kHz"),
    applications=ApplicationSpec(
        label="Stub apps",
        surfaces=(ApplicationSurface("control", "Control"),
                  ApplicationSurface("second", "Second surface"))),
)


class StubTextProfile(common.CapturedProfile):
    def ssdp_location(self, host: str, service_port: int) -> str:
        return f"http://{host}:{service_port}/dd.xml"


def stub_profile(port: int = 0) -> StubTextProfile:
    return StubTextProfile(
        id="stub-text-tv", display_name="Stub Text TV", model_name="Stub", model_number="ST-2",
        serial_number="STUB0000002", udn="uuid:00000000-0000-1000-8000-020000000002",
        software_version="1.0.0", source={"description": "Synthetic test fixture."},
        observed_open_ports=(),
        protocols=(common.ProtocolBinding(id="control", port=port, primary=True),),
        search_target="urn:stub:service:tv:1", ssdp_headers=(), documents={})


class StubTextAdapter(BaseAdapter):
    descriptor = STUBTEXT

    def __init__(self, core: Core):
        super().__init__(core)
        self.profile: StubTextProfile
        self.register_protocol("control", app=self.build_app)
        # One plain field type, the way an adapter publishes what its capture reported.
        core.set_content_types((ContentType("text", "Text"),), "text")

    def build_app(self) -> web.Application:
        app = web.Application()

        async def key(request):
            status, detail = await self.core.key(
                request.match_info["key"], "press", transport="http",
                peer=request.remote or "", source="stub")
            return web.json_response({"detail": detail}, status=status)

        app.add_routes([web.post("/keypress/{key}", key)])
        return app

    def load_profiles(self) -> dict[str, StubTextProfile]:
        return {"stub-text-tv": stub_profile()}

    async def disconnect_clients(self, detail: str | None = None) -> None:
        return None
