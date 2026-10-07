"""The open-source client harness: declarations, the verdict, records and their pages.

Running a real client downloads it, so no test here does. What stays offline is everything
around it: each declared client is well formed, the verdict reads steps, gaps and the event
log the way docs/open-source-clients.md says, the generated pages match their records, and
one run end to end with a binding that needs nothing installed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.support import STUB_IDS
from tvemu import expect
from tvemu.clients import report
from tvemu.clients.model import (ACTIONS, PLATFORMS, client_specs, judge, load_spec,
                                 stale_gaps)
from tvemu.clients.runner import HARNESS, Scrubber, _npm_tree, repository_root, run
from tvemu.platforms import platform_ids
from tvemu.platforms.catalogue import catalogue_entry

ROOT = Path(__file__).resolve().parents[1]


def _profiles(platform_id: str) -> list[str]:
    directory = PLATFORMS / platform_id / "profiles"
    return sorted(path.name for path in directory.iterdir() if (path / "profile.json").is_file())


def _spec(root: Path, platform_id: str, profiles: list[str], extra: str = "",
          install: str = "none", binding: str = ""):
    root.mkdir(parents=True, exist_ok=True)
    (root / "client.toml").write_text(textwrap.dedent(f"""\
        schema_version = 1
        summary = "a client written for this test"
        upstream = "https://example.test/client"
        license = "MIT"

        [install]
        kind = "{install}"

        [run]
        profiles = {json.dumps(profiles)}
        timeout = 60
        """) + textwrap.dedent(extra), encoding="utf-8")
    if binding:
        (root / "binding.py").write_text(textwrap.dedent(binding), encoding="utf-8")
    return load_spec(root, platform_id)


def _step(name, status="ok", action="key", events=(0, 0), **extra):
    return {"name": name, "action": action, "status": status, "detail": "",
            "events": list(events), **extra}


def _unsupported(event_id, operation):
    return {"id": event_id, "kind": "unsupported", "operation": operation, "status": 501}


class DeclaredClientsTests(unittest.TestCase):
    def test_every_declared_client_is_well_formed(self):
        specs = client_specs()
        if not specs:
            self.skipTest("this build declares no open-source client")
        for spec in specs:
            with self.subTest(client=spec.key):
                self.assertTrue(spec.binding.is_file(), f"a client needs {spec.binding.name}")
                if spec.binding.suffix == ".py":
                    compile(spec.binding.read_text(encoding="utf-8"), str(spec.binding), "exec")
                elif shutil.which("node"):
                    subprocess.run(["node", "--check", str(spec.binding)], check=True,
                                   capture_output=True)
                for profile in spec.profiles:
                    self.assertIn(profile, _profiles(spec.platform))
                if spec.install != "none":
                    self.assertTrue(spec.package, "an installed client names its package")
                    self.assertTrue(spec.last_green, "an installed client pins a last green version")
                if spec.scenario is not None:
                    self.assertEqual(expect.check([], {**spec.scenario, "expect": []}), [])
                for gap in spec.gaps:
                    self.assertTrue(gap.reason.strip(), f"{gap.operation} needs a reason")

    def test_the_generated_pages_match_their_records(self):
        if repository_root() is None:
            self.skipTest("pages are rendered into a checkout")
        for path, text in report.pages(ROOT).items():
            with self.subTest(page=path.relative_to(ROOT).as_posix()):
                self.assertTrue(path.is_file(), "run `python -m tvemu.clients report`")
                self.assertEqual(path.read_text(encoding="utf-8"), text,
                                 "out of date: run `python -m tvemu.clients report`")

    def test_the_catalogue_names_exactly_the_clients_whose_latest_record_passes(self):
        """The README's 🧪 and its count come from the catalogue; only a recorded run earns them."""
        if repository_root() is None:
            self.skipTest("records live in a checkout")
        for platform_id in platform_ids():
            entry = catalogue_entry(platform_id)
            if platform_id in STUB_IDS or entry is None:
                continue
            passing = set()
            for spec in client_specs((platform_id,)):
                records = report.read_records(ROOT, spec)
                if records and records[0]["verdict"] == "pass":
                    passing.add((spec.name, spec.upstream))
            with self.subTest(platform=platform_id):
                self.assertEqual({(client.name, client.url) for client in entry.clients}, passing,
                                 "catalogue.json `clients` must list exactly the declared "
                                 "clients whose latest recorded run passes, each linked to "
                                 "the upstream its client.toml names")

    def test_every_record_belongs_to_a_declared_client(self):
        # Records of a television this build does not include ship as published evidence,
        # while the client that made them ships only with the platform.
        declared = {spec.key for spec in client_specs()}
        present = set(platform_ids())
        for path in (ROOT / "docs" / "clients").glob("*/*/*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(record=path.name):
                if record["platform"] in present:
                    self.assertIn(f"{record['platform']}/{record['client']['name']}", declared)
                self.assertTrue(record["emulator"]["clean"], "a record is made from a clean tree")
                self.assertNotIn("commit", record["emulator"],
                                 "a record names the emulator by version, which both builds share")
                self.assertNotIn("<workspace>", json.dumps(record["client"]["environment"]))


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.spec = _spec(self.root / "client", "any", ["a", "b"], extra="""
            [[gaps]]
            operation = "POST /known"
            reason = "no capture holds it"

            [[gaps]]
            operation = "query/icon/*"
            reason = "no capture holds any icon"

            [[gaps]]
            operation = "GET /only-b"
            profiles = ["b"]
            reason = "profile b's capture lacks it"

            [[known_failures]]
            step = "understood"
            reason = "the evidence to fix it is not recorded yet"
            """)

    def test_a_clean_run_passes(self):
        verdict = judge(self.spec, "a", [_step("press")], [], since=0)
        self.assertEqual(verdict.verdict, "pass")

    def test_an_undeclared_gap_fails_the_run(self):
        verdict = judge(self.spec, "a", [_step("press")], [_unsupported(3, "POST /new")], 0)
        self.assertEqual(verdict.verdict, "fail")
        self.assertIn("POST /new", verdict.problems[0])

    def test_a_step_failing_on_a_declared_gap_is_a_known_gap(self):
        steps = [_step("search", "fail", events=(2, 4))]
        verdict = judge(self.spec, "a", steps, [_unsupported(3, "POST /known")], 0)
        self.assertEqual(verdict.verdict, "pass")
        self.assertEqual(steps[0]["status"], "known-gap")

    def test_a_gap_declared_for_one_profile_fails_on_another(self):
        events = [_unsupported(3, "GET /only-b")]
        self.assertEqual(judge(self.spec, "b", [_step("x", "fail", events=(2, 4))], events, 0).verdict,
                         "pass")
        self.assertEqual(judge(self.spec, "a", [_step("x", "fail", events=(2, 4))], events, 0).verdict,
                         "fail")

    def test_a_known_failure_is_reported_and_one_that_passes_is_stale(self):
        failing = [_step("understood", "fail")]
        self.assertEqual(judge(self.spec, "a", failing, [], 0).verdict, "pass")
        self.assertEqual(failing[0]["status"], "known-failure")
        passing = judge(self.spec, "a", [_step("understood")], [], 0)
        self.assertEqual(passing.verdict, "fail")
        self.assertIn("stale", passing.problems[0])

    def test_a_required_step_stopped_on_a_declared_gap_is_not_a_crash(self):
        steps = [_step("identify", "fail", events=(2, 4), required=True)]
        verdict = judge(self.spec, "b", steps, [_unsupported(3, "GET /only-b")], 0,
                        binding_exit="binding exited 1: stopped after required step identify")
        self.assertEqual(verdict.verdict, "pass")

    def test_a_binding_crash_and_an_unknown_action_fail(self):
        crashed = judge(self.spec, "a", [_step("press")], [], 0, binding_exit="binding exited 1")
        self.assertEqual(crashed.verdict, "fail")
        unknown = judge(self.spec, "a", [_step("press", action="teleport")], [], 0)
        self.assertEqual(unknown.verdict, "fail")
        self.assertNotIn("teleport", ACTIONS)

    def test_a_gap_ending_in_a_star_covers_every_operation_it_prefixes(self):
        steps = [_step("icon", "fail", events=(2, 4))]
        verdict = judge(self.spec, "a", steps, [_unsupported(3, "query/icon/12")], 0)
        self.assertEqual(verdict.verdict, "pass")
        self.assertEqual(steps[0]["status"], "known-gap")
        self.assertEqual(judge(self.spec, "a", [_step("x")], [_unsupported(3, "query/iconic")],
                               0).verdict, "fail")

    def test_a_declared_gap_no_covered_profile_met_is_stale(self):
        verdicts = [judge(self.spec, "a", [_step("x")],
                          [_unsupported(3, "POST /known"), _unsupported(4, "query/icon/7")], 0),
                    judge(self.spec, "b", [_step("x")], [], 0)]
        self.assertEqual(stale_gaps(self.spec, verdicts), ["GET /only-b"])

    def test_events_before_the_run_are_not_judged(self):
        verdict = judge(self.spec, "a", [_step("x")], [_unsupported(1, "POST /new")], since=1)
        self.assertEqual(verdict.verdict, "pass")


class HarnessTests(unittest.TestCase):
    def test_both_harnesses_write_the_same_step_record(self):
        python = (HARNESS / "tvemu_binding.py").read_text(encoding="utf-8")
        javascript = (HARNESS / "tvemu_binding.mjs").read_text(encoding="utf-8")
        for field in ("TVEMU_DEVICE_HOST", "TVEMU_DEVICE_PORT", "TVEMU_PROFILE", "TVEMU_API",
                      "TVEMU_WORKSPACE", "TVEMU_RESULTS", "not-offered", "duration_ms",
                      "required", "stopped after required step"):
            with self.subTest(field=field):
                self.assertIn(field, python)
                self.assertIn(field, javascript)
        if shutil.which("node"):
            subprocess.run(["node", "--check", str(HARNESS / "tvemu_binding.mjs")], check=True,
                           capture_output=True)

    def test_an_npm_tree_flattens_to_every_package_once(self):
        tree = {"dependencies": {
            "client": {"version": "2.0.0", "dependencies": {
                "xml": {"version": "1.1.0"}, "debug": {"version": "4.0.0"}}},
            "debug": {"version": "4.0.0"}}}
        self.assertEqual(sorted(_npm_tree(tree)), ["client@2.0.0", "debug@4.0.0", "xml@1.1.0"])


class ScrubberTests(unittest.TestCase):
    def test_workspace_and_home_never_reach_a_record(self):
        workspace = Path(tempfile.gettempdir()) / "tvemu-client-x"
        scrub = Scrubber(workspace)
        cleaned = scrub({"detail": [f"{workspace}/venv/lib/x.py", f"{Path.home()}/.cache"]})
        self.assertEqual(cleaned, {"detail": ["<workspace>/venv/lib/x.py", "~/.cache"]})


class EndToEndTests(unittest.TestCase):
    """One real run: a fresh virtual environment, the emulator in its own process."""

    def test_a_binding_without_dependencies_runs_against_the_emulator(self):
        platform_id = next((pid for pid in platform_ids() if pid not in STUB_IDS), None)
        if platform_id is None:
            self.skipTest("this build ships no television")
        profile = _profiles(platform_id)[0]
        with tempfile.TemporaryDirectory() as temporary:
            spec = _spec(Path(temporary) / "plain", platform_id, [profile], binding="""\
                from tvemu_binding import Harness

                async def main(harness):
                    async with harness.step("the emulator serves this profile", "identify"):
                        state = await harness.state()
                        assert state["device"]["id"] == harness.profile, state["device"]
                        assert state["service_listening"]
                    harness.not_offered("voice", "voice", "a plain client has no microphone")

                Harness.main(main)
                """)
            record = run(spec)
        self.assertEqual(record["verdict"], "pass", record["profiles"])
        steps = record["profiles"][0]["steps"]
        self.assertEqual([step["status"] for step in steps], ["ok", "not-offered"])
        self.assertEqual(record["client"]["install"], "none")
        self.assertNotIn(temporary, json.dumps(record))


if __name__ == "__main__":
    unittest.main()
