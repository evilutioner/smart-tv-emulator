"""The replay conformance harness: its comparator, its binding, and its runs.

No platform is named. Cases are chosen from whatever the build's profiles offer, so the
rules here hold for a build that ships one television or ten.
"""
from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

import support  # noqa: F401  (registers the stub platforms)
from tvemu.conformance import compare, http, mqtt, setup, websocket
from tvemu.conformance.model import ConformanceCase, Report
from tvemu.conformance.runner import (ADVERTISED_HOST, build_plan, coverage_complete,
                                      fresh_adapter, profiles, run_case)
from tvemu.platforms import platform_ids
from tvemu.platforms.common import adapter as common_adapter
from tvemu.platforms.common.evidence import Exchange, Step

HOST = {"host": ADVERTISED_HOST}


def body(expected: bytes, observed: bytes, *substitutions: str,
         headers: frozenset[str] = frozenset()) -> compare.Outcome:
    outcome = compare.Outcome()
    compare.compare_body(expected, observed, substitutions, HOST, outcome, headers)
    return outcome


def headers(expected: dict[str, str], observed: list[tuple[str, str]],
            *substitutions: str) -> compare.Outcome:
    outcome = compare.Outcome()
    compare.compare_headers(expected, observed, substitutions, HOST, outcome)
    return outcome


class ComparatorTest(unittest.TestCase):
    def test_identical_bytes_pass_and_one_byte_fails_with_its_offset(self):
        self.assertTrue(body(b"<root>abc</root>", b"<root>abc</root>").ok)
        outcome = body(b"<root>abc</root>", b"<root>abd</root>")
        self.assertFalse(outcome.ok)
        self.assertIn("byte 8", outcome.problems[0])

    def test_structural_equality_is_not_enough(self):
        self.assertFalse(body(b'{"a":1,"b":2}', b'{"a": 1, "b": 2}').ok)
        self.assertFalse(body(b'{"a":1,"b":2}', b'{"b":2,"a":1}').ok)
        self.assertFalse(body(b'{"a":"\\u00e9"}', '{"a":"é"}'.encode()).ok)

    def test_a_json_mask_excuses_its_value_and_nothing_beside_it(self):
        self.assertTrue(body(b'{"id":1,"result":[]}', b'{"id":42,"result":[]}', "id").ok)
        self.assertFalse(body(b'{"id":1,"result":[]}', b'{"id":42,"result":[0]}', "id").ok)
        self.assertFalse(body(b'{"id":1,"result":[]}', b'{"id":42, "result":[]}', "id").ok)

    def test_array_and_nested_paths(self):
        expected = b'{"result":[{"uri":"a","title":"x"}],"id":1}'
        self.assertTrue(body(expected, b'{"result":[{"uri":"bb","title":"x"}],"id":1}',
                             "result[0].uri").ok)
        self.assertFalse(body(expected, b'{"result":[{"uri":"bb","title":"y"}],"id":1}',
                              "result[0].uri").ok)
        self.assertTrue(body(b'{"r":[[{"v":1}]]}', b'{"r":[[{"v":7}]]}', "r[0][0].v").ok)

    def test_a_key_may_contain_a_slash_and_a_live_key_may_be_added(self):
        expected = b'{"system":{"a":1}}'
        observed = b'{"system":{"a":1},"audio/volume":{"current":3}}'
        self.assertTrue(body(expected, observed, "audio/volume").ok)
        self.assertFalse(body(expected, observed + b" ", "audio/volume").ok)
        self.assertFalse(body(expected, b'{"system":{"a":1},"other":1}', "audio/volume").ok)

    def test_a_declared_path_on_neither_side_is_a_problem(self):
        outcome = body(b'{"a":1}', b'{"a":1}', "missing")
        self.assertFalse(outcome.ok)
        self.assertIn("neither side", outcome.problems[0])

    def test_json_masks_need_json(self):
        self.assertFalse(body(b"bplist00", b"bplist00", "name").ok)

    def test_malformed_paths_are_refused(self):
        with self.assertRaises(ValueError):
            compare.json_path("a..b")

    def test_the_advertised_host_is_rendered_exactly_even_undeclared(self):
        template = b"<URLBase>http://{host}:8060/</URLBase>"
        self.assertTrue(body(template, f"<URLBase>http://{ADVERTISED_HOST}:8060/</URLBase>"
                             .encode()).ok)
        self.assertFalse(body(template, b"<URLBase>http://192.0.2.99:8060/</URLBase>").ok)

    def test_an_unknown_placeholder_needs_a_declaration_and_stands_for_one_token(self):
        template = b'0{"sid":"{sid}","upgrades":[]}'
        self.assertTrue(body(template, b'0{"sid":"abc123","upgrades":[]}', "{sid}").ok)
        self.assertFalse(body(template, b'0{"sid":"abc123","upgrades":[]}').ok)
        self.assertFalse(body(template, b'0{"sid":"a","b":"c","upgrades":[]}', "{sid}").ok)

    def test_headers_are_compared_by_value_and_found_whatever_their_case(self):
        self.assertTrue(headers({"Content-Type": "text/xml"},
                                [("content-type", "text/xml")]).ok)
        self.assertFalse(headers({"Content-Type": 'text/xml; charset="utf-8"'},
                                 [("Content-Type", "text/xml; charset=utf-8")]).ok)
        self.assertFalse(headers({"Cache-Control": "no-cache"}, []).ok)

    def test_a_header_substitution_requires_presence_only(self):
        self.assertTrue(headers({"Set-Cookie": "auth=A"}, [("Set-Cookie", "auth=B")],
                                "Set-Cookie").ok)
        self.assertFalse(headers({"Set-Cookie": "auth=A"}, [], "Set-Cookie").ok)

    def test_an_extra_served_header_is_a_note_not_a_fault(self):
        outcome = headers({}, [("Server", "x"), ("Date", "now")])
        self.assertTrue(outcome.ok)
        self.assertEqual(len(outcome.notes), 1)
        self.assertIn("Server", outcome.notes[0])
        self.assertNotIn("Date", outcome.notes[0])

    def test_a_json_value_is_replaced_without_touching_a_byte_around_it(self):
        data = b'{"request":"authenticate", "param-response":"old","request-id":"1"}'
        self.assertEqual(compare.replace_json_value(data, "param-response", b'"new!"'),
                         b'{"request":"authenticate", "param-response":"new!","request-id":"1"}')
        with self.assertRaises(ValueError):
            compare.replace_json_value(data, "absent", b"1")

    def test_neighbouring_members_only_one_side_carries_give_up_one_comma(self):
        expected = b'{"a":1,"b":{"c":2}}'
        for observed in (b'{"a":1,"b":{"c":2},"x":1,"y":[2]}',
                         b'{"x":1,"y":[2],"a":1,"b":{"c":2}}',
                         b'{"a":1,"x":1,"y":[2],"b":{"c":2}}'):
            self.assertTrue(body(expected, observed, "x", "y").ok, observed)
        self.assertFalse(body(expected, b'{"a":1,"b":{"c":2},"x":1,"z":3}', "x").ok)

    def test_a_header_named_substitution_never_masks_a_body_field(self):
        outcome = body(b'{"Set-Cookie":1}', b'{"Set-Cookie":2}', "Set-Cookie",
                       headers=frozenset({"set-cookie"}))
        self.assertFalse(outcome.ok)


