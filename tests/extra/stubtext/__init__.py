"""A second test-only platform, one that carries text and voice over its wire.

Its purpose is coverage rather than fidelity. `core.text()`, the `/api/v1/actions/text`
and `/field` endpoints and the voice bookkeeping are all shared code that ships in every
build, so they must stay under test in a build whose one real television happens to type
with per-character keypresses and has no microphone.
"""
from .adapter import STUBTEXT, StubTextAdapter

PLATFORM, ADAPTER = STUBTEXT, StubTextAdapter

__all__ = ["ADAPTER", "PLATFORM", "STUBTEXT", "StubTextAdapter"]
