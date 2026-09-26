"""Fill the generated blocks of each platform guide from the emulator's own declarations.

A guide is for somebody deciding whether this television does what they need, so the parts a
reader could not have guessed are written by hand and the parts the code already knows are
written from the code. A hand-maintained route table drifts; this one cannot.

The same run writes `docs/spec/<id>.openapi.json` and `docs/spec/<id>.asyncapi.json`, the
machine contract a driver (or a model writing one) reads without starting the emulator. A
television whose ports answer the same request gets one `<id>.<application>.openapi.json`
per application instead.

It also fills the blocks that state counts and lists across televisions — the README's
badges and television table, and the request form's checkboxes — from `catalogue.json`, so
a number is written in one place. "In this build" means the build the README describes: the
platforms `PUBLIC.toml` names where that manifest exists, else the ones this tree runs.

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
REQUEST_FORM = ROOT / ".github" / "ISSUE_TEMPLATE" / "television-request.yml"
# The same idea in YAML, where a block is a pair of comment lines.
YAML_BLOCK = re.compile(r"^( *)# generated:(\w+)\n.*?^ *# /generated$", re.S | re.M)


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
    devices = sum(len(entry.profile_ids) for entry in entries)
    listeners = sum(entry.protocols for entry in entries)
    return "\n".join([
        _badge("televisions", f"{included} included · {unavailable} N/A",
               f"{included} included, {unavailable} N/A"),
        _badge("captured devices", str(devices), f"{devices} captured devices"),
        _badge("protocol listeners", str(listeners), f"{listeners} protocol listeners"),
    ])


def televisions() -> str:
    shipped = published()
    lines = ["| Television | In this build | Remote control | Discovery | Pairing | Captured devices |",
             "|---|---|---|---|---|---|"]
    for entry in catalogue_entries():
        devices = "<br>".join(
            f"**{device.name}** — {device.detail}" if device.detail and len(device.profiles) < 2
            else f"**{device.name}**" + (f" ({len(device.profiles)} captures)"
                                         if len(device.profiles) > 1 else "")
            for device in entry.captured)
        state = "✅ **Included**" if entry.id in shipped else "N/A"
        lines.append(f"| **[{entry.display_name}]({entry.docs})** | {state} | {entry.remote} | "
                     f"{entry.discovery} | {entry.pairing} | {devices} |")
    return "\n".join(lines)


def request_options(indent: str) -> str:
    shipped = published()
    return "\n".join(f"{indent}- label: {entry.display_name}"
                     for entry in catalogue_entries() if entry.id not in shipped)


def shared() -> dict[Path, str]:
    """The files whose generated blocks come from the catalogue rather than one platform."""
    out: dict[Path, str] = {}
    if README.is_file():
        text = README.read_text(encoding="utf-8")
        renderers = {"badges": badges, "televisions": televisions}
        out[README] = BLOCK.sub(
            lambda m: (f"<!-- generated:{m.group(1)} -->\n{renderers[m.group(1)]()}\n"
                       "<!-- /generated -->"), text)
    if REQUEST_FORM.is_file():
        text = REQUEST_FORM.read_text(encoding="utf-8")
        out[REQUEST_FORM] = YAML_BLOCK.sub(
            lambda m: (f"{m.group(1)}# generated:{m.group(2)}\n{request_options(m.group(1))}\n"
                       f"{m.group(1)}# /generated"), text)
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