class RequestTest(unittest.TestCase):
    def test_a_setup_fills_placeholders_and_adds_only_the_headers_the_capture_lacks(self):
        step = Step("in", {"method": "POST", "path": "/x/{id}",
                           "headers": {"Cookie": "auth={token}", "Accept": "a/b"}},
                    payload=b'{"pin":"{pin}"}')
        raw = http.request_bytes(step, "192.0.2.10:80", {"id": "7", "token": "T", "pin": "1"},
                                 {"accept": "c/d", "X-Key": "k"})
        head, _, payload = raw.partition(b"\r\n\r\n")
        self.assertIn(b"POST /x/7 HTTP/1.1", head)
        self.assertIn(b"Cookie: auth=T", head)
        self.assertIn(b"Accept: a/b", head)
        self.assertNotIn(b"c/d", head)
        self.assertIn(b"X-Key: k", head)
        self.assertEqual(payload, b'{"pin":"1"}')

    def test_a_placeholder_left_unfilled_is_never_sent(self):
        step = Step("in", {"method": "GET", "path": "/x", "headers": {"Cookie": "{token}"}})
        with self.assertRaises(ValueError):
            http.request_bytes(step, "192.0.2.10:80")


class DescriptionTest(unittest.TestCase):
    def module(self, **attributes):
        return type("conformance", (), attributes)

    def test_setup_hooks_are_validated(self):
        async def hook(name, client):
            return {}
        found, default = setup.hooks(self.module(SETUPS={"pair": {"provides": ["token"]}},
                                                 DEFAULT_SETUP="pair", setup=hook))
        self.assertEqual((found["pair"].provides, default), (frozenset({"token"}), "pair"))
        for bad in ({"SETUPS": {"pair": {}}},
                    {"SETUPS": {"pair": {"provides": "token"}}, "setup": hook},
                    {"SETUPS": {"pair": {"provides": []}}, "DEFAULT_SETUP": "x",
                     "setup": hook}):
            with self.assertRaises(ValueError, msg=bad):
                setup.hooks(self.module(**bad))
        with self.assertRaises(ValueError):
            setup.prepared({"values": {"token": 1}}, "pair")

    def test_an_mqtt_script_names_its_replay_exactly_once(self):
        def values(*_):
            return {}
        spec = mqtt.description(self.module(MQTT={
            "protocol": "p", "default": [["a", "x"], ["a", "*"]],
            "scripts": {"y": [["b", "*"]]}}, mqtt_values=values))
        self.assertEqual(spec.script("z"), (("a", "x"), ("a", "z")))
        self.assertEqual(spec.script("y"), (("b", "y"),))
        for script in ([["a", "x"]], [["a", "*"], ["b", "*"]], []):
            with self.assertRaises(ValueError):
                mqtt.description(self.module(MQTT={"protocol": "p", "default": script},
                                             mqtt_values=values))
        self.assertIsNone(mqtt.description(self.module()))

    def test_the_mqtt_codec_reads_back_what_it_writes(self):
        packet, rest = mqtt._decode(mqtt.publish_packet("t/x", b"\xe2\x96\xb6" * 50) + b"\x30")
        self.assertEqual((packet.kind, packet.publish(), rest),
                         (mqtt.PUBLISH, ("t/x", b"\xe2\x96\xb6" * 50), b"\x30"))
        self.assertEqual(mqtt._decode(b"\x30\x05ab"), (None, b"\x30\x05ab"))
        packet, _ = mqtt._decode(mqtt.connect_packet("id", None, None))
        self.assertEqual(packet.kind, mqtt.CONNECT)


