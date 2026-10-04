"""Telling what an audio stream is from the stream: containers, sample readings and rate."""
from __future__ import annotations

import math
import random
import struct
import unittest

from tvemu.audio import AudioSniffer, _alaw, _mulaw


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def voiced(count: int, rate: int, pitch: int = 140) -> list[float]:
    """A signal with a voice's smoothness: a few harmonics, a slow envelope and a little noise."""
    noise = random.Random(1)
    out = []
    for index in range(count):
        t = index / rate
        envelope = 0.5 + 0.5 * math.sin(2 * math.pi * 3 * t)
        value = sum(math.sin(2 * math.pi * pitch * k * t) / n
                    for n, k in enumerate((1, 2, 3, 5, 10), 1)) * envelope * 0.35
        out.append(max(-1.0, min(1.0, value + noise.gauss(0, 0.01))))
    return out


def s16(samples, order="<") -> bytes:
    return b"".join(struct.pack(f"{order}h", int(value * 32000)) for value in samples)


def stream(data: bytes, bytes_per_second: int, frame: int = 8000) -> AudioSniffer:
    """Deliver `data` in real time at the given byte rate."""
    clock = Clock()
    sniffer = AudioSniffer(clock=clock)
    for start in range(0, len(data), frame):
        chunk = data[start:start + frame]
        sniffer.feed(chunk)
        clock.now += len(chunk) / bytes_per_second
    return sniffer


class ReadingTests(unittest.TestCase):
    def label(self, data: bytes, rate: int) -> dict:
        return stream(data, rate).snapshot()

    def test_signed_16_bit_mono_and_its_rate(self):
        for rate in (8000, 16000, 24000):
            with self.subTest(rate=rate):
                found = self.label(s16(voiced(rate * 4, rate)), rate * 2)
                self.assertEqual((found["encoding"], found["channels"], found["sample_rate"]),
                                 ("pcm_s16le", 1, rate))
                self.assertEqual(found["confidence"], "likely")
                self.assertIn("mono", found["label"])

    def test_byte_order_is_read_not_assumed(self):
        found = self.label(s16(voiced(64000, 16000), ">"), 32000)
        self.assertEqual(found["encoding"], "pcm_s16be")

    def test_eight_bit_samples_are_not_mistaken_for_sixteen(self):
        data = bytes(int(value * 100 + 128) for value in voiced(64000, 16000))
        found = self.label(data, 16000)
        self.assertEqual((found["encoding"], found["sample_rate"]), ("pcm_u8", 16000))

    def test_companded_samples_are_recognised(self):
        def encode(table_id):
            def one(value):
                target = int(value * 8000)
                best = min(range(256), key=lambda code: abs(table_id(code) - target))
                return best
            return bytes(one(value) for value in voiced(32000, 8000))
        for name, decode in (("g711_ulaw", _mulaw), ("g711_alaw", _alaw)):
            with self.subTest(name=name):
                self.assertEqual(self.label(encode(decode), 8000)["encoding"], name)

    def test_interleaved_stereo_is_told_from_mono(self):
        left, right = voiced(64000, 16000), voiced(64000, 16000, pitch=211)
        both = b"".join(struct.pack("<hh", int(a * 32000), int(b * 32000))
                        for a, b in zip(left, right))
        found = self.label(both, 64000)
        self.assertEqual((found["channels"], found["sample_rate"]), (2, 16000))
        duplicated = b"".join(struct.pack("<hh", int(a * 32000), int(a * 32000)) for a in left)
        self.assertEqual(self.label(duplicated, 64000)["channels"], 2)

    def test_a_rate_that_is_not_standard_is_said_so(self):
        found = self.label(s16(voiced(60000, 16000)), 2 * 20000)
        self.assertIsNone(found["sample_rate"])
        self.assertIn("not a standard rate", found["label"])

    def test_level_follows_the_signal(self):
        loud = self.label(s16(voiced(64000, 16000)), 32000)["level_db"]
        quiet = self.label(s16([v * 0.05 for v in voiced(64000, 16000)]), 32000)["level_db"]
        self.assertLess(-3, loud + 20)
        self.assertLess(quiet, loud - 20)


