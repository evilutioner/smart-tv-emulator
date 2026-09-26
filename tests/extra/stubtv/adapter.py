"""The smallest adapter that satisfies the platform contract."""
from __future__ import annotations

from aiohttp import web

from tvemu.core import Core
from tvemu.platforms.base import (
    ApplicationSpec, ApplicationSurface, PlatformDescriptor, ProtocolSpec,
)
from tvemu.platforms.common import BaseAdapter
from tvemu.platforms.common import profile as common

# "StubOnly" exists so a switch test can name a key that arrives with this platform
# and leaves with it, without borrowing a real remote's button.
STUB_KEYS = ("Home", "Back", "Up", "Down", "Left", "Right", "Select", "Power",
             "StubOnly")

STUBTV = PlatformDescriptor(
    id="stubtv",
    display_name="Stub TV",
    # Last, always: a build under test must never find its default platform here.
    order=9000,
    default_device_profile="stub-tv",
    protocol_label="Stub HTTP",
    default_port=0,          # an ephemeral port, so the stub never fights a real listener
    keys=STUB_KEYS,
    transports=("http",),
    limitations="A test fixture. It answers nothing a real television would.",
    protocols=(
        ProtocolSpec("control", "Control", "http", "Accepts remote keys over HTTP.",
                     control=True, scheme="http", protocol_label="Stub HTTP",
                     transport="http"),
    ),
    applications=ApplicationSpec(label="Stub apps",
                                 surfaces=(ApplicationSurface("control", "Control"),)),
)


class StubProfile(common.CapturedProfile):
    def ssdp_location(self, host: str, service_port: int) -> str:
        return f"http://{host}:{service_port}/dd.xml"


def stub_profile(port: int = 0) -> StubProfile:
    """The stub's captured device. `port` pins the control protocol, which is how a test
    arranges a switch that cannot bind; 0 keeps the ephemeral port used everywhere else."""
    return StubProfile(
        id="stub-tv", display_name="Stub TV", model_name="Stub", model_number="ST-1",
        serial_number="STUB0000001", udn="uuid:00000000-0000-1000-8000-020000000001",
        software_version="1.0.0", source={"description": "Synthetic test fixture."},
        observed_open_ports=(),
        protocols=(common.ProtocolBinding(id="control", port=port, primary=True),),
        search_target="urn:stub:service:tv:1", ssdp_headers=(), documents={})


class StubTVAdapter(BaseAdapter):
    descriptor = STUBTV

    def __init__(self, core: Core):
        super().__init__(core)
        self.profile: StubProfile
        self.register_protocol("control", app=self.build_app)

    def build_app(self) -> web.Application:
        app = web.Application()

        async def key(request):
            status, detail = await self.core.key(
                request.match_info["key"], "press", transport="http",
                peer=request.remote or "", source="stub")
            return web.json_response({"detail": detail}, status=status)

        app.add_routes([web.post("/keypress/{key}", key)])
        return app

    def load_profiles(self) -> dict[str, StubProfile]:
        return {"stub-tv": stub_profile()}

    async def disconnect_clients(self, detail: str | None = None) -> None:
        return None