def _profiles():
    return [(pid, reference) for pid in platform_ids()
            for reference in profiles(pid).values()]


def _references():
    return {(pid, reference.id): reference for pid, reference in _profiles()}


class BindingTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_profile_keeps_advertising_its_port_while_bound_on_loopback(self):
        found = _profiles()
        if not found:
            self.skipTest("this build ships no evidence-backed profile")
        platform_id, reference = found[0]
        adapter = fresh_adapter(platform_id, reference.id)
        protocol = adapter.profile.primary.id
        advertised = adapter.protocol_port(protocol)
        await adapter.start_protocol(protocol)
        try:
            host, port = adapter.bound[protocol]
            self.assertEqual(host, "127.0.0.1")
            self.assertNotEqual(port, 0)
            self.assertEqual(adapter.protocol_port(protocol), advertised)
            self.assertEqual(adapter.core.host, ADVERTISED_HOST)
        finally:
            await adapter.stop_all()
        self.assertEqual(adapter.bound, {})


class RunTest(unittest.IsolatedAsyncioTestCase):
    """End to end over real sockets. One plan and one run serve every assertion."""

    report: Report | None = None

    async def asyncSetUp(self):
        if RunTest.report is None:
            plan = await build_plan()
            report = Report(plan)
            references = _references()
            for case in plan.cases:
                report.results.append(
                    await run_case(case, references[(case.platform, case.profile)]))
            RunTest.report = report
        self.report = RunTest.report
        if not self.report.plan.cases:
            self.skipTest("this build ships no executable conformance case")

    def test_every_replay_is_a_case_or_a_named_gap_exactly_once(self):
        plan = self.report.plan
        covered = [(case.platform, case.profile, name)
                   for case in plan.cases for name in case.replays]
        gaps = [(gap.platform, gap.profile, gap.replay) for gap in plan.gaps]
        self.assertEqual(len(covered) + len(gaps), plan.replays)
        self.assertEqual(len(set(covered) | set(gaps)), plan.replays)
        self.assertTrue(all(gap.reason for gap in plan.gaps))

    def test_every_case_that_needs_a_setup_names_one_its_platform_declares(self):
        for case in self.report.plan.cases:
            if case.setup:
                known, _ = setup.hooks(websocket.platform_package(case.platform))
                self.assertIn(case.setup, known, case.id)

    def test_a_platform_declaring_complete_coverage_leaves_no_replay_uncovered(self):
        owed = [f"{gap.platform}/{gap.profile}/{gap.exchange}: {gap.reason}"
                for gap in self.report.plan.gaps if coverage_complete(gap.platform)]
        self.assertEqual(owed, [])

    def test_no_case_leaks_a_listener_a_socket_or_a_task(self):
        leaks = [f"{result.case.id}: {problem}" for result in self.report.results
                 for problem in result.problems if problem.startswith("leak:")]
        self.assertEqual(leaks, [])

    def test_some_platform_conforms_end_to_end(self):
        failing = {result.case.platform for result in self.report.results
                   if not result.passed}
        running = {result.case.platform for result in self.report.results}
        self.assertTrue(running - failing, "no platform passes every case it runs")

    def _passing(self, predicate=lambda case, reference: True):
        references = _references()
        for result in self.report.results:
            case = result.case
            reference = references[(case.platform, case.profile)]
            if result.passed and predicate(case, reference):
                return case, reference
        self.skipTest("no passing case of that shape")

    async def test_a_one_byte_mutation_of_a_replayed_payload_fails(self):
        case, reference = self._passing(
            lambda case, ref: bool(ref.capture.exchange(case.exchanges[0]).response().payload))
        mutated = _mutated(reference, case.exchanges[0], lambda data: data[:-1] + bytes(
            [data[-1] ^ 0x01]))
        result = await run_case(case, mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("body: first difference" in problem for problem in result.problems))

    async def test_a_one_byte_mutation_of_a_replayed_frame_fails(self):
        case, reference = self._passing(lambda case, ref: case.driver == "websocket")
        mutated = _mutated(reference, case.exchanges[-1], lambda data: data[:-1] + bytes(
            [data[-1] ^ 0x01]))
        result = await run_case(case, mutated)
        self.assertFalse(result.passed)
        self.assertTrue(any("body: first difference" in problem for problem in result.problems))

    async def test_a_mutation_inside_a_declared_field_passes_and_beside_it_fails(self):
        def json_substituted(case: ConformanceCase, reference) -> bool:
            return any(_json_scalar(reference, case, path) for name in case.replays
                       for path in reference.substitutions.get(name, ()))

        case, reference = self._passing(json_substituted)
        exchange_id = case.exchanges[0]
        path, start, end = next(found for name in case.replays
                                for path in reference.substitutions.get(name, ())
                                if (found := _json_scalar(reference, case, path)))
        inside = _mutated(reference, exchange_id,
                          lambda data: data[:start] + b'"zz"' + data[end:])
        self.assertTrue((await run_case(case, inside)).passed, path)
        beside = _mutated(reference, exchange_id,
                          lambda data: data[:end] + b" " + data[end:])
        self.assertFalse((await run_case(case, beside)).passed, path)


