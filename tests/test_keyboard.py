"""The shared text-input layer: state, access gating, and the dashboard's own endpoints.

Wire-level keyboard behaviour is captured per platform, so it lives in that platform's
suite. What is asserted here is the part every platform shares.
"""
from __future__ import annotations

import json
import socket
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from tvemu.control import control_app
from tvemu.core import MAX_TEXT_FIELD, Core, Settings
from tests.support import (LITERAL_KEYS, NO_KEYBOARD, TEXT_API, TEXT_KEY_PREFIXES,
                           closed_access_mode,
                           needs)
from tvemu.platforms import create_platform, platform_descriptor
from tvemu.runtime import Runtime

QUIET = {"ssdp": False, "bonjour": False}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ContractTests(unittest.TestCase):
    def test_a_platform_declaring_no_keyboard_still_refuses_text(self):
        # A platform whose capture carries no text surface declares no keyboard, and the
        # shared refusals stay in place rather than inventing one.
        core = Core(platform_descriptor(needs(NO_KEYBOARD, "no keyboard")), Settings())
        self.assertIsNone(core.keyboard)
        self.assertIsNone(core.keyboard_snapshot())
        self.assertEqual(core.result_for_text("lab"), (404, "This platform serves no text input"))

    def test_a_text_key_from_a_platforms_own_wire_is_out_of_scope_not_unknown(self):
        # Such a platform has no text surface, but its own protocol map still produces one key
        # per character. It names those prefixes, so the refusal says which of the two it is.
        descriptor = platform_descriptor(needs(TEXT_KEY_PREFIXES, "self-made text keys"))
        core = Core(descriptor, Settings())
        prefix = descriptor.text_key_prefixes[0]
        self.assertEqual(core.result_for_key(f"{prefix}a", "http"),
                         (501, "Text input is out of scope"))
        self.assertEqual(core.result_for_key("Nonsense", "http"), (400, "Unknown key"))

    def test_a_text_api_platform_names_only_keys_it_actually_has(self):
        descriptor = platform_descriptor(needs(TEXT_API, "a text API"))
        self.assertTrue(descriptor.keyboard.text_api)
        # Such a platform writes over the wire, so a delete or submit key is named only when
        # its remote has one; naming it otherwise would invent a button.
        for key in (descriptor.keyboard.delete_key, descriptor.keyboard.enter_key):
            self.assertTrue(key == "" or key in descriptor.keys, key)

    def test_a_literal_key_platform_names_keys_it_actually_has(self):
        descriptor = platform_descriptor(needs(LITERAL_KEYS, "literal keypresses"))
        keyboard = descriptor.keyboard
        self.assertTrue(keyboard.literal_prefix)
        for key in (keyboard.delete_key, keyboard.enter_key):
            self.assertIn(key, descriptor.keys)

    def test_only_a_single_character_is_a_literal_key(self):
        descriptor = platform_descriptor(needs(LITERAL_KEYS, "literal keypresses"))
        prefix = descriptor.keyboard.literal_prefix
        core = Core(descriptor, Settings())
        self.assertTrue(core.is_literal_key(f"{prefix}a"))
        self.assertTrue(core.is_literal_key(f"{prefix} "))
        # Such a remote sends one character per keypress, so a longer tail is malformed.
        self.assertFalse(core.is_literal_key(f"{prefix}hello"))
        self.assertEqual(core.result_for_key(f"{prefix}hello", "http"), (400, "Unknown key"))


class FieldTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.core = Core(platform_descriptor(needs(TEXT_API, "a text API")), Settings())
        self.core.service_listening = True
        # The adapter publishes the captured field types; this test drives the shared layer.
        from tvemu.platforms.base import ContentType

        self.core.set_content_types(
            (ContentType("text", "Text"), ContentType("password", "Password", hidden=True)),
            "text")

    async def test_focus_counts_transitions_rather_than_flagging_them(self):
        start = self.core.text_field.focus_serial
        self.core.focus_field(True)
        self.assertEqual(self.core.text_field.focus_serial, start + 1)
        # Re-focusing an already focused field is not a transition.
        self.core.focus_field(True)
        self.assertEqual(self.core.text_field.focus_serial, start + 1)
        self.core.focus_field(False)
        self.assertEqual(self.core.text_field.focus_serial, start + 2)

    async def test_blurring_drops_the_buffer(self):
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="secret")
        self.core.focus_field(False)
        self.assertEqual(self.core.text_field.text, "")

    async def test_an_undeclared_field_type_is_refused(self):
        with self.assertRaises(ValueError):
            self.core.focus_field(True, "phonenumber")

    async def test_insert_delete_enter_and_replace(self):
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="hello")
        await self.core.text("insert", transport="lab", text=" there")
        self.assertEqual(self.core.text_field.text, "hello there")
        await self.core.text("delete", transport="lab", count=6)
        self.assertEqual(self.core.text_field.text, "hello")
        await self.core.text("insert", transport="lab", text="bye", replace=True)
        self.assertEqual(self.core.text_field.text, "bye")
        self.assertEqual((await self.core.text("enter", transport="lab"))[0], 200)

    async def test_submitting_dismisses_the_keyboard(self):
        # The physical set answers sendEnterKey and then pushes a blurred widget, so Enter
        # is a focus transition rather than only an event.
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="query")
        serial = self.core.text_field.focus_serial
        await self.core.text("enter", transport="lab")
        self.assertFalse(self.core.text_field.focused)
        self.assertEqual(self.core.text_field.text, "")
        self.assertEqual(self.core.text_field.focus_serial, serial + 1)

    async def test_deleting_past_the_start_empties_without_failing(self):
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="ab")
        self.assertEqual((await self.core.text("delete", transport="lab", count=9))[0], 200)
        self.assertEqual(self.core.text_field.text, "")

    async def test_malformed_arguments_are_refused(self):
        self.core.focus_field(True)
        for kwargs in ({"op": "insert", "text": 7}, {"op": "delete", "count": 0},
                       {"op": "delete", "count": True}, {"op": "wat"}):
            with self.subTest(**kwargs):
                op = kwargs.pop("op")
                status, _ = await self.core.text(op, transport="lab", **kwargs)
                self.assertEqual(status, 400)

    async def test_the_buffer_is_bounded_however_much_is_pushed(self):
        self.core.focus_field(True)
        await self.core.text("insert", transport="lab", text="x" * (MAX_TEXT_FIELD * 2))
        self.assertEqual(len(self.core.text_field.text), MAX_TEXT_FIELD)

    async def test_a_hidden_field_keeps_its_text_out_of_the_event_log(self):
        self.core.focus_field(True, "password")
        await self.core.text("insert", transport="lab", text="hunter2")
        self.assertEqual(self.core.text_field.text, "hunter2")
        events = json.dumps(list(self.core.events))
        # Events are pushed to every subscriber and written to the log export.
        self.assertNotIn("hunter2", events)
        self.assertIn("7 chars", events)

    async def test_a_visible_field_records_what_was_typed(self):
        self.core.focus_field(True, "text")
        await self.core.text("insert", transport="lab", text="news")
        self.assertIn("news", json.dumps(list(self.core.events)))


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_dashboard_is_the_screen_not_a_client_on_the_network(self):
        # A mode that closes the network surface still leaves the TV's own on-screen
        # keyboard working, because the dashboard is the screen and not a client on the LAN.
        platform_id = needs(LITERAL_KEYS, "literal keypresses")
        mode = closed_access_mode(platform_id)
        if mode is None:
            self.skipTest("this platform's firmware has no mode that refuses control")
        core = Core(platform_descriptor(platform_id), Settings(access_mode=mode.id))
        core.service_listening = True
        self.assertEqual(core.result_for_text("lab"), (200, "Accepted"))
        self.assertNotEqual(core.result_for_text("http", "127.0.0.1")[0], 200)

    async def test_a_wire_write_is_allowed_by_an_open_access_mode(self):
        core = Core(platform_descriptor(needs(TEXT_API, "a text API")),
                    Settings(access_mode="enabled"))
        core.service_listening = True
        self.assertEqual(core.result_for_text("ws", "127.0.0.1"), (200, "Accepted"))

    async def test_a_wire_write_needs_a_listening_service(self):
        core = Core(platform_descriptor(needs(TEXT_API, "a text API")), Settings())
        core.service_listening = False
        status, _ = await core.text("insert", transport="ws", peer="127.0.0.1", text="a")
        self.assertEqual(status, 503)
        # The dashboard is not served by a protocol listener, so it is unaffected.
        self.assertEqual((await core.text("insert", transport="lab", text="a"))[0], 200)


