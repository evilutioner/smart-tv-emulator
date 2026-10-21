"""Measured audio queries and native editor transitions over the real listeners."""
import base64
import json
import unittest

from tests.test_roku import RokuCase
from tvemu.conformance import compare
from tvemu.platforms.common import xmlbytes
from tvemu.platforms.roku.conformance.state import response_parts


class XmlValueTests(unittest.TestCase):
    def test_evidence_clock_mask_preserves_other_json_bytes(self):
        raw = b'{"notify":"textedit-closed","param-textedit-id":"1","timestamp":"1.000"}'
        later = raw.replace(b'1.000', b'2.000')
        self.assertEqual(response_parts(raw, None)['wire'], response_parts(later, None)['wire'])
        reformatted = later.replace(b':"', b': "', 1)
        self.assertNotEqual(response_parts(raw, None)['wire'],
                            response_parts(reformatted, None)['wire'])
        with self.assertRaises(ValueError):
            response_parts(raw.replace(b'1.000', b'not-a-clock'), None)

    def test_only_declared_attribute_and_empty_leaf_can_change(self):
        original = b'<root><destinations><destination name="hdmi"><volume>100</volume></destination></destinations><rtp><address /></rtp></root>'
        actual = xmlbytes.replace_value(original, 'destinations.destination.@name', 'datagram')
        actual = xmlbytes.replace_value(actual, 'rtp.address', '127.0.0.1:1234')
        self.assertEqual(xmlbytes.replace_value(original, 'rtp.address', ''), original)
        outcome = compare.Outcome()
        compare.compare_body(original, actual,
                             ('destinations.destination.@name', 'rtp.address'), {}, outcome)
        self.assertFalse(outcome.problems, outcome.problems)
        for broken in (actual.replace(b'100', b'101'), actual.replace(b'name=', b'other='),
                       actual.replace(b'</rtp>', b'<extra/></rtp>')):
            outcome = compare.Outcome()
            compare.compare_body(original, broken,
                                 ('destinations.destination.@name', 'rtp.address'), {}, outcome)
            self.assertTrue(outcome.problems, broken)

    def test_attributes_are_addressed_unambiguously_and_escaped(self):
        data = b"<r><a label='x'/></r>"
        self.assertEqual(xmlbytes.replace_value(data, 'a.@label', "<&'\""),
                         b"<r><a label='&lt;&amp;&apos;&quot;'/></r>")
        with self.assertRaises(ValueError):
            xmlbytes.replace_value(b'<r><a label="x"/><a label="y"/></r>', 'a.@label', 'z')
        with self.assertRaises(ValueError):
            xmlbytes.replace_value(data, 'a.child', 'z')


class NativeTextTests(RokuCase):
    async def subscribe(self, socket):
        await self.ask(socket, 'subscribe', request='request-events',
                       **{'param-events': '+textedit-opened,+textedit-changed,+textedit-closed'})

    async def query(self, socket):
        reply = await self.ask(socket, 'query', request='query-textedit-state')
        return json.loads(base64.b64decode(reply['content-data']))['textedit-state']

    async def test_focus_ids_and_independent_subscriptions(self):
        one, _ = await self.session()
        two, _ = await self.session()
        await self.subscribe(one)
        self.core.focus_field(True, 'full')
        opened = await one.receive_json()
        self.assertEqual((opened['notify'], opened['param-textedit-id']), ('textedit-opened', '1'))
        self.assertEqual((await self.query(two))['textedit-id'], '1')
        self.core.focus_field(False)
        self.assertEqual((await one.receive_json())['notify'], 'textedit-closed')
        self.core.focus_field(True, 'full')
        self.assertEqual((await one.receive_json())['param-textedit-id'], '2')
        self.assertEqual((await self.query(two))['textedit-id'], '2')
        await one.close(); await two.close()

    async def test_text_reply_precedes_echo_and_cursor_counts_codepoints(self):
        socket, _ = await self.session()
        self.core.focus_field(True, 'full')
        await self.subscribe(socket)
        reply = await self.ask(socket, 'write', request='set-textedit-text', **{
            'param-textedit-id': '1', 'param-text': 'A😀Б中',
            'param-selection-start': '1', 'param-selection-end': '5'})
        self.assertEqual(reply['response-id'], 'write')
        echo = await socket.receive_json()
        self.assertEqual(echo['param-selection-start'], '4')
        self.assertEqual(echo['param-selection-end'], '4')
        self.assertEqual(echo['param-text'], 'A😀Б中')
        self.assertEqual(self.core.text_field.text, 'A😀Б中')
        # Dashboard edits use the same buffer and produce native notifications.
        await self.core.text('insert', text='z', transport='lab')
        self.assertEqual((await socket.receive_json())['param-text'], 'A😀Б中z')
        await socket.close()

    async def test_over_limit_and_wrong_id_are_successful_noops(self):
        socket, _ = await self.session()
        self.core.focus_field(True, 'full')
        async def write(identifier, text):
            return await self.ask(socket, 'write', request='set-textedit-text',
                                  **{'param-textedit-id': identifier, 'param-text': text})
        self.assertEqual((await write('1', '😀' * 38))['status'], '200')
        for identifier, text in [('wrong-id', 'replaced'), ('1', 'a' * 76)]:
            self.assertEqual((await write(identifier, text))['status'], '200')
            self.assertEqual((await self.query(socket))['text'], '😀' * 38)
        # Local edits must not advertise an impossible native field state either.
        await self.core.text('insert', text='a' * 76, replace=True, transport='lab')
        self.assertEqual((await self.query(socket))['text'], '😀' * 38)
        await socket.close()
