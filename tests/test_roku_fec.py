"""Measured SAS parity and independent finite-field controls, without networking."""
from __future__ import annotations

import struct
import unittest

from tvemu.platforms.common.evidence import load_capture
from tvemu.platforms.roku.sas_fec import SasFecEncoder, _multiply, _protected


def polynomial_product(left, right):
    product = 0
    for bit in range(4):
        if right & (1 << bit):
            product ^= left << bit
    for bit in range(6, 3, -1):
        if product & (1 << bit):
            product ^= 0x13 << (bit - 4)
    return product


class SasFecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capture = load_capture("tvemu.platforms.roku",
                               "roku-ecp2-surface-3820eu2-2026-10-18")
        cls.main = [capture.payload(f"sas-{index:02d}") for index in (0, 2, 4, 6)]
        cls.parity = [capture.payload(f"sas-{index:02d}") for index in (1, 3, 5, 7)]

    def test_initial_four_parity_packets_match_capture_bytes(self):
        encoder = SasFecEncoder()
        for main, expected in zip(self.main, self.parity):
            network = struct.unpack_from("<I", expected, 1)[0]
            with self.subTest(network=network):
                self.assertEqual(encoder.packet(main, network), expected)

    def test_field_products_against_independent_polynomial_reduction(self):
        for left in range(16):
            for right in range(16):
                self.assertEqual(_multiply(left, right), polynomial_product(left, right))
                self.assertEqual(_multiply(left, right), _multiply(right, left))
                for third in range(16):
                    self.assertEqual(_multiply(left, right ^ third),
                                     _multiply(left, right) ^ _multiply(left, third))
            if left:
                self.assertEqual(sum(_multiply(left, value) == 1 for value in range(16)), 1)
        self.assertEqual(_multiply(2, 8), 3)

    def test_protected_prefix_excludes_sync_but_includes_wire_header(self):
        main = self.main[0]
        self.assertEqual(_protected(main)[2], b"\x1d\x00" + main[:29])
        changed_sync = main[:30] + bytes([main[30] ^ 1]) + main[31:]
        self.assertEqual(SasFecEncoder().packet(main, 2),
                         SasFecEncoder().packet(changed_sync, 2))
        changed_network = main[:1] + struct.pack("<I", 99) + main[5:]
        self.assertNotEqual(SasFecEncoder().packet(main, 2),
                            SasFecEncoder().packet(changed_network, 2))

    def test_history_is_bounded_to_four_preceding_packets(self):
        encoder = SasFecEncoder()
        packets = []
        for number in range(1, 8):
            main = self.main[0][:1] + struct.pack("<II", number * 2 - 1, number) + self.main[0][9:]
            packets.append(encoder.packet(main, number * 2))
        self.assertEqual(packets[0][13:17], b"\x00\x00\x00\x00")
        self.assertEqual(packets[3][13:17], b"\x01\x02\x03\x00")
        self.assertEqual(packets[-1][13:17], b"\x01\x02\x03\x04")
        self.assertEqual(len(encoder._history), 4)

    def test_variable_payload_sizes_and_two_byte_fec_length(self):
        main = self.main[0]
        encoder = SasFecEncoder()
        long_main = main[:24] + struct.pack("<H", 200) + bytes(range(200)) + main[29:]
        parity = encoder.packet(long_main, 2)
        size = (parity[11] & 127) | (parity[12] << 7)
        self.assertEqual(size, 237)
        self.assertEqual(len(parity), 250)
        short_main = self.main[1]
        # Zero padding keeps the previous longer vector's parity tail in the next equation.
        self.assertEqual(len(encoder.packet(short_main, 4)), 250)

    def test_rejects_malformed_packet_without_advancing_history(self):
        encoder = SasFecEncoder()
        for bad in (b"", self.main[0][:-1], self.parity[0], self.main[0] + b"\x00"):
            with self.subTest(packet=bad[:12]):
                with self.assertRaises(ValueError):
                    encoder.packet(bad, 2)
        self.assertEqual(encoder.packet(self.main[0], 2), self.parity[0])
        with self.assertRaises(ValueError):
            encoder.packet(self.main[0], 3)
        self.assertEqual(encoder.packet(self.main[1], 4), self.parity[1])

    def test_audio_numbers_wrap_and_encoder_sessions_are_independent(self):
        encoder = SasFecEncoder()
        for number in (0xffffffff, 0):
            main = self.main[0][:5] + struct.pack("<I", number) + self.main[0][9:]
            packet = encoder.packet(main, 2**32 + 2)
            self.assertEqual(struct.unpack_from("<II", packet, 1), (2, number))
        self.assertEqual(packet[13:17], b"\x01\x00\x00\x00")
        self.assertEqual(SasFecEncoder().packet(self.main[0], 2), self.parity[0])
