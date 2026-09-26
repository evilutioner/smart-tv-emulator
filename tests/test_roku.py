"""Roku wire behaviour: HTTP ECP, the ecp-2 WebSocket and the four network-access modes.

Value sets and field presence are claims in `platforms/roku/contract.py`, which the shared
merge gate checks against every capture. What is tested here is the server: the rules a live
set was measured to enforce, which the emulator exists to reproduce.
"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer
from yarl import URL

from tests.support import STUB_IDS
from tvemu.control import control_app
from tvemu.core import Core, Settings
from tvemu.platforms import platform_ids
from tvemu.platforms.roku import ROKU, RokuAdapter
from tvemu.platforms.common.evidence import load_capture
from tvemu.platforms.roku.contract import ECP2_QUERIES, OPERATION_CLAIMS
from tvemu.platforms.roku.ecp import auth_response
from tvemu.runtime import Runtime

TCL_PROFILE = "tcl-roku-tv-32s357"
TCL_CAPTURE = load_capture("tvemu.platforms.roku", "tcl-roku-tv-32s357-enabled")
LIMITED_CAPTURE = load_capture("tvemu.platforms.roku", "tcl-roku-tv-32s357-15-3-4")
CLOSED = ("CLOSE", "CLOSED", "CLOSING")


class RokuCase(unittest.IsolatedAsyncioTestCase):
    profile = ""

    async def asyncSetUp(self):
        self.core = Core(ROKU, Settings(device_profile=self.profile))
        self.adapter = RokuAdapter(self.core)
        self.core.service_listening = True
        self.client = TestClient(TestServer(self.adapter.ecp.app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.adapter.ecp.disconnect()

    async def session(self):
        websocket = await self.client.ws_connect("/ecp-session", protocols=("ecp-2",))
        challenge = await websocket.receive_json()
        await websocket.send_json({
            "request": "authenticate", "request-id": "1",
            "param-response": auth_response(challenge["param-challenge"]),
        })
        self.assertEqual((await websocket.receive_json())["status"], "200")
        return websocket, challenge

    async def ask(self, websocket, request_id: str, **payload) -> dict:
        await websocket.send_json({"request-id": request_id, **payload})
        return await websocket.receive_json()

    async def press(self, websocket, request_id: str, key: str) -> dict:
        return await self.ask(websocket, request_id, request="key-press", **{"param-key": key})


class HttpKeyTests(RokuCase):
    async def test_the_whole_path_segment_is_percent_decoded_unlike_param_key(self):
        self.core.focus_field(True)
        for path in ("/keypress/Lit_h", "/keypress/LIT_i", "/keypress/%4Cit_!",
                     "/keypress/Lit_%20", "/keypress/Lit_%D0%AF"):
            with self.subTest(path=path):
                self.assertEqual((await self.client.post(path)).status, 200)
        self.assertEqual(self.core.text_field.text, "hi! Я")
        self.assertEqual((await self.client.post("/keypress/%48ome")).status, 200)
        self.assertEqual(self.core.counts["Home"], 1)

    async def test_a_button_name_ignores_case(self):
        for path in ("/keypress/Home", "/keypress/home", "/keypress/HOME"):
            self.assertEqual((await self.client.post(path)).status, 200, path)
        self.assertEqual(self.core.counts["Home"], 3)

    async def test_a_key_that_is_not_one_is_refused(self):
        for path in ("/keypress/Lit_AB", "/keypress/Bogus", "/keypress/Lit_"):
            self.assertEqual((await self.client.post(path)).status, 400, path)

    async def test_backspace_and_enter_edit_only_a_focused_field(self):
        self.assertEqual((await self.client.post("/keypress/Lit_h")).status, 200)
        self.assertEqual(self.core.text_field.text, "", "nothing focused, nothing typed")
        self.core.focus_field(True)
        for path in ("/keypress/Lit_h", "/keypress/Lit_i", "/keypress/Backspace"):
            self.assertEqual((await self.client.post(path)).status, 200)
        self.assertEqual(self.core.text_field.text, "h")
        self.assertEqual((await self.client.post("/keypress/Enter")).status, 200)
        self.assertFalse(self.core.text_field.focused)

    async def test_launch_publishes_the_id_and_the_exact_query(self):
        response = await self.client.post(
            URL("/launch/8378?contentID=movie%2F42&mediaType=movie", encoded=True))
        self.assertEqual(response.status, 200)
        launch = self.core.snapshot()["applications"]["last_launch"]
        self.assertEqual((launch["id"], launch["surface"]), ("8378", "ecp"))
        self.assertEqual(launch["payload"], "contentID=movie%2F42&mediaType=movie")


class Ecp2Tests(RokuCase):
    async def test_the_challenge_is_a_compact_notification_carrying_an_uptime(self):
        websocket = await self.client.ws_connect("/ecp-session", protocols=("ecp-2",))
        try:
            raw = (await websocket.receive()).data
            self.assertIn('"notify":"authenticate"', raw)
            self.assertNotIn(", ", raw)
            self.assertNotIn('": ', raw)
        finally:
            await websocket.close()
        websocket, challenge = await self.session()
        await websocket.close()
        self.assertNotIn("status", challenge)
        self.assertIsInstance(challenge["param-methods"], list)
        self.assertGreaterEqual(float(challenge["timestamp"]), 0.0)

    async def test_param_key_ignores_case_and_is_never_percent_decoded(self):
        self.core.focus_field(True)
        websocket, _ = await self.session()
        try:
            for number, key in enumerate(("Home", "home", "HOME", "Lit_h", "LIT_i", "lit_!",
                                          "LIT_ ", "Lit_Я"), start=2):
                self.assertEqual((await self.press(websocket, str(number), key))["status"],
                                 "200", key)
            self.assertEqual(self.core.counts["Home"], 3)
            self.assertEqual(self.core.text_field.text, "hi! Я")
            for number, key in enumerate(("Lit_%D0%AF", "Lit_%20", "%48ome", "Lit_%ZZ",
                                          "Lit_AB", "Bogus", ""), start=20):
                reply = await self.press(websocket, str(number), key)
                self.assertEqual((reply["status"], reply["status-msg"]),
                                 ("400", "Bad Request"), key)
            reply = await self.ask(websocket, "30", request="key-press", key="Home")
            self.assertEqual(reply["status"], "400", "the field must be spelled param-key")
        finally:
            await websocket.close()

    async def test_an_unknown_request_is_not_found(self):
        websocket, _ = await self.session()
        try:
            for request_id, name in (("2", "query-apps"), ("3", "nonsense")):
                reply = await self.ask(websocket, request_id, request=name)
                self.assertEqual((reply["status"], reply["status-msg"]), ("404", "Not Found"))
        finally:
            await websocket.close()

    async def test_a_request_id_is_echoed_and_never_validated(self):
        websocket, _ = await self.session()
        try:
            for request_id in ("", "1", "abc", "abc", "x" * 200):
                reply = await self.press(websocket, request_id, "Home")
                self.assertEqual((reply["status"], reply["response-id"]), ("200", request_id))
        finally:
            await websocket.close()

    async def test_an_unaddressable_frame_costs_the_whole_session(self):
        frames = ('{"request":"key-press","param-key":"Home"}',
                  '{"request":"key-press","param-key":"Home","request-id":7}',
                  '{"param-key":"Home","request-id":"2"}',
                  "not json at all", "[1,2,3]", '"a string"', "null", "{}")
        for raw in frames:
            with self.subTest(raw=raw):
                websocket, _ = await self.session()
                try:
                    await websocket.send_str(raw)
                    self.assertIn((await websocket.receive()).type.name, CLOSED)
                finally:
                    await websocket.close()

    async def test_every_request_the_emulator_serves_is_a_claimed_value(self):
        claim = next(claim for claim in OPERATION_CLAIMS["ecp-2.response"].claims
                     if claim.path == "response")
        declared = {value.literal for value in claim.values}
        served = {message.name for message in self.adapter.ecp.surface().messages
                  if message.direction == "in"}
        self.assertTrue(served <= declared, served - declared)


class AccessModeTests(RokuCase):
    async def test_limited_admits_keys_only_from_an_authenticated_session(self):
        self.core.settings = Settings(access_mode="limited")
        self.assertEqual((await self.client.post("/keypress/Home")).status, 403)
        self.assertEqual((await self.client.post("/launch/12")).status, 403)
        self.assertEqual((await self.client.get("/")).status, 200)
        websocket, _ = await self.session()
        try:
            self.assertEqual((await self.press(websocket, "2", "Back"))["status"], "200")
        finally:
            await websocket.close()
        self.assertEqual((self.core.counts["Home"], self.core.counts["Back"]), (0, 1))

    async def test_disabled_refuses_every_http_command_before_reading_it(self):
        self.core.settings = Settings(access_mode="disabled")
        for method, path in (("POST", "/keypress/Home"), ("POST", "/keypress/Bogus"),
                             ("POST", "/launch/12"), ("GET", "/query/apps"),
                             ("GET", "/query/device-info"), ("POST", "/search/browse")):
            with self.subTest(path=path):
                response = await self.client.request(method, path)
                self.assertEqual((response.status, await response.read()), (401, b""))
                self.assertNotIn("Content-Type", response.headers)
        self.assertEqual(self.core.counts["Home"], 0)

    async def test_disabled_keeps_documents_discovery_and_the_session(self):
        self.core.settings = Settings(access_mode="disabled")
        self.assertEqual((await self.client.get("/")).status, 200)
        self.assertNotEqual((await self.client.get("/query/nothing")).status, 401)
        self.assertTrue(self.core.access.discoverable)
        websocket, _ = await self.session()
        try:
            self.assertEqual((await self.press(websocket, "2", "Back"))["status"], "200")
        finally:
            await websocket.close()
        self.assertEqual(self.core.counts["Back"], 1)

    async def test_enabled_and_permissive_differ_only_off_subnet(self):
        self.core.host = "192.168.1.20"
        for mode, expected in (("enabled", 403), ("permissive", 200)):
            with self.subTest(mode=mode):
                self.core.settings = Settings(access_mode=mode)
                self.assertIsNone(self.core.access_denial("192.168.1.44"))
                for transport in ("http", "ws"):
                    self.assertEqual(
                        self.core.result_for_key("Home", transport, "203.0.113.5")[0], expected)


class TclProfileTests(RokuCase):
    profile = TCL_PROFILE

    async def test_the_television_serves_device_info_and_a_png(self):
        response = await self.client.get("/query/device-info")
        self.assertEqual((response.status, response.content_type), (200, "text/xml"))
        self.assertIn(b"<model-number>H104X</model-number>", await response.read())
        self.assertEqual(response.headers["Server"], "Roku/15.3.4 UPnP/1.0 Roku/15.3.4")
        response = await self.client.get("/device-image.png")
        self.assertEqual((response.status, response.content_type), (200, "image/png"))
        self.assertEqual((await response.read())[:8], b"\x89PNG\r\n\x1a\n")

    async def test_the_envelope_carries_its_own_copy_of_device_info(self):
        http = await (await self.client.get("/query/device-info")).read()
        websocket, _ = await self.session()
        try:
            reply = await self.ask(websocket, "2", request="query-device-info")
        finally:
            await websocket.close()
        self.assertEqual((reply["status"], reply["content-type"]),
                         ("200", 'text/xml; charset="utf-8"'))
        self.assertIn(b"<virtual-device-id>", base64.b64decode(reply["content-data"]))
        self.assertNotIn(b"<virtual-device-id>", http)

    async def test_every_captured_ecp2_query_replays_the_captured_bytes(self):
        websocket, _ = await self.session()
        try:
            for number, name in enumerate(ECP2_QUERIES, start=2):
                expected = json.loads(TCL_CAPTURE.payload(f"ws.{name}"))
                reply = await self.ask(websocket, str(number), request=name)
                self.assertEqual(
                    (reply["status"], reply["content-type"], reply["content-data"]),
                    ("200", expected["content-type"], expected["content-data"]), name)
        finally:
            await websocket.close()

    async def test_a_frame_lists_its_keys_in_sorted_order_as_the_set_does(self):
        websocket, _ = await self.session()
        try:
            await websocket.send_json({"request": "query-active-app", "request-id": "2"})
            raw = (await websocket.receive()).data
        finally:
            await websocket.close()
        self.assertEqual(list(json.loads(raw)), sorted(json.loads(raw)))
        self.assertTrue(raw.startswith('{"content-data":'), raw[:20])

    async def test_the_two_channel_lists_differ_as_the_sets_did(self):
        http = await (await self.client.get("/query/apps")).read()
        self.assertEqual(http, TCL_CAPTURE.payload("http.apps"))
        self.assertNotIn(b"subtype=", http)
        websocket, _ = await self.session()
        try:
            reply = await self.ask(websocket, "2", request="query-apps")
        finally:
            await websocket.close()
        self.assertIn(b"subtype=", base64.b64decode(reply["content-data"]))

    async def test_releasing_a_key_nobody_holds_is_202_on_both_wires(self):
        for path, status in (("/keydown/Lit_a", 200), ("/keyup/LIT_a", 200),
                             ("/keyup/Lit_b", 202), ("/keydown/Home", 200),
                             ("/keyup/home", 200), ("/keyup/Home", 202)):
            with self.subTest(path=path):
                response = await self.client.post(path)
                self.assertEqual((response.status, await response.read()), (status, b""))
        self.assertEqual(self.core.snapshot()["held_keys"], [])
        websocket, _ = await self.session()
        try:
            for number, (name, key, status) in enumerate(
                    (("key-down", "Lit_a", "200"), ("key-up", "Lit_a", "200"),
                     ("key-up", "Lit_b", "202")), start=2):
                reply = await self.ask(websocket, str(number), request=name,
                                       **{"param-key": key})
                self.assertEqual(reply["status"], status, (name, key))
            self.assertEqual(reply["status-msg"], "Accepted")
        finally:
            await websocket.close()


class TclLimitedModeTests(RokuCase):
    """What the TCL set on 15.3.4 answered with network access set to Limited."""

    profile = TCL_PROFILE

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.core.settings = Settings(device_profile=TCL_PROFILE, access_mode="limited")

    async def test_plain_http_loses_every_restricted_query_in_the_sets_own_words(self):
        refusal = LIMITED_CAPTURE.payload("http.apps")
        for path in ("/query/apps", "/query/media-player", "/query/icon/12",
                     "/query/tv-channels", "/query/audio-device", "/query/sgnodes/all"):
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual((response.status, response.content_type),
                                 (403, "text/plain"))
                self.assertEqual(await response.read(), refusal)

    async def test_device_info_active_app_and_the_documents_stay_open(self):
        for path in ("/", "/query/device-info", "/query/active-app", "/ecp_SCPD.xml",
                     "/device-image.png"):
            self.assertEqual((await self.client.get(path)).status, 200, path)
        self.assertEqual(await (await self.client.get("/query/active-app")).read(),
                         TCL_CAPTURE.payload("http.active-app"))
        self.assertNotEqual((await self.client.get("/query/nothing")).status, 403)

    async def test_a_refused_key_says_nothing_and_an_unknown_one_is_judged_first(self):
        for path, status in (("/keyup/Lit_a", 403), ("/keypress/TvemuProbe", 400)):
            with self.subTest(path=path):
                response = await self.client.post(path)
                self.assertEqual(response.status, status)
                self.assertEqual(await response.read(), b"")

    async def test_an_authenticated_session_keeps_every_query_and_key(self):
        websocket, _ = await self.session()
        try:
            reply = await self.ask(websocket, "2", request="query-apps")
            self.assertEqual(reply["status"], "200")
            self.assertIn(b"<apps>", base64.b64decode(reply["content-data"]))
            self.assertEqual((await self.press(websocket, "3", "Back"))["status"], "200")
        finally:
            await websocket.close()


class StickProfileTests(RokuCase):
    async def test_a_route_the_capture_lacks_is_501_not_a_fabricated_body(self):
        self.assertEqual((await self.client.get("/query/device-info")).status, 501)


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_shell_names_no_platform_and_serves_every_module(self):
        core = Core(ROKU, Settings())
        runtime = Runtime(core, RokuAdapter(core))
        runtime.started = True
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(TestServer(
                control_app(runtime, Path(directory) / "settings.json", port=8888)))
            await client.start_server()
            headers = {"Host": "127.0.0.1:8888"}
            try:
                shell = await (await client.get("/", headers=headers)).read()
                self.assertIn(b'src="/app.js"', shell)
                self.assertNotIn(b"Roku", shell)
                for asset in ["/dom.js"] + [f"/platforms/{platform_id}.js"
                                            for platform_id in platform_ids()
                                            if platform_id not in STUB_IDS]:
                    self.assertEqual((await client.get(asset, headers=headers)).status, 200,
                                     asset)
                self.assertEqual((await client.get("/../core.py", headers=headers)).status,
                                 404)
                snapshot = await (await client.get("/api/v1/state", headers=headers)).json()
                self.assertEqual([mode["id"] for mode in snapshot["access_modes"]],
                                 ["enabled", "permissive", "limited", "disabled"])
            finally:
                await client.close()


if __name__ == "__main__":
    unittest.main()
