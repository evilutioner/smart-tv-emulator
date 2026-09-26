"""The dashboard document is declared, and the declaration is checked against a live one.

`src/tvemu/view.py` says what `/api/v1/state` contains. Nothing used to: the shape was a dict
literal in `core.py` and `app.js` read it by convention, so a field renamed on one side became
`undefined` on the other with nothing to notice. These cases walk a real snapshot of every
platform the build ships against the declaration, in both directions.
"""
from __future__ import annotations

import unittest

import support  # noqa: F401  -- registers the stub platforms

from tvemu.core import Core
from tvemu.platforms import create_platform, platform_descriptor, platform_ids
from tvemu import view


def snapshots():
    """One live snapshot per platform, with its adapter attached as at startup."""
    for platform_id in platform_ids():
        core = Core(platform_descriptor(platform_id))
        adapter = create_platform(platform_id, core)
        adapter.publish_profile()
        adapter.publish_protocols()
        yield platform_id, core.snapshot()


class DashboardContractTests(unittest.TestCase):
    def test_every_field_a_snapshot_carries_is_declared(self):
        for platform_id, snapshot in snapshots():
            with self.subTest(platform=platform_id):
                self.assertEqual(sorted(set(snapshot) - set(view.FIELDS)), [])

    def test_every_declared_field_is_actually_carried(self):
        """A declaration nobody emits is as misleading as a field nobody declared."""
        for platform_id, snapshot in snapshots():
            with self.subTest(platform=platform_id):
                self.assertEqual(sorted(set(view.FIELDS) - set(snapshot)), [])

    def test_every_field_carries_the_type_it_declares(self):
        for platform_id, snapshot in snapshots():
            for name, value in snapshot.items():
                with self.subTest(platform=platform_id, field=name):
                    self.assertTrue(view.conforms(name, value),
                                    f"{name} is {view.json_type(value)}, "
                                    f"not {view.FIELDS[name][0]}")

    def test_the_declared_row_members_are_the_ones_a_row_has(self):
        """The blocks the dashboard reads by name, so a rename cannot pass unnoticed."""
        for platform_id, snapshot in snapshots():
            for name, members in view.ROW_FIELDS.items():
                value = snapshot[name]
                rows = value if isinstance(value, list) else [value]
                for row in rows:
                    with self.subTest(platform=platform_id, block=name):
                        self.assertEqual(sorted(set(members) - set(row)), [])

    def test_the_schema_version_is_the_one_the_snapshot_reports(self):
        for platform_id, snapshot in snapshots():
            with self.subTest(platform=platform_id):
                self.assertEqual(snapshot["schema_version"], view.SCHEMA_VERSION)

    def test_the_published_document_describes_every_route_the_api_serves(self):
        paths = set(view.openapi()["paths"])
        self.assertIn("/api/v1/state", paths)
        self.assertIn("/api/v1/openapi.json", paths)
        self.assertEqual(view.openapi()["components"]["schemas"]["Snapshot"]["required"],
                         sorted(view.FIELDS))


if __name__ == "__main__":
    unittest.main()
