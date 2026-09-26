"""Each protocol switches on its own, and one that will not bind never takes down the rest."""
from __future__ import annotations

import json
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aiohttp import ClientSession, TCPConnector
from aiohttp.test_utils import TestClient, TestServer

from tvemu.control import control_app
from tvemu.core import Core, Settings, parse_settings_document
from tests.support import control_protocol, quiet_protocols
from tvemu.platforms import create_platform, default_platform, platform_descriptor
from tvemu.platforms.common import profile as common
from tvemu.runtime import Runtime

# A protocol id no platform declares, for the cases about refusing one.
FOREIGN = "not-a-protocol"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def rows(core: Core) -> dict[str, dict]:
    return {row["id"]: row for row in core.snapshot()["protocols"]}


class SettingsTests(unittest.TestCase):
    def test_a_partial_patch_moves_only_the_protocols_it_names(self):
        base = Settings(protocols={"ssdp": False, "adb": True})
        merged = Settings.parse({"protocols": {"adb": False}}, base)
        self.assertEqual(merged.protocols, {"ssdp": False, "adb": False})

    def test_malformed_protocol_maps_are_rejected(self):
        for value in ({"Turnstile": True}, {"-adb": True}, {"adb": "yes"}, {"adb": 1},
                      {f"p{index}": True for index in range(33)}, []):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "protocols must map protocol ids to booleans"
            ):
                Settings.parse({"protocols": value})

    def test_hyphenated_ids_are_accepted(self):
        self.assertEqual(Settings.parse({"protocols": {"dial-description": False}}).protocols,
                         {"dial-description": False})

    def test_a_settings_file_from_the_previous_schema_is_refused(self):
        with self.assertRaisesRegex(ValueError, "schema_version=2 is required"):
            parse_settings_document({"schema_version": 1, "settings": {}})


class ProfileParsingTests(unittest.TestCase):
    BASE = {"protocols": [{"id": "ecp", "primary": True, "port": 8060}, {"id": "ssdp"}]}

    def test_exactly_one_protocol_must_be_primary(self):
        for protocols in ([{"id": "ecp"}],
                          [{"id": "ecp", "primary": True}, {"id": "ssdp", "primary": True}]):
            with self.subTest(protocols=protocols), self.assertRaisesRegex(
                ValueError, "exactly one protocol must be primary"
            ):
                common.parse_protocols({"protocols": protocols}, "p")

    def test_the_replaced_keys_name_their_successor(self):
        for removed in ("service", "discovery"):
            with self.subTest(removed=removed), self.assertRaisesRegex(
                ValueError, f"{removed!r} was replaced by 'protocols'"
            ):
                common.parse_protocols({removed: {}, **self.BASE}, "p")

    def test_a_warm_up_must_name_a_protocol_the_device_exposes(self):
        data = {"protocols": [{"id": "ecp", "primary": True, "warm_up": "dial"}]}
        with self.assertRaisesRegex(ValueError, "which this device does not expose"):
            common.parse_protocols(data, "p")

    def test_duplicate_and_malformed_entries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate protocol ssdp"):
            common.parse_protocols({"protocols": [{"id": "ssdp", "primary": True},
                                                  {"id": "ssdp"}]}, "p")
        with self.assertRaisesRegex(ValueError, "port must be a valid port"):
            common.parse_protocols({"protocols": [{"id": "ecp", "primary": True,
                                                   "port": 70000}]}, "p")

class ProtocolAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.platform_id = default_platform()
        self.descriptor = platform_descriptor(self.platform_id)
        self.control = control_protocol(self.descriptor)
        # Multicast privileges are not guaranteed on a test host, so responders stay off.
        self.quiet = quiet_protocols(self.descriptor)
        self.core = Core(self.descriptor, Settings(protocols={**self.quiet, FOREIGN: False}))
        self.core.host = "127.0.0.1"
        self.core.service_port = free_port()
        self.runtime = Runtime(self.core, create_platform(self.platform_id, self.core))
        await self.runtime.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "settings.json"
        self.client = TestClient(TestServer(control_app(self.runtime, self.path, port=8888)))
        await self.client.start_server()
        self.headers = {"Host": "127.0.0.1:8888", "Content-Type": "application/json"}

    async def asyncTearDown(self):
        await self.client.close()
        await self.runtime.close()
        self.temporary.cleanup()

    async def patch(self, body):
        return await self.client.patch("/api/v1/settings", headers=self.headers,
                                       data=json.dumps(body))

    async def test_a_protocol_this_platform_does_not_declare_is_refused(self):
        response = await self.patch({"protocols": {FOREIGN: True}})
        self.assertEqual(response.status, 400)
        self.assertIn(f"Unknown protocols: {FOREIGN}", (await response.json())["error"])

    async def test_a_carried_over_protocol_from_another_platform_is_left_alone(self):
        # The protocol map survives a platform switch, so it can name a protocol this
        # platform does not have. Such an entry must neither start nor block a patch.
        self.assertEqual(self.core.settings.protocols[FOREIGN], False)
        response = await self.patch({"protocols": {self.control: False}})
        self.assertEqual(response.status, 200)
        self.assertNotIn(FOREIGN, [row["id"] for row in (await response.json())["protocols"]])
        self.assertFalse(self.core.service_listening)

    async def test_switching_a_protocol_is_saved_and_restored(self):
        await self.patch({"protocols": {self.control: False}})
        response = await self.client.post("/api/v1/settings/save", headers=self.headers,
                                          data="{}")
        self.assertEqual(response.status, 200)
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["schema_version"], 2)
        self.assertEqual(saved["settings"]["protocols"][self.control], False)


if __name__ == "__main__":
    unittest.main()
