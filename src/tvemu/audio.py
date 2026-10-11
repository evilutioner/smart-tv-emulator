"""Working out what an incoming audio stream is, from the stream alone.

A protocol that carries voice rarely says what its bytes are, so a driver author has had to
capture a session and inspect it by hand. This module does that while the audio arrives. It
keeps a short window of the most recent bytes in memory, never on disk and never in a snapshot,
and answers with a description and how sure it is.

Three kinds of evidence are used, and the answer says which one it rests on:

- a container header (RIFF/WAVE, Ogg, FLAC, MP3, ADTS, Matroska), which is certain;
- for bare samples, how *smooth* the signal is under each way of reading the bytes. Real audio
  changes little from one sample to the next, while the same bytes read with the wrong width,
  byte order or channel count look like noise. This is a heuristic, and is labelled one;
- the arrival rate, which turns bytes per second into a sample rate when the sender streams in
  real time. A sender that bursts makes it wrong, so it is labelled as measured, not read.
"""
from __future__ import annotations

import math
import struct
import sys
import time
from array import array
from collections import deque

WINDOW = 16384
HEAD = 64
# The signal is re-read at most this often, and only once this much new audio has arrived.
INTERVAL = 0.5
MIN_NEW = 2048
MIN_WINDOW = 4096
# The slice of the window the live level is taken from, so the meter follows the voice.
LEVEL_BYTES = 4096
# Mean absolute step over standard deviation: about 1.1 for noise, well under 0.5 for audio.
SAMPLE_LIKE = 0.6
LIKELY = 0.35
# A reading of 8-bit samples, or of a different channel count, has to beat the preferred
# one by this factor: the wrong readings of 16-bit audio are only rarely much smoother.
CLEAR_WIN = 0.7
SILENT = 24 / 32768
RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)
SNAP = 0.04
MIN_SPAN = 1.5
MIN_FRAMES = 4
RECENT = 3.0


def _companded(decode) -> list[float]:
    return [decode(value) / 32768 for value in range(256)]


def _mulaw(value: int) -> int:
    value = ~value & 0xFF
    magnitude = (((value & 0x0F) << 3) + 0x84 << ((value & 0x70) >> 4)) - 0x84
    return -magnitude if value & 0x80 else magnitude


def _alaw(value: int) -> int:
    value ^= 0x55
    exponent = (value & 0x70) >> 4
    mantissa = value & 0x0F
    magnitude = (mantissa << 4) + 8 if exponent == 0 else ((mantissa << 4) + 0x108) << (exponent - 1)
    return magnitude if value & 0x80 else -magnitude


MULAW = _companded(_mulaw)
ALAW = _companded(_alaw)

# (id, description, bytes per sample). The order is the order of preference.
READINGS = (
    ("pcm_s16le", "PCM signed 16-bit little-endian", 2),
    ("pcm_s16be", "PCM signed 16-bit big-endian", 2),
    ("pcm_u8", "PCM unsigned 8-bit", 1),
    ("g711_ulaw", "G.711 µ-law 8-bit", 1),
    ("g711_alaw", "G.711 A-law 8-bit", 1),
)


def _container(head: bytes) -> tuple[str, str] | None:
    """The container a stream opens with, as (id, description), or None for bare data."""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav", "WAV"
    if head[:4] == b"OggS":
        codec = ("Opus" if b"OpusHead" in head else "Vorbis" if b"vorbis" in head
                 else "Speex" if b"Speex" in head else "unknown codec")
        return "ogg", f"Ogg · {codec}"
    if head[:4] == b"fLaC":
        return "flac", "FLAC"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska", "Matroska / WebM"
    return None


def _framed(head: bytes) -> tuple[str, str] | None:
    """MP3 and ADTS begin with a sync word that bare samples can also produce by chance."""
    if head[:3] == b"ID3" or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
                              and head[1] & 0x06 in (0x02, 0x04, 0x06)):
        return "mp3", "MP3"
    if len(head) > 1 and head[0] == 0xFF and head[1] & 0xF6 == 0xF0:
        return "aac_adts", "AAC (ADTS)"
    return None


def _wav_format(head: bytes) -> dict:
    """What a canonical RIFF header states: channels, rate and bits, when it is intact."""
    position = 12
    while position + 8 <= len(head):
        name, size = head[position:position + 4], struct.unpack_from("<I", head, position + 4)[0]
        if name == b"fmt " and position + 24 <= len(head):
            tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", head, position + 8)
            return {"tag": tag, "channels": channels, "sample_rate": rate, "bits": bits}
        position += 8 + size + (size & 1)
    return {}


def _step_ratio(samples) -> float | None:
    """Mean absolute step over standard deviation; None when the signal is too quiet to judge."""
    count = len(samples)
    if count < 64:
        return None
    mean = sum(samples) / count
    variance = sum((value - mean) ** 2 for value in samples) / count
    deviation = math.sqrt(variance)
    if deviation < SILENT:
        return None
    steps = sum(abs(b - a) for a, b in zip(samples, samples[1:])) / (count - 1)
    return steps / deviation


