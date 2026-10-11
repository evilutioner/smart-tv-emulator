"""Coordinate a platform lifecycle while keeping the control plane available."""
from __future__ import annotations

import asyncio
from dataclasses import replace

from .core import Core, Settings
from .platforms import create_platform, platform_descriptor
from .platforms.base import PlatformAdapter


class Runtime:
    def __init__(self, core: Core, platform: PlatformAdapter):
        self.core = core
        self.platform = platform
        self.lock = asyncio.Lock()

    async def apply_protocols(self) -> dict[str, str]:
        """Bring the listeners in line with the settings.

        Only the primary protocol's failure is fatal: it carries the address the emulator
        advertises, so a lab that cannot bind it has nothing to test against. Any other
        protocol that will not bind is reported in its own row while the rest keep serving.
        """
        failures = await self.platform.reconcile_protocols()
        primary = self.core.device_profile.get("primary_protocol", "")
        if primary in failures:
            raise ValueError(
                f"Could not bind {self.core.platform.display_name} at "
                f"{self.core.host}:{self.core.service_port}: {failures[primary]}"
            )
        return failures

    async def start(self):
        await self.apply_protocols()

    async def configure(self, changes):
        async with self.lock:
            settings = Settings.parse(changes, self.core.settings)
            profile_id = settings.device_profile or self.core.platform.default_device_profile
            if profile_id not in self.platform.profile_ids():
                choices = ", ".join(self.platform.profile_ids())
                raise ValueError(f"Unknown device profile {profile_id!r}; available: {choices}")
            modes = self.core.platform.access_modes
            mode_id = settings.access_mode or modes[0].id
            if mode_id not in {mode.id for mode in modes}:
                choices = ", ".join(mode.id for mode in modes)
                raise ValueError(f"Unknown access mode {mode_id!r} for "
                                 f"{self.core.platform.display_name}; available: {choices}")
            # Only the switches this patch actually moves are checked against the active
            # platform. A protocol another platform declares stays in the map untouched: ids
            # such as `ssdp` mean the same thing everywhere, and one this platform does not
            # expose simply never starts.
            known = {spec.id for spec in self.core.platform.protocols}
            changing = {key for key, value in settings.protocols.items()
                        if self.core.settings.protocols.get(key) != value}
            unknown = changing - known
            if unknown:
                raise ValueError(f"Unknown protocols: {', '.join(sorted(unknown))}")
            settings = replace(settings, device_profile=profile_id, access_mode=mode_id)
            profile_changed = profile_id != self.core.settings.device_profile
            previous_settings = self.core.settings
            previous_profile = previous_settings.device_profile
            self.core.settings = settings
            try:
                # Selecting a captured identity releases every listener first, because the
                # ports move with it; a protocol switch alone only moves that one protocol.
                if profile_changed:
                    await self.platform.select_profile(profile_id)
                await self.apply_protocols()
            except (OSError, ValueError):
                self.core.settings = previous_settings
                if profile_changed:
                    await self.platform.select_profile(previous_profile)
                await self.apply_protocols()
                raise
            self.core.record("settings", "settings.updated", detail=str(changes))

    async def set_platform(self, platform_id: str) -> None:
        """Emulate a different TV without restarting the process."""
        async with self.lock:
            if platform_id == self.core.platform.id:
                return
            descriptor = platform_descriptor(platform_id)  # Unknown id fails before any teardown.
            leaving, adapter = self.core.platform, self.platform
            settings, service_port = self.core.settings, self.core.service_port
            service_port_pinned = self.core.service_port_pinned
            await self.close()
            self.core.retarget(descriptor)
            # The captured device and the access mode belong to the platform being left, so
            # the new adapter resolves both to its own defaults. The protocol switches stay:
            # a protocol id names the same wire protocol on every platform, and one the new
            # platform does not expose is simply never started.
            self.core.settings = replace(self.core.settings, device_profile="", access_mode="")
            arriving = None
            try:
                self.platform = arriving = create_platform(platform_id, self.core)
                self.core.record("platform", "platform.switched",
                                 detail=f"{leaving.display_name} → {descriptor.display_name}")
                await self.start()
            except (OSError, ValueError):
                # A partial start must not leave the abandoned platform holding ports the
                # restored one, or the next attempt, needs.
                if arriving is not None:
                    await arriving.stop_all()
                # Restore the platform that was serving, including a pinned launch port.
                self.core.platform, self.platform = leaving, adapter
                self.core.settings, self.core.service_port = settings, service_port
                self.core.service_port_pinned = service_port_pinned
                self.platform.publish_profile()
                self.core.record("platform", "platform.restored",
                                 detail=f"Switch to {descriptor.display_name} failed")
                await self.start()
                raise

    async def close(self):
        await self.platform.stop_all()
