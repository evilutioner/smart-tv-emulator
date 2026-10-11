"""Fill the generated blocks of each platform guide from the emulator's own declarations.

A guide is for somebody deciding whether this television does what they need, so the parts a
reader could not have guessed are written by hand and the parts the code already knows are
written from the code. A hand-maintained route table drifts; this one cannot.

The same run writes `docs/spec/<id>.openapi.json` and `docs/spec/<id>.asyncapi.json`, the
machine contract a driver (or a model writing one) reads without starting the emulator. A
television whose ports answer the same request gets one `<id>.<application>.openapi.json`
per application instead.

It also fills the blocks that state counts and lists across televisions — the README's
badges and television table, and the detailed table in `docs/televisions.md` — from
`catalogue.json`, so a number is written in one place. "In this build" means the build the
README describes: the platforms `PUBLIC.toml` names where that manifest exists, else the ones
this tree runs.

Run with no arguments to rewrite every guide, or with platform ids to rewrite some. `--check`
rewrites nothing and reports which files have fallen behind, which is what the test runs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from urllib.parse import quote
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tvemu.platforms import platform_ids                       # noqa: E402
from tvemu.platforms.common import report                      # noqa: E402
from tvemu.platforms.catalogue import catalogue_entries        # noqa: E402

# Any guide under docs/ named after its platform and carrying generated blocks; a short
# overview without blocks is left alone.
DOCS = ROOT / "docs"
# Non-greedy across the whole block, and tolerant of an empty one: a guide is written
# with the markers and no body, then filled.
BLOCK = re.compile(r"<!-- generated:(\w+) -->.*?<!-- /generated -->", re.S)
SPEC = DOCS / "spec"
README = ROOT / "README.md"
TELEVISIONS = DOCS / "televisions.md"


def rendered(platform_id: str, name: str) -> str:
    surface = report.surface_of(platform_id)
    if surface is None:
        raise SystemExit(f"{platform_id} declares no surface, so its guide cannot be filled")
    if name == "surface":
        return report.markdown_surface(surface)
    if name == "contract":
        return report.markdown_contract(platform_id, surface)
    raise SystemExit(f"unknown generated block: {name}")


def fill(platform_id: str, text: str) -> str:
    return BLOCK.sub(
        lambda m: (f"<!-- generated:{m.group(1)} -->\n"
                   f"{rendered(platform_id, m.group(1))}\n"
                   "<!-- /generated -->"), text)


def published() -> set[str]:
    """The platforms the README's build ships."""
    from tvemu.__main__ import manifest_path
    path = manifest_path("public")
    if path is None:
        return set(platform_ids())
    return set(tomllib.loads(path.read_text(encoding="utf-8")).get("platforms") or [])


def _badge(label: str, message: str, alt: str) -> str:
    def part(text: str) -> str:
        return quote(text.replace("-", "--"), safe="")
    return (f'  <img alt="{alt}" '
            f'src="https://img.shields.io/badge/{part(label)}-{part(message)}-6c7a7e">')


def badges() -> str:
    entries = catalogue_entries()
    shipped = published()
    included = sum(entry.id in shipped for entry in entries)
    unavailable = len(entries) - included
    devices = sum(len(device.profiles) for entry in entries for device in entry.captured
                  if not device.modelled)
    validated = sum(len(device.profiles) for entry in entries for device in entry.captured
                    if device.validated)
    listeners = sum(entry.protocols for entry in entries)
    clients = sum(len(entry.clients) for entry in entries)
    return "\n".join([
        _badge("televisions", f"{included} included · {unavailable} N/A",
               f"{included} included, {unavailable} N/A"),
        _badge("captured devices", str(devices), f"{devices} captured devices"),
        _badge("validated with real apps", str(validated),
               f"{validated} devices validated with real apps"),
        _badge("tested with open-source clients", str(clients),
               f"tested with {clients} open-source clients"),
        _badge("protocol listeners", str(listeners), f"{listeners} protocol listeners"),
    ])


def _evidence(device) -> str:
    """How a device is known, as the icons the README's legend explains."""
    return ("📱" if device.modelled else "📡") + ("✅" if device.validated else "")


def _device_name(device) -> str:
    count = len(device.profiles)
    return f"**{device.name}**" + (f" ({count} captures)" if count > 1 else "")


