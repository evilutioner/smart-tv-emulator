"""Roku wire protocols, separate from the dashboard control API."""

from .adapter import ROKU, RokuAdapter

# The registry's contract. The names above stay for this platform's own
# modules and tests, which import them directly.
PLATFORM, ADAPTER = ROKU, RokuAdapter

__all__ = ["ADAPTER", "PLATFORM", "ROKU", "RokuAdapter"]
