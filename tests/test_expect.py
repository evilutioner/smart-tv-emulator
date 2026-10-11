"""A scenario check reads the event log the way a driver test would assert on it."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tvemu import expect
from tvemu.core import Core
from tvemu.platforms import default_platform, platform_descriptor

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

    def test_evicted_forbidden_event_cannot_turn_into_success(self):
        core = Core(platform_descriptor(default_platform()))
        core.record("command", "probe/refused", status=403)
        for _ in range(core.events.maxlen):
            core.record("command", "probe/accepted", status=200)
        scenario = {"expect": [{"status": 200}], "forbid": [{"status": 403}]}
        rows = expect.read_jsonl("\n".join(json.dumps(e) for e in core.events))
        self.assertIn("incomplete event log", expect.check(rows, scenario)[0])
        self.assertEqual(expect.check(rows, scenario, since=1), [])
        core.record("command", "probe/accepted", status=200)
        self.assertIn("incomplete event log",
                      expect.check(list(core.events), scenario, since=1)[0])

    def test_a_gap_inside_the_requested_range_fails(self):
        rows = [EVENTS[0], EVENTS[1], EVENTS[3]]
        scenario = {"expect": [{"operation": "launch/*"}], "forbid": [{"status": 403}]}
        self.assertIn("expected event id 3, got 4", expect.check(rows, scenario)[0])
        self.assertIn("incomplete event log", expect.check(rows, scenario, since=2)[0])
        self.assertEqual(expect.check(rows, scenario, since=3), [])

    def test_explicit_clear_starts_a_new_range_without_resetting_ids(self):
        core = Core(platform_descriptor(default_platform()))
        core.record("command", "probe/refused", status=403)
        core.clear_events()
        self.assertEqual(list(core.events), [])
        event = core.record("command", "probe/accepted", status=200)
        self.assertEqual(event["id"], 2)
        scenario = {"forbid": [{"status": 403}]}
        rows = expect.read_jsonl(json.dumps(event))
        self.assertEqual(expect.check(rows, scenario), [])
        self.assertEqual(expect.check(rows, scenario, since=1), [])
        core.clear_events()
        core.record("command", "probe/accepted", status=200)
        self.assertIn("incomplete event log", expect.check(list(core.events), scenario, since=1)[0])


class CommandLineTests(unittest.TestCase):
    def test_a_truncated_export_returns_failure_and_never_prints_ok(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = root / "scenario.json"
            scenario.write_text(json.dumps({"forbid": [{"status": 403}]}))
            log = root / "log.jsonl"
            log.write_text(json.dumps({"id": 2, "status": 200}) + "\n")
            with contextlib.redirect_stdout(io.StringIO()) as output, \
                    contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(expect.main([str(scenario), "--events", str(log)]), 1)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("incomplete event log", errors.getvalue())

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