class NotSamplesTests(unittest.TestCase):
    def test_random_bytes_are_compressed_or_encrypted(self):
        rng = random.Random(2)
        found = stream(bytes(rng.randrange(256) for _ in range(64000)), 32000).snapshot()
        self.assertEqual(found["encoding"], "opaque")
        self.assertIn("compressed or encrypted", found["label"])

    def test_fixed_size_opaque_frames_are_described_by_size_rate_and_bit_rate(self):
        # The shape one real client streams: 40-byte compressed frames, a hundred a second.
        rng = random.Random(3)
        found = stream(bytes(rng.randrange(256) for _ in range(12000)), 4000, frame=40).snapshot()
        self.assertEqual((found["encoding"], found["frame_size"]), ("opaque", 40))
        self.assertIn("40-byte frames, 100 a second · 32 kbit/s", found["basis"])

    def test_silence_is_waiting_not_a_format(self):
        found = stream(b"\x00" * 64000, 32000).snapshot()
        self.assertEqual((found["label"], found["confidence"]), ("Silence", "waiting"))

    def test_too_little_data_is_not_judged(self):
        sniffer = AudioSniffer(clock=Clock())
        sniffer.feed(s16(voiced(500, 16000)))
        self.assertEqual(sniffer.snapshot()["confidence"], "waiting")

    def test_an_mp3_sync_word_over_noise_is_named(self):
        rng = random.Random(3)
        data = b"\xff\xfb\x90\x00" + bytes(rng.randrange(256) for _ in range(20000))
        self.assertIn("MP3", stream(data, 16000).snapshot()["label"])


class ContainerTests(unittest.TestCase):
    def test_a_wav_header_states_the_format(self):
        header = (b"RIFF" + struct.pack("<I", 0) + b"WAVEfmt "
                  + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
                  + b"data" + struct.pack("<I", 0))
        found = stream(header + s16(voiced(4000, 16000)), 32000).snapshot()
        self.assertEqual((found["encoding"], found["confidence"], found["sample_rate"]),
                         ("wav", "certain", 16000))
        self.assertEqual(found["label"], "WAV · mono · 16 kHz · 16-bit")

    def test_ogg_names_its_codec(self):
        found = stream(b"OggS\x00\x02" + b"\x00" * 20 + b"OpusHead" + b"\x00" * 100,
                       8000).snapshot()
        self.assertEqual((found["encoding"], found["label"]), ("ogg", "Ogg · Opus"))


class LiveTests(unittest.TestCase):
    def test_a_change_of_description_is_reported_once(self):
        clock = Clock()
        sniffer = AudioSniffer(clock=clock)
        data = s16(voiced(64000, 16000))
        changes = 0
        for start in range(0, len(data), 8000):
            changes += sniffer.feed(data[start:start + 8000])
            clock.now += 0.25
        self.assertGreaterEqual(changes, 1)
        self.assertLessEqual(changes, 3, "the label settles instead of flickering")

    def test_a_settled_description_survives_one_odd_reading(self):
        clock = Clock()
        sniffer = AudioSniffer(clock=clock)
        speech = s16(voiced(160000, 16000))
        noise = random.Random(4)
        labels = []
        for index, start in enumerate(range(0, len(speech), 8000)):
            frame = speech[start:start + 8000]
            if index == 10:
                frame = bytes(noise.randrange(256) for _ in range(8000))
            sniffer.feed(frame)
            labels.append(sniffer.snapshot()["label"])
            clock.now += 0.25
        settled = [label for label in labels if "16 kHz" in label]
        self.assertTrue(settled)
        first = labels.index(settled[0])
        # Once settled it stays, through the noise, to the end of the stream.
        self.assertEqual(set(labels[first:]), {settled[0]})

    def test_throughput_falls_to_zero_once_the_audio_stops(self):
        clock = Clock()
        sniffer = AudioSniffer(clock=clock)
        data = s16(voiced(64000, 16000))
        for start in range(0, len(data), 8000):
            sniffer.feed(data[start:start + 8000])
            clock.now += 0.25
        self.assertGreater(sniffer.snapshot()["bytes_per_second"], 20000)
        clock.now += 5
        self.assertEqual(sniffer.snapshot()["bytes_per_second"], 0)

    def test_the_window_is_bounded(self):
        sniffer = AudioSniffer(clock=Clock())
        for _ in range(100):
            sniffer.feed(b"\x01\x02" * 4000)
        self.assertLessEqual(len(sniffer.window), 16384)
        self.assertEqual(sniffer.total, 800000)


if __name__ == "__main__":
    unittest.main()