def _json_scalar(reference, case, path):
    """(path, start, end) of a declared JSON scalar in the captured output, or None."""
    if compare.PLACEHOLDER.fullmatch(path):
        return None
    payload = reference.capture.exchange(case.exchanges[0]).response().payload
    if not payload:
        return None
    try:
        root = compare._Scanner(payload).parse()
        found = compare._locate(root, compare.json_path(path))
    except ValueError:
        return None
    if found is None:
        return None
    node = compare._value_node(root, compare.json_path(path))
    if node.members is not None or node.items is not None:
        return None
    return path, node.start, node.end


def _mutated(reference, exchange_id, change):
    """The same profile with one output payload of one exchange changed."""
    capture = reference.capture
    exchange = capture.exchange(exchange_id)
    steps = tuple(replace(step, payload=change(step.payload))
                  if step.direction == "out" else step for step in exchange.steps)
    exchanges = dict(capture.exchanges)
    exchanges[exchange_id] = replace(exchange, steps=steps)
    return replace(reference, capture=replace(capture, exchanges=exchanges))


class WebSocketPlanTest(unittest.TestCase):
    def test_a_client_frame_the_capture_did_not_keep_is_a_gap_whatever_the_channel(self):
        exchange = Exchange("ws.x", "x", "websocket", (
            Step("in", {"channel": "c"}), Step("out", {"channel": "c"}, "x.json", b"{}")))
        channel = websocket.Channel("c", "/")
        self.assertIn("no client frame", websocket.replay_gap(exchange, channel))
        self.assertIn("no client frame", websocket.replay_gap(exchange, None))

    def test_a_kept_exchange_needs_only_its_channel(self):
        exchange = Exchange("ws.x", "x", "websocket", (
            Step("in", {"channel": "c"}, "a.json", b"{}"),
            Step("out", {"channel": "c"}, "b.json", b"{}")))
        self.assertIn("no WebSocket channel", websocket.replay_gap(exchange, None))
        self.assertEqual(websocket.replay_gap(exchange, websocket.Channel("c", "/")), "")


class LeakDetectionTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_listener_left_bound_is_reported(self):
        plan = await build_plan()
        if not plan.cases:
            self.skipTest("this build ships no executable conformance case")
        case = plan.cases[0]
        reference = _references()[(case.platform, case.profile)]

        original = common_adapter.BaseAdapter.stop_all
        kept = []

        async def keep_listening(self):
            kept.append(self)

        common_adapter.BaseAdapter.stop_all = keep_listening
        try:
            result = await run_case(case, reference)
        finally:
            common_adapter.BaseAdapter.stop_all = original
            for adapter in kept:
                await original(adapter)
        self.assertTrue(any(problem.startswith("leak:") for problem in result.problems))


if __name__ == "__main__":
    unittest.main()