def _asymmetry(samples) -> float:
    """How unequal the steps into even and odd samples are: large for duplicated stereo."""
    even = sum(abs(samples[i] - samples[i - 1]) for i in range(2, len(samples), 2))
    odd = sum(abs(samples[i] - samples[i - 1]) for i in range(1, len(samples), 2))
    low, high = sorted((even, odd))
    return high / low if low else (math.inf if high else 1.0)


def _decode(reading: str, data: bytes) -> list[float]:
    if reading in ("pcm_s16le", "pcm_s16be"):
        data = data[:len(data) // 2 * 2]
        samples = array("h")
        samples.frombytes(data)
        if (reading == "pcm_s16le") != (sys.byteorder == "little"):
            samples.byteswap()
        return [value / 32768 for value in samples]
    if reading == "pcm_u8":
        return [(value - 128) / 128 for value in data]
    return [(MULAW if reading == "g711_ulaw" else ALAW)[value] for value in data]


def _split(samples: list[float], channels: int) -> list[list[float]]:
    return [samples[index::channels] for index in range(channels)]


def _label_rate(rate: float) -> tuple[int | None, str]:
    """A measured sample rate as (standard rate or None, how it reads)."""
    for standard in RATES:
        if abs(rate / standard - 1) <= SNAP:
            return standard, f"{standard / 1000:g} kHz"
    return None, f"{rate / 1000:.1f} kHz, not a standard rate"


class AudioSniffer:
    """Feed it the audio as it arrives; ask it what the audio is."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.head = b""
        self.window = bytearray()
        # The stream offset of the window's first byte, so a slice can start on a sample.
        self.offset = 0
        self.total = 0
        self.frames = 0
        self.first_size = 0
        # Every frame's size while they are all the same, 0 once one differs: a codec that
        # sends fixed-size frames is described by that size even when its bytes say nothing.
        self.frame_size = 0
        self.first_at: float | None = None
        self.last_at: float | None = None
        self.recent: deque[tuple[float, int]] = deque()
        self.checked_at = 0.0
        self.checked_total = 0
        self.result: dict | None = None
        self.changed = False
        # A different description has to be read twice running before it replaces a settled one.
        self.pending: str | None = None

    def feed(self, data: bytes) -> bool:
        """Take one frame. True when what the stream is described as just changed."""
        if not data:
            return False
        now = self.clock()
        if self.first_at is None:
            self.first_at, self.first_size = now, len(data)
            self.frame_size = len(data)
        elif len(data) != self.frame_size:
            self.frame_size = 0
        self.last_at = now
        self.frames += 1
        self.total += len(data)
        if len(self.head) < HEAD:
            self.head = (self.head + data)[:HEAD]
        self.window += data
        if len(self.window) > WINDOW:
            drop = len(self.window) - WINDOW
            del self.window[:drop]
            self.offset += drop
        self.recent.append((now, len(data)))
        while self.recent and now - self.recent[0][0] > RECENT:
            self.recent.popleft()
        if (now - self.checked_at >= INTERVAL and self.total - self.checked_total >= MIN_NEW) \
                or self.result is None:
            self.checked_at, self.checked_total = now, self.total
            return self._read()
        return False

    # ── reading ───────────────────────────────────────────────────────────────────────
    def _rate(self, bytes_per_sample: int, channels: int) -> tuple[float | None, float]:
        """The sample rate the arrival rate implies, and the arrival rate itself."""
        recent = self.recent
        span = recent[-1][0] - recent[0][0] if len(recent) > 1 else 0.0
        per_second = sum(size for _, size in list(recent)[1:]) / span if span > 0 else 0.0
        whole = (self.last_at or 0) - (self.first_at or 0)
        if self.frames >= MIN_FRAMES and whole >= MIN_SPAN:
            # The first frame arrived with no time before it, so it does not count.
            per_second = (self.total - self.first_size) / whole
            return per_second / (bytes_per_sample * channels), per_second
        return None, per_second

    def _framing(self, per_second: float) -> str:
        """What arrival alone says about opaque audio: frame size, frame rate and bit rate."""
        if self.frames < MIN_FRAMES or per_second <= 0:
            return ""
        text = f" · {per_second * 8 / 1000:.0f} kbit/s"
        if self.frame_size:
            text = (f" · {self.frame_size}-byte frames, {per_second / self.frame_size:.0f} a "
                    f"second" + text)
        return text

    def _slice(self) -> bytes:
        """The window from a whole number of frames after the stream began."""
        skip = -self.offset % 4
        return bytes(self.window[skip:])

    def _read(self) -> bool:
        """Describe the stream. True when the description differs from the last one.

        A description that is settled (sure, and with its rate) is not dropped for one odd
        reading: a burst of noise or a rate measured over a short stretch would otherwise make
        the label flicker as someone speaks. The new reading has to come up twice running.
        """
        found = self._describe()
        previous = self.result
        settled = (previous is not None and previous["confidence"] in ("likely", "certain")
                   and "rate unknown" not in previous["label"])
        if settled and found["label"] != previous["label"] and found["confidence"] != "certain":
            if found["label"] != self.pending:
                self.pending = found["label"]
                # Keep what was settled, with the live figures of this reading.
                live = {key: found[key] for key in
                        ("bytes", "frames", "bytes_per_second", "level_db", "peak_db")
                        if key in found}
                self.result = {**previous, **live}
                self.changed = False
                return False
        self.pending = None
        changed = previous is None or found["label"] != previous["label"]
        self.result = found
        self.changed = changed
        return changed

    def _describe(self) -> dict:
        base = {"bytes": self.total, "frames": self.frames}
        container = _container(self.head)
        if container is not None:
            identity, description = container
            stated = _wav_format(self.head) if identity == "wav" else {}
            channels, rate = stated.get("channels"), stated.get("sample_rate")
            label = description
            if rate and channels:
                layout = {1: "mono", 2: "stereo"}.get(channels, f"{channels} channels")
                label += f" · {layout} · {rate / 1000:g} kHz"
                if stated.get("bits"):
                    label += f" · {stated['bits']}-bit"
            return {**base, "encoding": identity, "label": label, "channels": channels,
                    "sample_rate": rate, "confidence": "certain", "basis": "container header",
                    "bytes_per_second": round(self._rate(2, 1)[1]), "level_db": None}

        data = self._slice()
        if len(data) < MIN_WINDOW:
            return {**base, "encoding": None, "label": "Listening…", "channels": None,
                    "sample_rate": None, "confidence": "waiting", "basis": "too little data",
                    "bytes_per_second": round(self._rate(2, 1)[1]), "level_db": None}

        scored = []
        for identity, description, width in READINGS:
            samples = _decode(identity, data)
            for channels in (1, 2):
                parts = _split(samples, channels)
                ratios = [_step_ratio(part) for part in parts]
                if any(ratio is None for ratio in ratios):
                    continue
                score = sum(ratios) / channels
                if channels == 2 and _asymmetry(samples) > 3:
                    score = 0.0
                scored.append((identity, description, width, channels, score, samples))
        if not scored:
            return {**base, "encoding": None, "label": "Silence", "channels": None,
                    "sample_rate": None, "confidence": "waiting",
                    "basis": "no signal to judge yet",
                    "bytes_per_second": round(self._rate(2, 1)[1]), "level_db": None}

        best = self._choose(scored)
        identity, description, width, channels, score, samples = best
        per_second = self._rate(width, channels)[1]
        if score > SAMPLE_LIKE:
            framed = _framed(self.head)
            label = f"{framed[1]} (no container)" if framed else "Not sample-like: compressed or encrypted"
            basis = "sync word" if framed else "no reading of the bytes is smooth"
            return {**base, "encoding": framed[0] if framed else "opaque", "label": label,
                    "channels": None, "sample_rate": None,
                    "confidence": "likely" if framed else "guess",
                    "basis": basis + self._framing(per_second),
                    "frame_size": self.frame_size or None,
                    "bytes_per_second": round(per_second), "level_db": None}
        rate, rate_text = (None, "rate unknown")
        measured = self._rate(width, channels)[0]
        if measured:
            rate, rate_text = _label_rate(measured)
        layout = "mono" if channels == 1 else "stereo, interleaved"
        recent = samples[-LEVEL_BYTES // width:]
        rms = math.sqrt(sum(value * value for value in recent) / max(1, len(recent)))
        peak = max((abs(value) for value in recent), default=0)
        return {**base, "encoding": identity,
                "label": f"{description} · {layout} · {rate_text}",
                "channels": channels, "sample_rate": rate,
                "sample_rate_measured": round(measured) if measured else None,
                "confidence": "likely" if score < LIKELY and not identity.startswith("g711")
                else "guess",
                "basis": f"sample smoothness {score:.2f}; rate from arrival",
                "bytes_per_second": round(per_second),
                "level_db": round(20 * math.log10(rms), 1) if rms > 0 else None,
                "peak_db": round(20 * math.log10(peak), 1) if peak > 0 else None}

    @staticmethod
    def _choose(scored: list) -> tuple:
        """The smoothest reading, with the preferred ones given the benefit of the doubt.

        16-bit before 8-bit and mono before stereo: the wrong readings of 16-bit audio are only
        rarely much smoother, so something else has to be clearly better to be chosen.
        """
        best = min(item[4] for item in scored)
        order = {name: index for index, (name, _, _) in enumerate(READINGS)}
        chosen = min(scored, key=lambda item: item[4])
        for candidate in sorted(scored, key=lambda item: (order[item[0]], item[3])):
            if candidate[4] <= best / CLEAR_WIN:
                chosen = candidate
                break
        if chosen[0].startswith("g711"):
            # The two companding laws decode each other's bytes into a similar signal, so
            # there is no benefit of the doubt between them: the smoother reading wins.
            chosen = min((item for item in scored if item[0].startswith("g711")
                          and item[3] == chosen[3]), key=lambda item: item[4])
        return chosen

    def snapshot(self) -> dict | None:
        """The current description and live figures, never any audio."""
        if self.result is None:
            return None
        per_second = self.result["bytes_per_second"]
        if self.recent and self.clock() - self.recent[-1][0] > 1.0:
            per_second = 0
        return {**self.result, "bytes_per_second": per_second}