def _tested_with(entry, docs: str) -> str:
    """What a television was tested with, each linked, with the report that says so.

    A vendor's app was driven by hand and its report is a ledger row; an open-source client
    runs every week and its report is the platform's page of recorded runs. Those pages ship
    for every television, included or not, so the link is there whenever the page is.
    """
    shipped = (ROOT / "docs" / "clients" / f"{entry.id}.md").is_file()
    tested = [f"✅ [{app.name}]({app.url}) · [report]({docs}manual-validation.md#ledger)"
              for app in entry.apps]
    tested += [f"🧪 [{client.name}]({client.url})"
               + (f" · [report]({docs}clients/{entry.id}.md#{client.name})" if shipped else "")
               for client in entry.clients]
    if (ROOT / "docs" / "tests" / f"{entry.id}.md").is_file():
        tested.append(f"🔬 [unit and replay tests]({docs}tests/{entry.id}.md)")
    return "<br>".join(tested) or "—"


def televisions() -> str:
    """The README's table: one line per television, devices marked by how they are known."""
    shipped = published()
    lines = ["| Television | What it speaks | Devices | Tested with |",
             "|---|---|---|---|"]
    for entry in catalogue_entries():
        devices = "<br>".join(f"{_evidence(device)} {_device_name(device)}"
                              for device in entry.captured)
        state = "**Included**" if entry.id in shipped else "N/A"
        lines.append(f"| **[{entry.display_name}]({entry.docs})**<br>{state} | "
                     f"{entry.summary} | {devices} | {_tested_with(entry, 'docs/')} |")
    return "\n".join(lines)


def television_details() -> str:
    """The full table in docs/televisions.md: ports, discovery, pairing and firmware."""
    shipped = published()
    lines = ["| Television | In this build | Remote control | Discovery | Pairing | Devices | "
             "Tested with |",
             "|---|---|---|---|---|---|---|"]
    for entry in catalogue_entries():
        devices = "<br>".join(
            f"{_evidence(device)} {_device_name(device)}"
            + (f" — {device.detail}" if device.detail and len(device.profiles) < 2 else "")
            for device in entry.captured)
        state = "**Included**" if entry.id in shipped else "N/A"
        docs = entry.docs.removeprefix("docs/")
        lines.append(f"| **[{entry.display_name}]({docs})** | {state} | {entry.remote} | "
                     f"{entry.discovery} | {entry.pairing} | {devices} | {_tested_with(entry, '')} |")
    return "\n".join(lines)


def shared() -> dict[Path, str]:
    """The files whose generated blocks come from the catalogue rather than one platform."""
    out: dict[Path, str] = {}
    renderers = {"badges": badges, "televisions": televisions,
                 "television_details": television_details}
    for path in (README, TELEVISIONS):
        if path.is_file():
            out[path] = BLOCK.sub(
                lambda m: (f"<!-- generated:{m.group(1)} -->\n{renderers[m.group(1)]()}\n"
                           "<!-- /generated -->"), path.read_text(encoding="utf-8"))
    return out


def _json(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def specs(platform_id: str) -> dict[Path, str]:
    """The OpenAPI and AsyncAPI files this platform's declarations produce."""
    surface = report.surface_of(platform_id)
    if surface is None:
        return {}
    out: dict[Path, str] = {}
    if surface.routes:
        for group, document in report.openapi_documents(platform_id, surface).items():
            name = f"{platform_id}.{group}.openapi.json" if group else f"{platform_id}.openapi.json"
            out[SPEC / name] = _json(document)
    if surface.messages:
        out[SPEC / f"{platform_id}.asyncapi.json"] = _json(report.asyncapi(platform_id, surface))
    return out


def expected(platform_id: str) -> dict[Path, str]:
    """Every generated file for one platform, as the code would write it now."""
    out: dict[Path, str] = {}
    for path in sorted(DOCS.rglob(f"{platform_id}.md")):
        text = path.read_text(encoding="utf-8")
        if BLOCK.search(text):
            out[path] = fill(platform_id, text)
    return {**out, **specs(platform_id)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platforms", nargs="*", default=None)
    parser.add_argument("--check", action="store_true",
                        help="report guides that have fallen behind instead of rewriting them")
    args = parser.parse_args()
    behind = []
    targets: dict[Path, str] = {} if args.platforms else shared()
    for platform_id in args.platforms or platform_ids():
        targets.update(expected(platform_id))
    for path, text in targets.items():
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            continue
        name = path.relative_to(ROOT).as_posix()
        if args.check:
            behind.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"rewrote {name}")
    for name in behind:
        print(f"{name} is behind the code", file=sys.stderr)
    return 1 if behind else 0


if __name__ == "__main__":
    raise SystemExit(main())
