"""Fill the generated blocks of each platform guide from the emulator's own declarations.

A guide is for somebody deciding whether this television does what they need, so the parts a
reader could not have guessed are written by hand and the parts the code already knows are
written from the code. A hand-maintained route table drifts; this one cannot.

The same run writes `docs/spec/<id>.openapi.json` and `docs/spec/<id>.asyncapi.json`, the
machine contract a driver reads without starting the emulator. A
television whose ports answer the same request gets one `<id>.<application>.openapi.json`
per application instead.

It also fills the blocks that state counts and lists across televisions — the README's
badges and television table, and the detailed table in `docs/televisions.md` — from
`catalogue.json`, so a number is written in one place, and draws the README's generation
timeline for every television with two or more generations into `docs/images/generations/`. "In this build" means the build the
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
from html import escape
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
        _badge("platforms", f"{included} included · {unavailable} on request",
               f"{included} included, {unavailable} on request"),
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


# How a catalogue kind reads in a table's Type column, and as a group of the README's table.
KIND_NAMES = {"tv": "TV", "projector": "Projector", "console": "Console"}
KIND_GROUPS = {"tv": "Televisions", "projector": "Projectors", "console": "Consoles"}

# Where the README's generation timelines are written, one per platform with two or more.
GENERATIONS = DOCS / "images" / "generations"
# Fill colours by era, oldest first: two eras are the ends of the scale, three use all of it.
# Each pairs a fill with a text colour for light and for dark pages.
ERA_COLOURS = (("#EF9F27", "#BA7517", "#EF9F27"), ("#1D9E75", "#0F6E56", "#5DCAA5"),
               ("#378ADD", "#185FA5", "#85B7EB"), ("#7F77DD", "#534AB7", "#AFA9EC"),
               ("#D85A30", "#993C1D", "#F0997B"))
TIMELINE_WIDTH = 240
# A table cell shrinks an image to fit, so the column header holds the timeline's width open
# with spaces a browser will not break.
GENERATIONS_HEADER_PAD = "&nbsp;" * 34


def _eras(entry) -> list[str]:
    return list(dict.fromkeys(generation.family for generation in entry.generations))


def _era_colours(count: int) -> list[tuple[str, str, str]]:
    if count == 2:
        return [ERA_COLOURS[0], ERA_COLOURS[2]]
    return list(ERA_COLOURS[:count]) if count >= 3 else [ERA_COLOURS[2]]


def _years(entry) -> tuple[int, int] | None:
    spans = [generation.years for generation in entry.generations]
    if not spans or None in spans:
        return None
    return min(span[0] for span in spans), max(span[1] for span in spans)


def _era_labels(entry) -> list[str]:
    """What the timeline says under its bar: eras counted, or each generation named."""
    eras = _eras(entry)
    if len(eras) == len(entry.generations):
        return eras
    return [f"{sum(g.family == era for g in entry.generations)} {era}" for era in eras]


def _text_width(text: str) -> float:
    return len(text) * 6.1


def generation_timeline(entry) -> str:
    """One platform's generations as a bar, oldest first, for a README table cell.

    Segments are as wide as the model years they cover when every generation is dated, and
    equal otherwise; the labels under the bar are coloured as their segments, so the cell
    needs no legend.
    """
    eras = _eras(entry)
    colours = dict(zip(eras, _era_colours(len(eras))))
    dated = _years(entry) is not None
    weights = [(g.years[1] - g.years[0] + 1) if dated else 1 for g in entry.generations]
    gap = 2
    usable = TIMELINE_WIDTH - gap * (len(weights) - 1)
    parts, x, starts = [], 0.0, {}
    for generation, weight in zip(entry.generations, weights):
        width = usable * weight / sum(weights)
        starts.setdefault(generation.family, (x, generation.years))
        parts.append(f'<rect x="{x:.1f}" y="0" width="{width:.1f}" height="10" rx="2" '
                     f'fill="{colours[generation.family][0]}"/>')
        x += width + gap
    y = 10
    if dated:
        y += 14
        first, last = _years(entry)
        ticks = [(start, years[0]) for start, years in starts.values()]
        placed = []
        for at, year in ticks:
            if not placed or at - placed[-1] >= 34:
                placed.append(at)
                parts.append(f'<text class="year" x="{at:.1f}" y="{y}">{year}</text>')
        if TIMELINE_WIDTH - placed[-1] >= 60:
            parts.append(f'<text class="year" x="{TIMELINE_WIDTH}" y="{y}" '
                         f'text-anchor="end">{last}</text>')
    line, lines = [], []
    for era, label in zip(eras, _era_labels(entry)):
        candidate = line + [(era, label)]
        if line and _text_width(" · ".join(text for _, text in candidate)) > TIMELINE_WIDTH:
            lines.append(line)
            candidate = [(era, label)]
        line = candidate
    lines.append(line)
    styles = []
    for index, era in enumerate(eras):
        styles.append(f".e{index}{{fill:{colours[era][1]}}}")
    dark = " ".join(f".e{index}{{fill:{colours[era][2]}}}" for index, era in enumerate(eras))
    for row in lines:
        y += 16
        spans = []
        for position, (era, label) in enumerate(row):
            if position:
                spans.append('<tspan class="dot"> · </tspan>')
            spans.append(f'<tspan class="e{eras.index(era)}">{escape(label)}</tspan>')
        parts.append(f'<text y="{y}">{"".join(spans)}</text>')
    height = y + 4
    title = escape(f"{entry.display_name}: " + ", ".join(_era_labels(entry)))
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{TIMELINE_WIDTH}" height="{height}" '
        f'viewBox="0 0 {TIMELINE_WIDTH} {height}" role="img">',
        f"  <title>{title}</title>",
        "  <style>",
        "    text { font: 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial,"
        " sans-serif; }",
        "    .year { font-size: 11px; fill: #6e7781; } .dot { fill: #6e7781; }",
        f"    {' '.join(styles)}",
        f"    @media (prefers-color-scheme: dark) {{ .year, .dot {{ fill: #9198a1; }} {dark} }}",
        "  </style>",
        *(f"  {part}" for part in parts),
        "</svg>",
        "",
    ])


def generation_timelines() -> dict[Path, str]:
    return {GENERATIONS / f"{entry.id}.svg": generation_timeline(entry)
            for entry in catalogue_entries() if len(entry.generations) > 1}


def _generations_cell(entry) -> str:
    count = len(entry.generations)
    if count == 0:
        return "—"
    if count == 1:
        return entry.generations[0].name
    years = _years(entry)
    span = f" · {years[0]}&nbsp;→&nbsp;{years[1]}" if years and years[0] != years[1] else ""
    image = (GENERATIONS / f"{entry.id}.svg").relative_to(ROOT).as_posix()
    alt = escape(f"{entry.display_name} generations: " + ", ".join(_era_labels(entry)), quote=True)
    return (f"**{count}**&nbsp;gens{span}<br>"
            f'<img src="{image}" width="{TIMELINE_WIDTH}" alt="{alt}">')


def _devices_cell(entry) -> str:
    def count(test) -> int:
        return sum(len(device.profiles) for device in entry.captured if test(device))
    lines = [(count(lambda d: not d.modelled), "📡&nbsp;{}&nbsp;captured"),
             (count(lambda d: d.modelled), "📱&nbsp;{}&nbsp;modelled"),
             (count(lambda d: d.validated), "✅&nbsp;{}&nbsp;validated")]
    return "<br>".join(text.format(number) for number, text in lines if number) or "—"


def _tested_cell(entry) -> str:
    lines = []
    if entry.apps:
        lines.append("✅ " + ", ".join(f"[{app.name}]({app.url})" for app in entry.apps))
    if entry.clients:
        lines.append("🧪 " + ", ".join(f"[{client.name}]({client.url})"
                                      for client in entry.clients))
    return "<br>".join(lines) or "—"


def televisions() -> str:
    """The README's table: what this build includes first, then the rest by kind."""
    shipped = published()
    entries = catalogue_entries()
    included = [entry for entry in entries if entry.id in shipped]
    others = [entry for entry in entries if entry.id not in shipped]
    groups = [("In this repository", included),
              ("Televisions on request", [e for e in others if e.kind == "tv"])]
    rest = [entry for entry in others if entry.kind != "tv"]
    kinds = [KIND_GROUPS.get(kind, kind) for kind in dict.fromkeys(e.kind for e in rest)]
    if rest:
        name = " and ".join([", ".join(kinds[:-1]), kinds[-1]] if len(kinds) > 1 else kinds)
        groups.append((f"{name.capitalize()} on request", rest))
    blocks = []
    for title, members in groups:
        if not members:
            continue
        lines = [f"**{title}**", "",
                 f"| Television | Generations{GENERATIONS_HEADER_PAD} | Protocols | Devices | "
                 "Tested with |",
                 "|---|---|---|---|---|"]
        for entry in members:
            lines.append(f"| **[{entry.display_name}]({entry.docs})** | "
                         f"{_generations_cell(entry)} | "
                         f"**{entry.protocols}** protocols<br><sub>{entry.summary}</sub> | "
                         f"{_devices_cell(entry)} | {_tested_cell(entry)} |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def television_details() -> str:
    """The full table in docs/televisions.md: ports, discovery, pairing and firmware."""
    shipped = published()
    lines = ["| Platform | Type | In this build | Remote control | Discovery | Pairing | "
             "Devices | Tested with |",
             "|---|---|---|---|---|---|---|---|"]
    for entry in catalogue_entries():
        devices = "<br>".join(
            f"{_evidence(device)} {_device_name(device)}"
            + (f" — {device.detail}" if device.detail and len(device.profiles) < 2 else "")
            for device in entry.captured)
        state = "**Included**" if entry.id in shipped else "On request"
        docs = entry.docs.removeprefix("docs/")
        lines.append(f"| **[{entry.display_name}]({docs})** | "
                     f"{KIND_NAMES.get(entry.kind, entry.kind)} | {state} | {entry.remote} | "
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
    return {**out, **generation_timelines()}


def stale_timelines() -> list[Path]:
    """Timelines left behind by a platform that no longer has two generations."""
    wanted = set(generation_timelines())
    return sorted(path for path in GENERATIONS.glob("*.svg") if path not in wanted)


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
    if not args.platforms:
        for path in stale_timelines():
            name = path.relative_to(ROOT).as_posix()
            if args.check:
                behind.append(name)
            else:
                path.unlink()
                print(f"removed {name}")
    for name in behind:
        print(f"{name} is behind the code", file=sys.stderr)
    return 1 if behind else 0


if __name__ == "__main__":
    raise SystemExit(main())
