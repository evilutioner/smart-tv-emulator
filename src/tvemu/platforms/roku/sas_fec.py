"""SAS format-5 parity for the emulator's own audio datagrams.

The client contract is the FEC header the audio receiver of the Roku mobile app for
Android 14.1.2 reads; the coefficient table below matches the receiver's FEC
coefficients. Captured exchanges sas-00 through sas-07 in
roku-ecp2-surface-3820eu2-2026-10-18 verify the initial four equations.

Each protected vector is its prefix length as u16LE followed by the original
datagram up to, but excluding, the main sync header. Parity is a linear combination
over GF(16), independently on both nibbles, with polynomial x**4 + x + 1.
Sync and FEC headers are not protected. This implements format 5 only; it does
not implement retry requests or claim receiver recovery under packet loss.
"""
from __future__ import annotations

import struct
from collections import deque


_COEFFICIENTS = bytes.fromhex(
    "03 01 06 05 01 02 0e 06 "
    "0d 08 07 07 06 08 08 05 "
    "02 06 0d 02 01 07 08 0f "
    "03 0c 0c 0a 0a 01 0b 08 "
    "0f 01 0f 03 0c 0d 0e 01 "
    "06 0c 0c 05 06 0f 0b 0f "
    "0a 06 0e 04 07 04 0e 07 "
    "07 06 0a 03 0d 09 03 01"
)


def _multiply(left: int, right: int) -> int:
    """Multiply two field elements represented by four bits."""
    value = 0
    while right:
        if right & 1:
            value ^= left
        right >>= 1
        left <<= 1
        if left & 0x10:
            left ^= 0x13
    return value


_PRODUCTS = tuple(bytes(_multiply(c, b & 15) | (_multiply(c, b >> 4) << 4)
                        for b in range(256)) for c in range(16))


def _length(value: int) -> bytes:
    if not 0 <= value < 1 << 14:
        raise ValueError("SAS header length exceeds its two-byte representation")
    return (bytes([value]) if value < 128 else
            bytes([(value & 127) | 128, value >> 7]))


def _read_length(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("Truncated SAS header length")
    length = data[offset]
    offset += 1
    if length & 128:
        if offset >= len(data):
            raise ValueError("Truncated SAS header length")
        length = (length & 127) | (data[offset] << 7)
        offset += 1
    return length, offset


def _protected(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 10 or data[0] not in (43, 44, 45):
        raise ValueError("Expected a SAS v43-v45 main audio datagram")
    bitmap = data[9]
    if bitmap in (0x93, 0x91):
        if len(data) < 11 or data[10] != 0x40:
            raise ValueError("Unsupported SAS main audio headers")
        offset, extension = 11, True
    elif bitmap in (0x13, 0x11):
        offset, extension = 10, False
    else:
        raise ValueError("Unsupported SAS main audio headers")
    size, offset = _read_length(data, offset)
    if size != 12 or offset + size > len(data):
        raise ValueError("Expected the measured twelve-byte main audio header")
    offset += size
    if bitmap & 2:
        if offset + 2 > len(data):
            raise ValueError("Truncated SAS main audio payload length")
        size = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2 + size
        if offset > len(data):
            raise ValueError("Truncated SAS main audio payload")
    prefix = data[:offset]
    size, end = _read_length(data, offset)
    if size != 9 or end + size > len(data):
        raise ValueError("Expected the measured nine-byte main sync header")
    end += size
    if extension:
        size, end = _read_length(data, end)
        if size:
            raise ValueError("Only an empty main-packet FEC extension is supported")
    if end != len(data):
        raise ValueError("Unexpected trailing SAS main audio data")
    audio_number = int.from_bytes(data[5:9], "little")
    return data[0], audio_number, struct.pack("<H", len(prefix)) + prefix


class SasFecEncoder:
    """One session's current main packet and up to four preceding packets.

    Call after finalising the main packet's network number. Send that main
    packet, then the returned FEC packet with the next network number. Create
    a new encoder for each session; audio numbers must be consecutive.
    """

    def __init__(self):
        self._history: deque[tuple[int, int, bytes]] = deque(maxlen=4)

    def packet(self, audio_datagram: bytes, network_sequence: int) -> bytes:
        version, number, vector = _protected(audio_datagram)
        if self._history:
            previous_version, previous_number, _ = self._history[-1]
            if version != previous_version or number != (previous_number + 1) & 0xffffffff:
                raise ValueError("A SAS FEC session requires consecutive main audio numbers")
        terms = [(version, number, vector), *reversed(self._history)]
        parity = bytearray(max(len(term[2]) for term in terms))
        row = (number % 8) * 8
        distances = []
        for _, term_number, term_vector in terms:
            coefficient = _COEFFICIENTS[row + term_number % 8]
            products = _PRODUCTS[coefficient]
            for index, value in enumerate(term_vector):
                parity[index] ^= products[value]
            if term_number != number:
                distances.append((number - term_number) & 0xffffffff)
        body = (bytes([5, *distances, *([0] * (4 - len(distances)))])
                + struct.pack("<I", number) + parity)
        encoded_length = _length(len(body))
        packet = (struct.pack("<BII", version, network_sequence & 0xffffffff, number)
                  + b"\x80\x40" + encoded_length + body)
        self._history.append((version, number, vector))
        return packet
