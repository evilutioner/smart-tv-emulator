"""The televisions this product models, whether or not this build can run them.

Data, not code. `catalogue.json` is hand-maintained beside this module and ships unchanged
to every build, so a build that lacks a platform's package can still name it, summarise it,
and point at its guide. Which entries are locked is never stored: the registry derives it
from the packages actually present, so a build that ships everything locks nothing.

It is also the one source of every count and list the published text states — the README's
television table, badges and generation timelines and the table in `docs/televisions.md` are
generated from it by `tools/render_docs.py`. Each captured device names the profile ids it
stands for, and a build that runs a platform checks those ids and the protocol count against
the code, so the catalogue cannot drift from what it describes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CATALOGUE = Path(__file__).with_name("catalogue.json")

# Where a reader is sent to ask about a television this build does not include. Overridden
# by the catalogue file so the address lives with the rest of the published text.
DEFAULT_REQUEST_URL = "https://marchik.dev"

# What kind of device a platform is, in the order the dashboard groups them. A platform the
# catalogue does not know is presented as a television.
KINDS = ("tv", "projector", "console")


@dataclass(frozen=True)
class CapturedDevice:
    name: str
    detail: str = ""
    profiles: tuple[str, ...] = ()
    # Modelled from a vendor's client rather than measured on a set: it is a selectable
    # profile, but no published count may call it a captured device.
    modelled: bool = False
    # A real remote app was driven against it and recorded in docs/manual-validation.md.
    validated: bool = False

    @property
    def label(self) -> str:
        """The device as one line: several captures of one model, or none, say so."""
        count = len(self.profiles)
        if self.modelled:
            return f"{self.name} (modelled)"
        return self.name if count < 2 else f"{self.name} ({count} captures)"


@dataclass(frozen=True)
class Generation:
    """One remote-control stack a platform's firmwares have shipped, oldest first.

    `era` groups generations a reader knows by one name, such as the operating system a
    vendor's sets ran at the time; without one a generation is its own era. `years` is the span
    of model years, when the sets are dated at all.
    """

    name: str
    era: str = ""
    years: tuple[int, int] | None = None

    @property
    def family(self) -> str:
        return self.era or self.name


@dataclass(frozen=True)
class Link:
    """Something named in the published text, and where a reader finds it."""

    name: str
    url: str = ""


@dataclass(frozen=True)
class CatalogueEntry:
    id: str
    display_name: str
    summary: str
    kind: str = "tv"
    # The platform a build starts with when it ships it; at most one entry says so.
    default: bool = False
    docs: str = ""
    remote: str = ""
    discovery: str = ""
    pairing: str = ""
    protocols: int = 0
    generations: tuple[Generation, ...] = ()
    captured: tuple[CapturedDevice, ...] = ()
    # Open-source client libraries that drive it, each with a passing recorded run under
    # docs/clients/; the open-source counterpart of a device's `validated`.
    clients: tuple[Link, ...] = ()
    # The vendors' own remote apps driven against it by hand, named as the
    # docs/manual-validation.md ledger names them, each with its store page.
    apps: tuple[Link, ...] = ()

    @property
    def devices(self) -> str:
        return ", ".join(device.label for device in self.captured)

    @property
    def profile_ids(self) -> tuple[str, ...]:
        return tuple(profile for device in self.captured for profile in device.profiles)


@lru_cache(maxsize=1)
def _document() -> dict:
    try:
        document = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if document.get("schema_version") == 2 else {}


@lru_cache(maxsize=1)
def catalogue_entries() -> tuple[CatalogueEntry, ...]:
    """Every catalogued platform, in display order: by kind, then by name.

    A missing or unreadable catalogue yields nothing rather than failing: the emulator then
    runs exactly as before and only the upsell disappears.
    """
    rows = _document().get("platforms") or []
    entries = [CatalogueEntry(id=row["id"], display_name=row["display_name"],
                              kind=str(row.get("kind") or "tv"),
                              default=row.get("default") is True,
                              summary=row.get("summary", ""),
                              docs=row.get("docs", ""), remote=row.get("remote", ""),
                              discovery=row.get("discovery", ""),
                              pairing=row.get("pairing", ""),
                              protocols=int(row.get("protocols", 0)),
                              generations=tuple(_generation(item)
                                                for item in row.get("generations") or []
                                                if isinstance(item, dict) and item.get("name")),
                              clients=_links(row.get("clients")),
                              apps=_links(row.get("apps")),
                              captured=tuple(_device(item) for item in row.get("captured") or []
                                             if isinstance(item, dict) and item.get("name")))
               for row in rows if isinstance(row, dict) and row.get("id")]
    return tuple(sorted(entries, key=lambda entry: display_key(entry.id, entry.display_name,
                                                              entry.kind)))


def display_key(platform_id: str, display_name: str, kind: str = "tv") -> tuple:
    """Where a platform sits in the selector: grouped by kind, then by name."""
    rank = KINDS.index(kind) if kind in KINDS else len(KINDS)
    return rank, display_name.casefold(), platform_id


def _links(rows) -> tuple[Link, ...]:
    return tuple(Link(name=str(row["name"]), url=str(row.get("url") or ""))
                 for row in rows or () if isinstance(row, dict) and row.get("name"))


def _generation(row: dict) -> Generation:
    years = row.get("years")
    return Generation(name=str(row["name"]), era=str(row.get("era") or ""),
                      years=(int(years[0]), int(years[-1])) if years else None)


def _device(row: dict) -> CapturedDevice:
    return CapturedDevice(name=row["name"], detail=row.get("detail", ""),
                          profiles=tuple(row.get("profiles") or ()),
                          modelled=row.get("modelled") is True,
                          validated=row.get("validated") is True)


def catalogue_ids() -> tuple[str, ...]:
    return tuple(entry.id for entry in catalogue_entries())


def catalogue_entry(platform_id: str) -> CatalogueEntry | None:
    return next((entry for entry in catalogue_entries() if entry.id == platform_id), None)


def platform_kind(platform_id: str) -> str:
    entry = catalogue_entry(platform_id)
    return entry.kind if entry else "tv"


def default_id() -> str | None:
    return next((entry.id for entry in catalogue_entries() if entry.default), None)


def request_url() -> str:
    return str(_document().get("request_url") or DEFAULT_REQUEST_URL)


__all__ = ["KINDS", "CapturedDevice", "CatalogueEntry", "Generation", "Link", "catalogue_entries",
           "catalogue_entry", "catalogue_ids", "default_id", "display_key", "platform_kind", "request_url"]
