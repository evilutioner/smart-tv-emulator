"""Smart TV platform registry, discovered from the packages in this directory.

No platform is named here. A package under `platforms/` that exports `PLATFORM` (a
`PlatformDescriptor`) and `ADAPTER` (its adapter class) is a platform, so the directory
listing is the id list. That is what lets one build ship a single adapter and another ship
eight from this same file. Display order is `PlatformDescriptor.order`, so a build that
ships a subset still has a stable selector and a stable default.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from functools import lru_cache

from tvemu.core import Core

from .base import PlatformAdapter, PlatformDescriptor
from .catalogue import CatalogueEntry, catalogue_entry, catalogue_ids, request_url

# Packages beside the platforms that are shared machinery rather than a television.
_RESERVED = frozenset({"base", "catalogue", "common"})

# Packages present but not loadable, by id. Never fatal: the process serves whatever else
# imported, which keeps one broken adapter from taking the whole bench down.
_errors: dict[str, str] = {}

# Ids a build has been asked to serve, or None for "everything present". Set by
# `restrict_to`, which is how a source tree previews a build that ships fewer platforms.
_only: frozenset[str] | None = None


class PlatformUnavailable(LookupError):
    """A catalogued platform this build does not ship.

    Deliberately not a `ValueError`: the control API answers an unknown id with 400 and this
    with its own status, so the shared handler for malformed input must not swallow it.
    """

    def __init__(self, entry: CatalogueEntry):
        self.entry = entry
        super().__init__(f"{entry.display_name} is not part of this build")


@lru_cache(maxsize=None)
def _registry() -> dict[str, tuple[PlatformDescriptor, type]]:
    found: list[tuple[PlatformDescriptor, type]] = []
    for info in pkgutil.iter_modules(__path__):
        if not info.ispkg or info.name.startswith("_") or info.name in _RESERVED:
            continue
        if _only is not None and info.name not in _only:
            continue
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
            descriptor, adapter = module.PLATFORM, module.ADAPTER
        except Exception as exc:
            _errors[info.name] = f"{type(exc).__name__}: {exc}"
            print(f"tvemu: platform {info.name!r} unavailable: {exc}", file=sys.stderr)
            continue
        if descriptor.id != info.name:
            # The id is also a directory name and the dashboard module's path, so a
            # mismatch is a packaging fault rather than a platform that can serve.
            _errors[info.name] = f"package declares id {descriptor.id!r}"
            continue
        found.append((descriptor, adapter))
    found.sort(key=lambda item: (item[0].order, item[0].id))
    return {descriptor.id: (descriptor, adapter) for descriptor, adapter in found}


def restrict_to(platform_ids) -> None:
    """Serve only these platforms, as a build that shipped just them would.

    The ids come from a build manifest rather than from shared code, so this previews a
    smaller build without anything here knowing which televisions exist.
    """
    global _only
    _only = frozenset(platform_ids)
    _errors.clear()
    _registry.cache_clear()


def platform_errors() -> dict[str, str]:
    _registry()
    return dict(_errors)


def platform_ids() -> tuple[str, ...]:
    """The platforms this build can actually run, in display order."""
    return tuple(_registry())


def default_platform() -> str:
    ids = platform_ids()
    if not ids:
        raise RuntimeError(f"No TV platform could be loaded: {platform_errors() or 'none found'}")
    return ids[0]


def locked_ids() -> tuple[str, ...]:
    """Catalogued platforms this build does not include, in display order.

    Derived rather than stored, so a build that ships everything withholds nothing and has
    no way to claim otherwise.
    """
    live = _registry()
    return tuple(pid for pid in catalogue_ids() if pid not in live)


def platform_choices() -> tuple[dict[str, object], ...]:
    """Every platform this build presents to the dashboard, runnable or not."""
    live = _registry()
    rows: list[tuple[int, dict[str, object]]] = [
        (descriptor.order,
         {"id": descriptor.id, "display_name": descriptor.display_name,
          "availability": "available", "summary": descriptor.protocol_label})
        for descriptor, _ in live.values()]
    for platform_id in locked_ids():
        entry = catalogue_entry(platform_id)
        rows.append((entry.order,
                     {"id": entry.id, "display_name": entry.display_name,
                      "availability": "n/a", "summary": entry.summary,
                      "devices": entry.devices, "docs": entry.docs,
                      "contact": request_url()}))
    rows.sort(key=lambda row: (row[0], row[1]["id"]))
    return tuple(row for _, row in rows)


def platform_descriptor(platform_id: str) -> PlatformDescriptor:
    entry = _registry().get(platform_id)
    if entry is not None:
        return entry[0]
    locked = catalogue_entry(platform_id) if platform_id in locked_ids() else None
    if locked is not None:
        raise PlatformUnavailable(locked)
    raise ValueError(f"Unknown TV platform: {platform_id}")


def create_platform(platform_id: str, core: Core) -> PlatformAdapter:
    entry = _registry().get(platform_id)
    if entry is None:
        platform_descriptor(platform_id)   # raises whichever of the two applies
    return entry[1](core)


__all__ = ["PlatformAdapter", "PlatformDescriptor", "PlatformUnavailable", "create_platform",
           "default_platform", "locked_ids", "platform_choices", "platform_descriptor",
           "platform_errors", "platform_ids", "restrict_to"]
