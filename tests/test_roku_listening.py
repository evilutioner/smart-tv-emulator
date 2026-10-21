"""Private-listening receiver contracts and real-listener lifecycle regressions."""
from __future__ import annotations

import asyncio
import base64
import ctypes
import ctypes.util
import json
import struct
import unittest
from importlib.resources import files

from tests.test_roku import RokuCase
from tvemu.platforms.common.adapter import LoopbackBinding
from tvemu.platforms.common.evidence import load_capture
from tvemu.platforms.roku.listening import opus_pair, rtp_packet, rtcp_app, sas_packet


class AudioFramingTests(unittest.TestCase):
    def test_sas_main_audio_matches_hardware_datagram(self):
        capture = load_capture('tvemu.platforms.roku', 'roku-ecp2-surface-3820eu2-2026-10-18')
        raw = capture.payload('sas-00')
        expected = raw
        stream_id = struct.unpack_from('<I', raw, 18)[0]
        self.assertEqual(sas_packet(raw[26:29], 1, 0, stream_id), expected)

    def test_sas_finite_clock_matches_measured_silent_packet(self):
        capture = load_capture('tvemu.platforms.roku', 'roku-sas-clock-3820eu2-2026-10-18')
        raw = capture.exchange('clock-start').steps[2].payload
        network, audio = struct.unpack_from('<II', raw, 1)
        position = int.from_bytes(raw[12:18], 'little')
        stream = int.from_bytes(raw[18:22], 'little')
        clock = int.from_bytes(raw[-10:-4], 'little', signed=True)
        self.assertNotEqual(clock, -(1 << 47))
        actual = sas_packet(raw[26:29], audio, position, stream, clock_offset=clock)
        actual = actual[:1] + struct.pack('<I', network) + actual[5:]
        self.assertEqual(actual, raw)

    def test_rtp_wraps_sequence_and_timestamp_independently(self):
        raw = rtp_packet(b'opus', 65537, 2**32 + 480, 42)
        self.assertEqual(struct.unpack('!BBHII', raw[:12]), (128, 97, 1, 480, 42))
        self.assertEqual(raw[12:], b'opus')

    def test_prepared_fixture_and_20ms_pairs_decode_with_native_opus(self):
        library = ctypes.util.find_library('opus')
        if not library:
            self.skipTest('Optional native Opus decoder is unavailable')
        opus = ctypes.CDLL(library)
        opus.opus_decoder_create.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        opus.opus_decoder_create.restype = ctypes.c_void_p
        opus.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int,
                                    ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int]
        opus.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
        fixture = json.loads(files('tvemu.platforms.roku').joinpath('fixtures/test-tone.json').read_text())
        frames = [base64.b64decode(p) for p in fixture['packets']]
        error = ctypes.c_int()
        decoder = opus.opus_decoder_create(48000, 2, ctypes.byref(error))
        self.assertEqual(error.value, 0)
        pcm = (ctypes.c_int16 * (960 * 2))()
        try:
            for frame in frames:
                self.assertEqual(opus.opus_decode(decoder, frame, len(frame), pcm, 960, 0), 480)
            pair = opus_pair(frames[0], frames[1])
            self.assertEqual(opus.opus_decode(decoder, pair, len(pair), pcm, 960, 0), 960)
            self.assertGreater(max(abs(value) for value in pcm), 100)
        finally:
            opus.opus_decoder_destroy(decoder)


class Receiver(asyncio.DatagramProtocol):
    def __init__(self):
        self.packets = asyncio.Queue()

    def datagram_received(self, data, addr):
        self.packets.put_nowait((data, addr))