class DashboardAPITests(unittest.IsolatedAsyncioTestCase):
    async def start(self, platform_id: str):
        self.core = Core(platform_descriptor(platform_id), Settings())
        self.core.host = "127.0.0.1"
        self.core.service_port = free_port()
        self.core.settings = replace(self.core.settings, protocols=QUIET)
        self.runtime = Runtime(self.core, create_platform(platform_id, self.core))
        await self.runtime.start()
        self.addAsyncCleanup(self.runtime.close)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.client = TestClient(TestServer(control_app(
            self.runtime, Path(self.temporary.name) / "settings.json", port=8888)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)
        self.headers = {"Host": "127.0.0.1:8888", "Content-Type": "application/json"}

    async def act(self, name, body):
        return await self.client.post(f"/api/v1/actions/{name}", headers=self.headers,
                                      json=body)

    async def test_typing_from_the_dashboard_moves_the_field(self):
        await self.start(needs(TEXT_API, "a text API"))
        self.assertEqual((await self.act("field", {"focused": True})).status, 200)
        response = await self.act("text", {"op": "insert", "text": "hi"})
        self.assertEqual(response.status, 200)
        snapshot = await response.json()
        field = snapshot["keyboard"]["field"]
        self.assertEqual(field["text"], "hi")
        self.assertTrue(field["focused"])
        # The tile names who wrote, so remote and API text are distinguishable.
        self.assertEqual(field["source"], "dashboard")

    async def test_the_snapshot_offers_the_captured_field_types(self):
        await self.start(needs(TEXT_API, "a text API"))
        keyboard = (await (await self.client.get("/api/v1/state",
                                                 headers=self.headers)).json())["keyboard"]
        self.assertEqual([content["id"] for content in keyboard["content_types"]], ["text"])
        self.assertTrue(keyboard["text_api"])

    async def test_a_platform_with_no_reported_field_types_offers_none(self):
        platform_id = needs(LITERAL_KEYS, "literal keypresses")
        await self.start(platform_id)
        keyboard = (await (await self.client.get("/api/v1/state",
                                                 headers=self.headers)).json())["keyboard"]
        # A wire with no keyboard-status API reports no field type, so the dashboard has
        # none to offer and hides the selector rather than inventing a default.
        self.assertEqual(keyboard["content_types"], [])
        self.assertEqual(keyboard["literal_prefix"],
                         platform_descriptor(platform_id).keyboard.literal_prefix)

    async def test_an_undeclared_field_type_is_a_bad_request(self):
        await self.start(needs(TEXT_API, "a text API"))
        response = await self.act("field", {"focused": True, "content_type": "nope"})
        self.assertEqual(response.status, 400)

    async def test_malformed_text_bodies_are_refused(self):
        await self.start(needs(TEXT_API, "a text API"))
        await self.act("field", {"focused": True})
        for body in ({"op": "insert", "text": 7}, {"op": "delete", "count": 0},
                     {"op": "nonsense"}):
            with self.subTest(body=body):
                self.assertEqual((await self.act("text", body)).status, 400)

    async def test_both_endpoints_are_absent_when_the_platform_has_no_keyboard(self):
        await self.start(needs(NO_KEYBOARD, "no keyboard"))
        snapshot = await (await self.client.get("/api/v1/state", headers=self.headers)).json()
        self.assertIsNone(snapshot["keyboard"])
        for name, body in (("text", {"op": "insert", "text": "a"}),
                           ("field", {"focused": True})):
            with self.subTest(name=name):
                self.assertEqual((await self.act(name, body)).status, 404)


class LiteralKeyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.descriptor = platform_descriptor(needs(LITERAL_KEYS, "literal keypresses"))
        self.keyboard = self.descriptor.keyboard
        self.prefix = self.keyboard.literal_prefix
        self.core = Core(self.descriptor, Settings())
        self.core.service_listening = True

    async def key(self, key, action="keypress"):
        return await self.core.key(key, action, "http", "127.0.0.1", "owner")

    async def literal(self, char, action="keypress"):
        return await self.key(f"{self.prefix}{char}", action)

    async def test_a_literal_key_goes_nowhere_until_something_has_focus(self):
        # Nothing on screen is taking text, so the keypress is accepted and goes nowhere.
        self.assertEqual((await self.literal("a"))[0], 200)
        self.assertEqual(self.core.text_field.text, "")

    async def test_a_literal_key_types_into_a_focused_field(self):
        self.core.focus_field(True)
        for char in "hi ":
            await self.literal(char)
        self.assertEqual(self.core.text_field.text, "hi ")

    async def test_the_remotes_own_delete_and_submit_keys_edit_the_field(self):
        self.core.focus_field(True)
        await self.literal("a")
        await self.literal("b")
        await self.key(self.keyboard.delete_key)
        self.assertEqual(self.core.text_field.text, "a")
        self.assertEqual((await self.key(self.keyboard.enter_key))[0], 200)

    async def test_editing_keys_are_ordinary_keys_while_nothing_has_focus(self):
        delete = self.keyboard.delete_key
        self.assertEqual((await self.key(delete))[0], 200)
        self.assertEqual(self.core.counts[delete], 1)

    async def test_typed_characters_never_enter_the_key_counters(self):
        # counts is unbounded and ships in every snapshot, so text must not accumulate there.
        self.core.focus_field(True)
        for char in "abcdef":
            await self.literal(char)
        self.assertEqual(dict(self.core.counts), {})
        self.assertEqual(self.core.held, {})
        # A typed character is not a remote button, so it is not the "last key" either.
        self.assertIsNone(self.core.last_key)

    async def test_a_keydown_and_keyup_pair_types_once(self):
        self.core.focus_field(True)
        await self.literal("z", "keydown")
        await self.literal("z", "keyup")
        self.assertEqual(self.core.text_field.text, "z")


if __name__ == "__main__":
    unittest.main()
