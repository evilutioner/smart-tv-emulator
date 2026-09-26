"""A scenario check reads the event log the way a driver test would assert on it."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tvemu import expect

EVENTS = [
    {"id": 1, "kind": "pairing", "operation": "pairing.accepted", "status": 200},
    {"id": 2, "kind": "command", "operation": "keypress/Home", "status": 200},
    {"id": 3, "kind": "command", "operation": "keypress/Back", "status": 403,
     "detail": "limited mode"},
    {"id": 4, "kind": "command", "operation": "launch/12", "status": 200},
]


class MatchTests(unittest.TestCase):
    def test_every_named_field_must_be_equal(self):
        self.assertTrue(expect.matches(EVENTS[1], {"operation": "keypress/Home", "status": 200}))
        self.assertFalse(expect.matches(EVENTS[1], {"operation": "keypress/Home", "status": 403}))

    def test_a_trailing_star_is_a_prefix(self):
        self.assertTrue(expect.matches(EVENTS[3], {"operation": "launch/*"}))
        self.assertFalse(expect.matches(EVENTS[3], {"operation": "keypress/*"}))

    def test_a_field_the_event_lacks_never_matches(self):
        self.assertFalse(expect.matches(EVENTS[0], {"detail": "*"}))


class CheckTests(unittest.TestCase):
    def test_an_ordered_scenario_is_a_subsequence(self):
        scenario = {"expect": [{"operation": "pairing.*"}, {"operation": "launch/12"}]}
        self.assertEqual(expect.check(EVENTS, scenario), [])

    def test_order_is_enforced_unless_turned_off(self):
        scenario = {"expect": [{"operation": "launch/12"}, {"operation": "keypress/Home"}]}
        problems = expect.check(EVENTS, scenario)
        self.assertEqual(len(problems), 1)
        self.assertIn("expectation 2", problems[0])
        self.assertEqual(expect.check(EVENTS, {**scenario, "ordered": False}), [])

    def test_a_forbidden_event_fails_and_is_named(self):
        problems = expect.check(EVENTS, {"expect": [], "forbid": [{"status": 403}]})
        self.assertEqual(len(problems), 1)
        self.assertIn("keypress/Back", problems[0])

    def test_since_ignores_what_happened_before(self):
        scenario = {"expect": [{"operation": "pairing.accepted"}]}
        self.assertEqual(len(expect.check(EVENTS, scenario, since=1)), 1)

    def test_an_unmet_expectation_shows_the_events_it_looked_at(self):
        problems = expect.check(EVENTS, {"expect": [{"operation": "text/*"}]})
        self.assertIn("launch/12", problems[0])

    def test_an_empty_pattern_is_refused_rather_than_matching_everything(self):
        with self.assertRaises(ValueError):
            expect.check(EVENTS, {"expect": [{}]})


class CommandLineTests(unittest.TestCase):
    def test_an_exported_log_is_checked_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "log.jsonl").write_text("".join(json.dumps(e) + "\n" for e in EVENTS))
            (root / "ok.json").write_text(json.dumps({"expect": [{"operation": "launch/*"}]}))
            (root / "bad.json").write_text(json.dumps({"expect": [{"operation": "text/*"}]}))
            log = str(root / "log.jsonl")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(expect.main([str(root / "ok.json"), "--events", log]), 0)
                self.assertEqual(expect.main([str(root / "bad.json"), "--events", log]), 1)
            self.assertIn("text/*", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