class PrivateListeningTests(RokuCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.adapter.listener_binding = LoopbackBinding()
        self.receiver, self.rtcp_receiver = Receiver(), Receiver()
        loop = asyncio.get_running_loop()
        for _ in range(100):
            self.udp, _ = await loop.create_datagram_endpoint(
                lambda: self.receiver, local_addr=('127.0.0.1', 0))
            self.port = self.udp.get_extra_info('sockname')[1]
            try:
                self.rtcp_udp, _ = await loop.create_datagram_endpoint(
                    lambda: self.rtcp_receiver, local_addr=('127.0.0.1', self.port + 1))
                break
            except (OSError, OverflowError):
                self.udp.close()
        else:
            self.fail('could not bind adjacent RTP/RTCP client ports')

    async def asyncTearDown(self):
        self.udp.close()
        self.rtcp_udp.close()
        await self.adapter.stop_all()
        await super().asyncTearDown()
        self.assertFalse(self.core.state_observers)
        self.assertFalse(self.adapter.audio.sessions)

    async def audio(self, ws, mode='mobile-sas'):
        params = {'param-audio-output': mode}
        if mode == 'mobile-sas':
            params.update({'param-sas-min-version': '43', 'param-sas-max-version': '45',
                           'param-guid': 'test-client', 'param-sas-ip-address': '127.0.0.1',
                           'param-sas-port': str(self.port)})
        else:
            params['param-devname'] = f'127.0.0.1:{self.port}:97:960'
        return await self.ask(ws, 'audio', request='set-audio-output', **params)

    async def test_sas_start_stop_and_restart_are_real_datagrams(self):
        ws, _ = await self.session()
        self.assertEqual((await self.audio(ws))['status'], '200')
        first, _ = await asyncio.wait_for(self.receiver.packets.get(), 1)
        parity, _ = await asyncio.wait_for(self.receiver.packets.get(), 1)
        second, _ = await asyncio.wait_for(self.receiver.packets.get(), 1)
        self.assertEqual(parity[9:11], b'\x80\x40')
        self.assertEqual([int.from_bytes(p[1:5], 'little') for p in (first, parity, second)], [1, 2, 3])
        self.assertEqual(first[0], 45)
        self.assertEqual(struct.unpack_from('<I', second, 12)[0] -
                         struct.unpack_from('<I', first, 12)[0], 480)
        self.assertEqual(first[18:22], second[18:22], 'stream id is stable across packets')
        await self.ask(ws, 'stop', request='mobile-sas-disconnect', **{'param-devname': 'test-client'})
        self.assertFalse(self.adapter.audio.sessions)
        self.assertEqual((await self.audio(ws))['status'], '200')
        await ws.close()

    async def test_sas_timing_feedback_replaces_sentinel_and_does_not_rebase(self):
        ws, _ = await self.session()
        await self.audio(ws)
        initial, destination = await asyncio.wait_for(self.receiver.packets.get(), 1)
        self.assertEqual(int.from_bytes(initial[-10:-4], 'little', signed=True), -(1 << 47))
        capture = load_capture('tvemu.platforms.roku', 'roku-sas-clock-3820eu2-2026-10-18')
        status = capture.exchange('clock-start').steps[1].payload
        self.udp.sendto(status, destination)
        session = next(iter(self.adapter.audio.sessions.values()))
        for _ in range(100):
            if session.clock_offset is not None:
                break
            await asyncio.sleep(.005)
        self.assertIsNotNone(session.clock_offset, 'receiver clock is required before Opus playback')
        offset = session.clock_offset
        for _ in range(20):
            packet, _ = await asyncio.wait_for(self.receiver.packets.get(), 1)
            if packet[9:11] == b'\x93\x40' and int.from_bytes(packet[-10:-4], 'little', signed=True) == offset:
                break
        else:
            self.fail('finite clock offset never reached the wire')
        changed = bytearray(status)
        changed[48:56] = (987654321).to_bytes(8, 'little', signed=True)
        self.udp.sendto(changed, destination)
        await asyncio.sleep(.03)
        self.assertEqual(session.clock_offset, offset, 'queued audio must retain its clock origin')
        await ws.close()

    async def test_two_audio_clients_stop_independently(self):
        first, _ = await self.session()
        second, _ = await self.session()
        other = Receiver()
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: other, local_addr=('127.0.0.1', 0))
        try:
            await self.audio(first)
            original_port, self.port = self.port, transport.get_extra_info('sockname')[1]
            try:
                await self.audio(second)
            finally:
                self.port = original_port
            await asyncio.wait_for(self.receiver.packets.get(), 1)
            await asyncio.wait_for(other.packets.get(), 1)
            self.assertEqual(len(self.adapter.audio.sessions), 2)
            await first.close()
            for _ in range(50):
                if len(self.adapter.audio.sessions) == 1:
                    break
                await asyncio.sleep(.01)
            self.assertEqual(len(self.adapter.audio.sessions), 1)
            await asyncio.wait_for(other.packets.get(), 1)
            await second.close()
        finally:
            transport.close()

    async def test_rtp_and_rtcp_handshake_and_bye(self):
        ws, _ = await self.session()
        self.assertEqual((await self.audio(ws, 'datagram'))['status'], '200')
        packet, _ = await asyncio.wait_for(self.receiver.packets.get(), 1)
        self.assertEqual(packet[:2], b'\x80\x61')
        self.assertEqual(packet[12] & 3, 0, '10ms Opus despite destination capacity960')
        self.assertEqual(struct.unpack_from('!I', packet, 8)[0], 0)
        target = self.adapter.bound['private-listening']
        self.udp.sendto(rtcp_app(b'VDLY', struct.pack('!I', 1200000)), target)
        while True:
            answer, _ = await asyncio.wait_for(self.rtcp_receiver.packets.get(), 1)
            if answer[1] == 204:
                break
        self.assertEqual(answer[8:], b'XDLY' + struct.pack('!I', 1200000))
        self.udp.sendto(rtcp_app(b'CVER', struct.pack('!I', 2)), target)
        while True:
            answer, _ = await asyncio.wait_for(self.rtcp_receiver.packets.get(), 1)
            if answer[1] == 204:
                break
        self.assertEqual(answer[8:], b'NCLI')
        self.udp.sendto(struct.pack('!BBHI', 0x81, 203, 1, 0), target)
        for _ in range(20):
            if not self.adapter.audio.sessions:
                break
            await asyncio.sleep(.01)
        self.assertFalse(self.adapter.audio.sessions)
        await ws.close()

    async def test_audio_disable_cancels_sessions_and_releases_listener(self):
        ws, _ = await self.session()
        await self.audio(ws)
        await self.adapter.stop_protocol('private-listening')
        self.assertFalse(self.adapter.audio.sessions)
        self.assertNotIn('private-listening', self.adapter.bound)
        await ws.close()

    async def test_invalid_destinations_and_versions_do_not_start_audio(self):
        ws, _ = await self.session()
        for params in ({'param-audio-output': 'datagram', 'param-devname': 3},
                       {'param-audio-output': 'mobile-sas', 'param-sas-min-version': '99',
                        'param-sas-max-version': '100'}, {'param-audio-output': 'unknown'}):
            reply = await self.ask(ws, 'bad', request='set-audio-output', **params)
            self.assertEqual(reply['status'], '400')
        self.assertFalse(self.adapter.audio.sessions)
        await ws.close()


