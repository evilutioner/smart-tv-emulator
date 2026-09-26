"""Switching the emulated television, stated without naming one.

Every case here picks its platforms from the registry rather than by name, so the same
file covers a build that ships one television and a build that ships eight. The second
platform is a stub fixture (`tests/extra/stubtv`), which keeps switch machinery under test
in a build with a single real platform and keeps a real device's captured port map from
becoming load-bearing for a rule about switching.
"""
from __future__ import annotations

import json
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from tests.support import (control_protocol, first_platform, install_stub_platform,
                           quiet_protocols, remove_stub_platform, stub_adapter_class,
                           stub_profiles_on)
from tvemu.control import control_app
from tvemu.core import Core, Settings, read_settings, write_settings
from tvemu.platforms import (create_platform, default_platform, platform_choices,
                             platform_descriptor, platform_ids)
from tvemu.runtime import Runtime


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class SettingsResolutionTests(unittest.TestCase):
    def test_saved_platform_is_reported_not_rejected(self):
        # A settings file records whichever platform was active, including one this build
        # no longer ships, so reading it must report the tag rather than reject the file.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            write_settings(path, Settings(device_profile="some-captured-device",
                                          protocols={"ssdp": False}), "another-tv")
            saved_platform, settings = read_settings(path)
            self.assertEqual(saved_platform, "another-tv")
            self.assertEqual(settings.device_profile, "some-captured-device")
            self.assertEqual(settings.protocols, {"ssdp": False})

    def test_missing_file_resolves_to_the_default_platform(self):
        saved_platform, settings = read_settings(Path("/nonexistent/settings.json"))
        self.assertIsNone(saved_platform)
        self.assertEqual(settings, Settings())
        # The default is the first platform the dashboard offers, whatever a build ships.
        self.assertEqual(default_platform(), platform_choices()[0]["id"])
        self.assertIn(default_platform(), platform_ids())

    def test_a_foreign_profile_does_not_survive_a_platform_change(self):
        # What __main__ does when the saved platform is not the platform being started.
        platform_id = default_platform()
        descriptor = platform_descriptor(platform_id)
        core = Core(descriptor, Settings(device_profile="", access_mode=""))
        create_platform(platform_id, core)
        self.assertEqual(core.settings.device_profile, descriptor.default_device_profile)
        self.assertEqual(core.settings.access_mode, descriptor.access_modes[0].id)


class PlatformSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.other = install_stub_platform()
        self.addCleanup(remove_stub_platform)
        self.platform_id = default_platform()
        self.descriptor = platform_descriptor(self.platform_id)
        self.arriving = platform_descriptor(self.other)
        self.core = Core(self.descriptor, Settings())
        self.core.host = "127.0.0.1"
        self.core.service_port = free_port()
        self.runtime = Runtime(self.core, create_platform(self.platform_id, self.core))
        # Discovery needs multicast privileges a test host may not grant. A switch carries
        # no responder over, so both platforms' discovery ids are named here.
        self.core.settings = replace(self.core.settings, protocols={
            **quiet_protocols(self.descriptor), **quiet_protocols(self.arriving)})
        await self.runtime.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.client = TestClient(TestServer(control_app(
            self.runtime, Path(self.temporary.name) / "settings.json", port=8888)))
        await self.client.start_server()
        self.headers = {"Host": "127.0.0.1:8888", "Content-Type": "application/json"}

    async def asyncTearDown(self):
        await self.client.close()
        await self.runtime.close()
        self.temporary.cleanup()

    async def post(self, path, body):
        return await self.client.post(path, headers=self.headers, data=json.dumps(body))

    async def test_switch_replaces_platform_state_ports_and_keys(self):
        departing_key = self.descriptor.keys[0]
        arriving_key = next(key for key in self.arriving.keys
                            if key not in self.descriptor.keys)
        leaving_only = next(key for key in self.descriptor.keys
                            if key not in self.arriving.keys)
        await self.core.key(departing_key, "keypress", "http", "127.0.0.1", "http:test")
        self.assertEqual(self.core.accepted, 1)
        departing_port = self.core.service_port

        response = await self.post("/api/v1/platform", {"platform": self.other})
        self.assertEqual(response.status, 200)
        snapshot = await response.json()

        self.assertEqual(self.core.platform.id, self.other)
        self.assertEqual(snapshot["device"]["platform"], self.other)
        self.assertNotEqual(self.core.service_port, departing_port)
        self.assertEqual(self.core.settings.device_profile,
                         self.arriving.default_device_profile)
        self.assertIn(arriving_key, self.core.keys)
        self.assertNotIn(leaving_only, self.core.keys)
        self.assertEqual(self.core.accepted, 0)
        self.assertEqual(dict(self.core.counts), {})
        self.assertTrue(self.core.service_listening)
        self.assertIn("platform.switched", [event["operation"] for event in self.core.events])

    async def test_the_snapshot_offers_exactly_what_this_build_presents(self):
        snapshot = await (await self.client.get("/api/v1/state",
                                                headers=self.headers)).json()
        self.assertEqual([item["id"] for item in snapshot["platforms"]],
                         [row["id"] for row in platform_choices()])
        self.assertEqual({item["id"] for item in snapshot["platforms"]
                          if item["availability"] == "available"}, set(platform_ids()))

    async def test_a_catalogued_platform_this_build_omits_says_so(self):
        pending = [row for row in platform_choices() if row["availability"] == "n/a"]
        if not pending:
            self.skipTest("this build runs every catalogued platform")
        response = await self.post("/api/v1/platform", {"platform": pending[0]["id"]})
        self.assertEqual(response.status, 501)
        body = await response.json()
        self.assertEqual((body["reason"], body["platform"]), ("n/a", pending[0]["id"]))
        self.assertTrue(body["contact"])
        # The refusal is resolved before any teardown, so nothing stopped serving.
        self.assertEqual(self.core.platform.id, self.platform_id)
        self.assertTrue(self.core.service_listening)

    async def test_switch_back_restores_the_previous_protocol(self):
        control = control_protocol(self.descriptor)
        await self.post("/api/v1/platform", {"platform": self.other})
        self.core.service_port = free_port()
        response = await self.post("/api/v1/platform", {"platform": self.platform_id})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.core.platform.id, self.platform_id)
        self.assertEqual(self.core.settings.device_profile,
                         self.descriptor.default_device_profile)
        self.assertTrue(self.core.service_listening)
        rows = {row["id"]: row for row in self.core.snapshot()["protocols"]}
        self.assertTrue(rows[control]["listening"], rows[control])

    async def test_unknown_platform_is_rejected_and_the_current_one_keeps_serving(self):
        response = await self.post("/api/v1/platform", {"platform": "not-a-platform"})
        self.assertEqual(response.status, 400)
        self.assertIn("not-a-platform", (await response.json())["error"])
        self.assertEqual(self.core.platform.id, self.platform_id)
        self.assertTrue(self.core.service_listening)

        for body in ({}, {"platform": ""}, {"platform": 7}):
            with self.subTest(body=body):
                self.assertEqual((await self.post("/api/v1/platform", body)).status, 400)
        self.assertEqual(self.core.platform.id, self.platform_id)

    async def test_a_switch_leaves_no_text_behind(self):
        typist = first_platform(lambda d: d.keyboard is not None)
        if typist is None:
            self.skipTest("this build ships no platform with a keyboard")
        if typist != self.platform_id:
            await self.runtime.set_platform(typist)
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="typed before the switch")
        self.assertEqual(self.core.text_field.text, "typed before the switch")
        # The stub serves no text input, so the tile disappears rather than keeping a buffer.
        await self.runtime.set_platform(self.other)
        self.assertIsNone(self.core.keyboard_snapshot())
        self.assertEqual(self.core.text_field.text, "")
        self.assertFalse(self.core.text_field.focused)
        self.assertEqual(self.core.content_types, ())

    async def test_every_published_snapshot_is_internally_consistent(self):
        expected = {pid: platform_descriptor(pid)
                    for pid in (self.platform_id, self.other)}
        seen = []
        publish = self.core.publish

        def capture():
            seen.append(self.core.snapshot())
            publish()

        self.core.publish = capture
        try:
            await self.runtime.set_platform(self.other)
        finally:
            self.core.publish = publish

        self.assertTrue(seen, "a switch must publish at least one snapshot")
        for snapshot in seen:
            device = snapshot["device"]
            descriptor = expected[device["platform"]]
            # A snapshot must never pair one platform's descriptor with another's identity.
            self.assertEqual(device["profile"], descriptor.default_device_profile,
                             device["platform"])
            self.assertTrue(device["name"], f"{device['platform']} published with no identity")
            self.assertEqual(set(snapshot["keys"]), set(descriptor.keys), device["platform"])
            keyboard = snapshot["keyboard"]
            if keyboard is None:
                continue
            # The field types are captured per device, so a half-retargeted snapshot could
            # otherwise show a field type the arriving platform never declared.
            declared = {content["id"] for content in keyboard["content_types"]}
            field = keyboard["field"]
            if field["content_type"]:
                self.assertIn(field["content_type"], declared, device["platform"])

    async def test_switching_to_the_active_platform_is_a_no_op(self):
        await self.core.key(self.descriptor.keys[0], "keypress", "http", "127.0.0.1",
                            "http:test")
        response = await self.post("/api/v1/platform", {"platform": self.platform_id})
        self.assertEqual(response.status, 200)
        self.assertEqual(self.core.accepted, 1)

    async def test_a_failed_switch_restores_the_platform_that_was_serving(self):
        departing_port = self.core.service_port
        occupied = socket.socket()
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        taken = occupied.getsockname()[1]
        control = control_protocol(self.descriptor)
        try:
            with patch.object(stub_adapter_class(), "load_profiles",
                              stub_profiles_on(taken)):
                # A primary-protocol bind failure is a ValueError, which the API maps to 400.
                response = await self.post("/api/v1/platform", {"platform": self.other})
                self.assertEqual(response.status, 400)
                self.assertIn("Could not bind", (await response.json())["error"])
        finally:
            occupied.close()
        self.assertEqual(self.core.platform.id, self.platform_id)
        self.assertEqual(self.core.service_port, departing_port)
        self.assertEqual(self.core.settings.device_profile,
                         self.descriptor.default_device_profile)
        self.assertTrue(self.core.service_listening)
        self.assertEqual(self.core.device_profile["id"],
                         self.descriptor.default_device_profile)
        self.assertIn("platform.restored", [event["operation"] for event in self.core.events])
        rows = {row["id"]: row for row in self.core.snapshot()["protocols"]}
        self.assertTrue(rows[control]["listening"])

    async def test_an_access_mode_does_not_survive_a_platform_change(self):
        extra = next((mode for mode in self.descriptor.access_modes[1:]), None)
        if extra is None or len(self.arriving.access_modes) != 1:
            self.skipTest("this build's default platform offers only one access mode")
        response = await self.client.patch("/api/v1/settings", headers=self.headers,
                                           data=json.dumps({"access_mode": extra.id}))
        self.assertEqual(response.status, 200)
        self.assertEqual(self.core.settings.access_mode, extra.id)

        # That mode belongs to the departing platform; the arriving one resolves to its own.
        response = await self.post("/api/v1/platform", {"platform": self.other})
        self.assertEqual(response.status, 200)
        arriving_default = self.arriving.access_modes[0].id
        self.assertEqual(self.core.settings.access_mode, arriving_default)
        self.assertEqual([mode["id"] for mode in (await response.json())["access_modes"]],
                         [arriving_default])
        self.assertEqual((await self.client.patch(
            "/api/v1/settings", headers=self.headers,
            data=json.dumps({"access_mode": extra.id}))).status, 400)

    async def test_saving_records_the_current_platform_without_a_new_setting(self):
        await self.post("/api/v1/platform", {"platform": self.other})
        response = await self.post("/api/v1/settings/save", {})
        self.assertEqual(response.status, 200)
        saved = json.loads(Path((await response.json())["saved"]).read_text())
        self.assertEqual(saved["platform"], self.other)
        self.assertNotIn("platform", saved["settings"])


if __name__ == "__main__":
    unittest.main()
