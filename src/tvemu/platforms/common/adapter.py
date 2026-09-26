"""Adapter behaviour that is identical for every platform."""
from __future__ import annotations

import asyncio
import ssl
from dataclasses import replace

from aiohttp import web

from tvemu.core import Core
from tvemu.platforms.base import DISCOVERY_KINDS, PlatformDescriptor, ProtocolListener

from .profile import CapturedProfile


class BaseAdapter:
    """Profile selection, listener bookkeeping, and per-protocol lifecycle.

    A subclass supplies `descriptor`, loads its profiles, builds its protocol objects in
    `__init__` (after `super().__init__`), and registers one `ProtocolListener` per
    `ProtocolSpec` the descriptor declares. Everything else is shared: which protocols are
    switched on, which ports they take, and how one is started or stopped without touching
    the rest.
    """

    descriptor: PlatformDescriptor
    profile_switch_detail: str = ""

    def __init__(self, core: Core):
        self.core = core
        self.profiles = self.load_profiles()
        selected = core.settings.device_profile or self.descriptor.default_device_profile
        if selected not in self.profiles:
            raise ValueError(self._unknown_profile(selected))
        self.profile: CapturedProfile = self.profiles[selected]
        mode = core.settings.access_mode or self.descriptor.access_modes[0].id
        if mode not in {option.id for option in self.descriptor.access_modes}:
            raise ValueError(self._unknown_access_mode(mode))
        self.specs = {spec.id: spec for spec in self.descriptor.protocols}
        for profile in self.profiles.values():
            # Catch a profile that names a protocol this platform cannot serve at
            # construction, rather than at the first bind attempt.
            unknown = {binding.id for binding in profile.protocols} - set(self.specs)
            if unknown:
                raise ValueError(f"Profile {profile.id} declares protocols "
                                 f"{self.descriptor.display_name} does not offer: "
                                 f"{', '.join(sorted(unknown))}")
        self.core.settings = replace(self.core.settings, device_profile=selected,
                                     access_mode=mode)
        self.runners: dict[str, web.AppRunner] = {}
        self.sites: dict[str, web.TCPSite] = {}
        self.servers: dict[str, asyncio.AbstractServer] = {}
        self.listeners: dict[str, ProtocolListener] = {}
        self.active: set[str] = set()
        # Protocols a device starts on demand stay closed until their trigger arrives.
        self.warmed: set[str] = set()
        self.errors: dict[str, str] = {}
        self.publish_profile()

    # ── profiles ───────────────────────────────────────────────────────────────────────

    def load_profiles(self) -> dict[str, CapturedProfile]:
        raise NotImplementedError

    def _unknown_profile(self, profile_id: str) -> str:
        choices = ", ".join(self.profiles)
        return (f"Unknown {self.descriptor.display_name} device profile {profile_id!r}; "
                f"available: {choices}")

    def _unknown_access_mode(self, mode_id: str) -> str:
        choices = ", ".join(option.id for option in self.descriptor.access_modes)
        return (f"Unknown {self.descriptor.display_name} access mode {mode_id!r}; "
                f"available: {choices}")

    def publish_profile(self) -> None:
        if not self.core.service_port_pinned:
            self.core.service_port = self.profile_port()
        self.core.set_device_profile(
            self.profile.summary(), [profile.summary() for profile in self.profiles.values()]
        )
        self.publish_protocols()

    def profile_port(self) -> int:
        primary = self.profile.primary
        return primary.port or self.descriptor.default_port

    def profile_ids(self) -> tuple[str, ...]:
        return tuple(self.profiles)

    async def select_profile(self, profile_id: str) -> None:
        try:
            profile = self.profiles[profile_id]
        except KeyError as exc:
            raise ValueError(self._unknown_profile(profile_id)) from exc
        if profile is self.profile:
            return
        # A new identity moves every captured port, so nothing may stay bound across it.
        await self.stop_all()
        await self.disconnect_clients(self.profile_switch_detail or None)
        self.profile = profile
        # A new identity invalidates every warm-up the previous device had granted.
        self.warmed.clear()
        self.errors.clear()
        self.publish_profile()
        self.core.reset("State reset for captured device profile switch")

    # ── protocol declaration and state ─────────────────────────────────────────────────

    def register_protocol(self, protocol_id: str, **listener) -> None:
        if protocol_id not in self.specs:
            raise ValueError(f"{self.descriptor.display_name} declares no protocol "
                             f"{protocol_id!r}")
        self.listeners[protocol_id] = ProtocolListener(**listener)

    def protocol_enabled(self, protocol_id: str) -> bool:
        """The on/off state in force: the saved setting, else the device's or platform's default."""
        binding = self.profile.binding(protocol_id)
        if binding is None:
            return False
        spec = self.specs[protocol_id]
        fallback = spec.default if binding.default is None else binding.default
        return self.core.settings.protocols.get(protocol_id, fallback)

    def protocol_armed(self, protocol_id: str) -> bool:
        """Whether an enabled protocol is still waiting for the request that opens it."""
        binding = self.profile.binding(protocol_id)
        return bool(binding and binding.warm_up) and protocol_id not in self.warmed

    def protocol_wanted(self, protocol_id: str) -> bool:
        if protocol_id not in self.listeners or not self.protocol_enabled(protocol_id):
            return False
        if self.protocol_armed(protocol_id):
            return False
        # A platform's access mode may take the device off the network entirely.
        if self.specs[protocol_id].kind in DISCOVERY_KINDS:
            return self.core.access.discoverable
        return True

    def protocol_port(self, protocol_id: str) -> int:
        binding = self.profile.binding(protocol_id)
        if binding is None:
            return 0
        # `--port` and the launch override pin the primary protocol only.
        return self.core.service_port if binding.primary else binding.port

    def protocol_advertised_ports(self, protocol_id: str) -> tuple[int, ...]:
        """Ports named by a discovery row; platforms may publish more than one."""
        port = self.protocol_port(protocol_id)
        return (port,) if port else ()

    def surface(self):
        """The declared surface of this platform, or None for one that declares nothing.

        Every television overrides this. Only the test stubs keep the default, and they return
        None rather than an empty surface: "declares no surface" and "declares no routes" are
        different answers, and a report must not print the second for the first.
        """
        return None

    def publish_protocols(self) -> None:
        """Hand the dashboard one row per protocol the active device exposes."""
        rows = []
        for spec in self.descriptor.protocols:
            binding = self.profile.binding(spec.id)
            if binding is None:
                continue
            rows.append({
                "id": spec.id, "label": spec.label, "kind": spec.kind, "summary": spec.summary,
                "control": spec.control, "primary": binding.primary,
                "protocol_label": spec.protocol_label, "scheme": spec.scheme or spec.kind,
                "port": self.protocol_port(spec.id),
                "advertised_ports": list(self.protocol_advertised_ports(spec.id)),
                "enabled": self.protocol_enabled(spec.id),
                "listening": spec.id in self.active,
                "armed": self.protocol_enabled(spec.id) and self.protocol_armed(spec.id),
                "error": self.errors.get(spec.id),
            })
        self.core.set_protocols(rows)

    # ── protocol lifecycle ─────────────────────────────────────────────────────────────

    async def start_protocol(self, protocol_id: str) -> None:
        """Bind one protocol. An OSError leaves the others exactly as they were."""
        if protocol_id in self.active:
            return
        listener = self.listeners[protocol_id]
        host, port = self.core.host, self.protocol_port(protocol_id)
        if listener.responder is not None:
            await listener.responder.start()
        elif listener.app is not None:
            context = listener.ssl_context() if listener.ssl_context else None
            await self._start_app(protocol_id, listener.app(), host, port, context)
        else:
            context = listener.ssl_context() if listener.ssl_context else None
            await self._start_server(protocol_id, listener.connected, host, port, context)
        self.active.add(protocol_id)
        self.errors.pop(protocol_id, None)
        # Republish before recording, so the event's own snapshot already shows the new state.
        self.publish_protocols()
        self.core.record("protocol", f"protocol.{protocol_id}.started",
                         detail=self._where(protocol_id))

    async def stop_protocol(self, protocol_id: str) -> None:
        """Release one protocol, dropping only the sessions that belong to it."""
        if protocol_id not in self.active:
            return
        listener = self.listeners[protocol_id]
        self.active.discard(protocol_id)
        if listener.responder is not None:
            await listener.responder.stop()
        else:
            # Stop accepting first, so no client connects while existing ones are torn down.
            server = self.servers.get(protocol_id)
            site = self.sites.get(protocol_id)
            if server is not None:
                server.close()
            if site is not None:
                await site.stop()
            if listener.disconnect is not None:
                await listener.disconnect()
            if server is not None:
                await server.wait_closed()
                self.servers.pop(protocol_id, None)
            runner = self.runners.pop(protocol_id, None)
            self.sites.pop(protocol_id, None)
            if runner is not None:
                await runner.cleanup()
        self.publish_protocols()
        self.core.record("protocol", f"protocol.{protocol_id}.stopped")

    async def reconcile_protocols(self) -> dict[str, str]:
        """Bring the listeners in line with the settings, one protocol at a time."""
        failures: dict[str, str] = {}
        for protocol_id in sorted(self.active):
            if not self.protocol_wanted(protocol_id):
                await self.stop_protocol(protocol_id)
        self.errors = {key: value for key, value in self.errors.items()
                       if self.protocol_wanted(key)}
        for spec in self.descriptor.protocols:
            if spec.id in self.active or not self.protocol_wanted(spec.id):
                continue
            try:
                await self.start_protocol(spec.id)
            except OSError as exc:
                failures[spec.id] = str(exc)
                self.errors[spec.id] = str(exc)
                self.core.record("protocol", f"protocol.{spec.id}.error", detail=str(exc))
        self.publish_protocols()
        return failures

    async def warm_up(self, protocol_id: str) -> None:
        """Open a protocol the captured device starts on demand. Safe to call repeatedly."""
        if protocol_id not in self.listeners or not self.protocol_armed(protocol_id):
            return
        if not self.protocol_enabled(protocol_id):
            return
        self.warmed.add(protocol_id)
        try:
            await self.start_protocol(protocol_id)
        except OSError as exc:
            self.errors[protocol_id] = str(exc)
            self.core.record("protocol", f"protocol.{protocol_id}.error", detail=str(exc))
        self.publish_protocols()

    async def stop_all(self) -> None:
        for protocol_id in sorted(self.active):
            await self.stop_protocol(protocol_id)
        self.warmed.clear()
        self.publish_protocols()

    def _where(self, protocol_id: str) -> str:
        spec = self.specs[protocol_id]
        if spec.kind in DISCOVERY_KINDS:
            return f"{spec.label} · captured profile: {self.profile.id}"
        return f"{self.core.host}:{self.protocol_port(protocol_id)}"

    # ── listener bookkeeping ───────────────────────────────────────────────────────────

    async def _start_app(self, name: str, app: web.Application, host: str, port: int,
                         ssl_context: ssl.SSLContext | None = None) -> None:
        runner = web.AppRunner(app, shutdown_timeout=1)
        await runner.setup()
        site = web.TCPSite(runner, host, port, ssl_context=ssl_context)
        try:
            await site.start()
        except BaseException:
            await runner.cleanup()
            raise
        self.runners[name] = runner
        self.sites[name] = site

    async def _start_server(self, name: str, client_connected, host: str, port: int,
                            ssl_context: ssl.SSLContext | None = None) -> None:
        self.servers[name] = await asyncio.start_server(
            client_connected, host, port, ssl=ssl_context,
        )

    # ── clients ────────────────────────────────────────────────────────────────────────

    async def disconnect_clients(self, detail: str | None = None) -> None:
        raise NotImplementedError

    async def disconnect(self) -> None:
        await self.disconnect_clients()

    async def action(self, name: str, data: dict) -> None:
        raise web.HTTPNotFound()