class NotificationTests(RokuCase):
    async def test_two_sessions_subscribe_independently_and_replies_remain_fifo(self):
        one, _ = await self.session()
        two, _ = await self.session()
        for ws, event in [(one, 'plugin-ui-run'), (two, 'plugin-ui-exit')]:
            await self.ask(ws, 'sub', request='request-events', **{'param-events': '+' + event})
        reply = await self.ask(one, 'launch', request='launch', **{'param-channel-id': '837'})
        self.assertEqual(reply['status'], '200')
        event = await one.receive_json()
        self.assertEqual((event['notify'], event['param-channel-title']), ('plugin-ui-run', 'YouTube'))
        await two.send_json({'request': 'key-press', 'request-id': 'home', 'param-key': 'Home'})
        self.assertEqual((await two.receive_json())['response-id'], 'home')
        event = await two.receive_json()
        self.assertEqual(event['notify'], 'plugin-ui-exit')
        await self.ask(one, 'unsub', request='request-events', **{'param-events': '-plugin-ui-run'})
        await self.ask(one, 'launch2', request='launch', **{'param-channel-id': '837'})
        # If a stale notify leaked after unsubscribe this next reply would be the notify.
        self.assertEqual((await self.ask(one, 'next', request='query-apps'))['response-id'], 'next')
        await one.close()
        await two.close()


class DatagramEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_fec_evidence_rejects_corrupt_parity_despite_runtime_payload_substitution(self):
        from dataclasses import replace
        from unittest.mock import patch
        from tvemu.conformance.runner import Selection, build_plan, profiles, run_case
        from tvemu.platforms.roku.sas_fec import SasFecEncoder

        profile = 'roku-streaming-stick-4k-3820eu2'
        selected = f'roku/{profile}/evidence.sas-fec-history'
        plan = await build_plan(Selection('roku', profile, selected))
        case = replace(plan.cases[0], timeout=.2)
        reference = profiles('roku')[profile]
        self.assertTrue((await run_case(case, reference)).passed)
        encode = SasFecEncoder.packet

        def corrupt(encoder, main, sequence):
            packet = encode(encoder, main, sequence)
            return packet[:-1] + bytes([packet[-1] ^ 1])

        with patch.object(SasFecEncoder, 'packet', corrupt):
            result = await run_case(case, reference)
        self.assertFalse(result.passed)
        self.assertTrue(any('parity does not protect' in item for item in result.problems),
                        result.problems)

    async def test_clock_evidence_fails_when_sender_never_leaves_sentinel(self):
        from dataclasses import replace
        from unittest.mock import patch
        from tvemu.conformance.runner import Selection, build_plan, profiles, run_case

        profile = 'roku-streaming-stick-4k-3820eu2'
        selected = f'roku/{profile}/evidence.sas-clock'
        plan = await build_plan(Selection('roku', profile, selected))
        self.assertEqual(len(plan.cases), 1)
        case = replace(plan.cases[0], timeout=.2)
        reference = profiles('roku')[profile]
        self.assertTrue((await run_case(case, reference)).passed)

        def unknown_clock(payload, sequence, samples, stream_id, version=45, clock_offset=None):
            return sas_packet(payload, sequence, samples, stream_id, version, None)

        with patch('tvemu.platforms.roku.listening.sas_packet', unknown_clock):
            result = await run_case(case, reference)
        self.assertFalse(result.passed)
        self.assertTrue(any('TimeoutError' in item or 'finite' in item
                            for item in result.problems), result.problems)
