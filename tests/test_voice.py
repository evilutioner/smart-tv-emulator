from __future__ import annotations

import unittest
from pathlib import Path

from tests.support import NO_VOICE, VOICE_STREAM, needs
from tvemu.core import Core, Settings
from tvemu.platforms import platform_descriptor
from tvemu.platforms.base import VoiceSpec


class VoiceStateTests(unittest.TestCase):
    """Voice bookkeeping is shared state, so every case here picks its platform by
    declared capability rather than by name."""

    def setUp(self):
        self.streaming = platform_descriptor(needs(VOICE_STREAM, "a streaming voice input"))

    def test_shared_stream_lifecycle_keeps_only_metrics_and_completed_summary(self):
        core = Core(self.streaming, Settings())
        spec = self.streaming.voice
        self.assertEqual(core.snapshot()["voice"], {
            "label": spec.label,
            "mode": spec.mode,
            "format": spec.audio_format,
            "state": "idle",
            "active": False,
            "session_id": "",
            "chunks": 0,
            "bytes": 0,
            "started_at": "",
            "ended_at": "",
            "duration_ms": 0,
            "detail": "",
            "transport": "",
        })

        self.assertTrue(core.voice_begin(7, owner="client-1", transport="test"))
        self.assertFalse(core.voice_begin(8, owner="client-2", transport="test"))
        self.assertTrue(core.voice_ready(7, owner="client-1", transport="test"))
        self.assertTrue(core.voice_payload(7, 8192, owner="client-1", transport="test"))
        self.assertTrue(core.voice_payload(7, 20480, owner="client-1", transport="test"))
        self.assertTrue(core.voice_end(7, owner="client-1", transport="test"))

        voice = core.snapshot()["voice"]
        self.assertEqual((voice["state"], voice["active"]), ("completed", False))
        self.assertEqual((voice["chunks"], voice["bytes"]), (2, 28672))
        self.assertTrue(voice["started_at"])
        self.assertTrue(voice["ended_at"])
        self.assertGreaterEqual(voice["duration_ms"], 0)
        self.assertNotIn("samples", repr(core.snapshot()))

        core.reset()
        self.assertEqual(core.snapshot()["voice"]["state"], "idle")
        self.assertEqual(core.snapshot()["voice"]["bytes"], 0)

    def test_interruption_and_wrong_owner_are_isolated(self):
        core = Core(self.streaming, Settings())
        self.assertTrue(core.voice_begin("session", owner="one", transport="test"))
        self.assertFalse(core.voice_ready("session", owner="two", transport="test"))
        self.assertFalse(core.voice_interrupt(owner="two", transport="test"))
        self.assertTrue(core.voice_interrupt(owner="one", transport="test", detail="closed"))
        self.assertEqual(core.snapshot()["voice"]["state"], "interrupted")

    def test_platform_without_voice_has_no_snapshot_block(self):
        silent = platform_descriptor(needs(NO_VOICE, "no voice input"))
        core = Core(silent, Settings())
        self.assertIsNone(core.snapshot()["voice"])
        self.assertFalse(core.voice_begin(1, owner="client", transport="test"))
        # Retargeting is what a platform switch does, so the block has to appear on arrival.
        core.retarget(self.streaming)
        self.assertEqual(core.snapshot()["voice"]["state"], "idle")

    def test_voice_spec_rejects_invalid_contracts(self):
        with self.assertRaises(ValueError):
            VoiceSpec(label="Voice", mode="unknown")
        with self.assertRaises(ValueError):
            VoiceSpec(label="Voice", mode="stream")
        self.assertEqual(VoiceSpec(label="Voice", mode="trigger").audio_format, "")

    def test_dashboard_contains_generic_hidden_voice_tile(self):
        web = Path(__file__).parents[1] / "src/tvemu/web"
        html = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="voice-card" hidden', html)
        self.assertIn("function drawVoice(data)", script)
        self.assertIn('$("voice-card")', script)


if __name__ == "__main__":
    unittest.main()
