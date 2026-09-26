"""A minimal second platform, for tests only.

Switching platforms, reconciling protocols and clearing state between televisions is
shared machinery, so it must stay under test in a build that ships a single television.
This package is never installed: `tests/support.install_stub_platform` appends it to the
registry's search path for the duration of a test.
"""
from .adapter import STUBTV, StubTVAdapter

PLATFORM, ADAPTER = STUBTV, StubTVAdapter

__all__ = ["ADAPTER", "PLATFORM", "STUBTV", "StubTVAdapter"]
