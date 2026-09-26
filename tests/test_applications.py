from __future__ import annotations

import unittest
from pathlib import Path

from tvemu.core import Core, MAX_APPLICATION_PAYLOAD
from tvemu.platforms import default_platform, platform_descriptor, platform_ids
from tests.support import STUB_IDS
from tvemu.platforms.catalogue import catalogue_ids


class ApplicationStateTests(unittest.TestCase):
    """Launch bookkeeping, stated about the emulator rather than about one television."""

    def setUp(self):
        self.descriptor = platform_descriptor(default_platform())

    def test_every_platform_this_build_ships_declares_native_launch_surfaces(self):
        self.assertTrue(platform_ids(), "a build must ship at least one platform")
        for platform_id in platform_ids():
            with self.subTest(platform=platform_id):
                spec = platform_descriptor(platform_id).applications
                self.assertIsNotNone(spec)
                self.assertTrue(spec.surfaces)

    def test_every_platform_this_build_ships_is_catalogued(self):
        # The catalogue is what names a platform the build cannot run, so a shipped
        # platform missing from it would be invisible to any other build. Test fixtures
        # are not televisions and are deliberately absent from it.
        self.assertLessEqual(set(platform_ids()) - set(STUB_IDS), set(catalogue_ids()))

    def test_an_oversized_payload_is_truncated_and_says_so(self):
        core = Core(self.descriptor)
        surface = self.descriptor.applications.surfaces[0].id
        core.application_launch("com.example.dynamic", surface=surface, transport="test",
                                payload="x" * (MAX_APPLICATION_PAYLOAD + 20), status=200)
        launch = core.snapshot()["applications"]["last_launch"]
        self.assertEqual(len(launch["payload"]), MAX_APPLICATION_PAYLOAD)
        self.assertTrue(launch["payload_truncated"])

    def test_the_same_native_id_on_two_surfaces_stays_two_observations(self):
        descriptor = platform_descriptor(
            next((pid for pid in platform_ids()
                  if len(platform_descriptor(pid).applications.surfaces) > 1),
                 default_platform()))
        surfaces = [surface.id for surface in descriptor.applications.surfaces]
        if len(surfaces) < 2:
            self.skipTest("this build ships no platform with two launch surfaces")
        core = Core(descriptor)
        for surface in surfaces[:2]:
            core.application_launch("com.example.dynamic", surface=surface, transport="test")
        keys = {item["key"] for item in core.snapshot()["applications"]["items"]}
        for surface in surfaces[:2]:
            self.assertIn(f"{surface}:com.example.dynamic", keys)

    def test_reset_clears_the_last_launch_and_the_observed_cards(self):
        core = Core(self.descriptor)
        surface = self.descriptor.applications.surfaces[0].id
        core.application_launch("com.example.dynamic", surface=surface, transport="test")
        self.assertIsNotNone(core.snapshot()["applications"]["last_launch"])
        core.reset()
        reset = core.snapshot()["applications"]
        self.assertIsNone(reset["last_launch"])
        self.assertNotIn("com.example.dynamic", {item["id"] for item in reset["items"]})

    def test_rejected_attempt_is_kept_for_the_red_ui_state(self):
        core = Core(self.descriptor)
        surface = self.descriptor.applications.surfaces[0].id
        core.application_launch("", surface=surface, transport="test", status=400,
                                detail="Missing package")
        launch = core.snapshot()["applications"]["last_launch"]
        self.assertEqual(launch["status"], 400)
        self.assertEqual(launch["id"], "(missing app id)")

    def test_dashboard_contains_generic_launch_tile(self):
        web = Path(__file__).parents[1] / "src/tvemu/web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="applications-card" hidden', html)
        self.assertIn("function drawApplications(data)", script)
        self.assertIn('data-filter="application"', html)


if __name__ == "__main__":
    unittest.main()
