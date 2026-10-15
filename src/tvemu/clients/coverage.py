"""What a client run covered, zone by zone, counted from its record and nothing else.

A binding says what the client offers in a zone (`harness.offers`) and what each step
exercised (`covers`). From that, every zone of one profile's run splits by what happened, and
the name says whose move it is:

    ok                          exercised, and it passed
    untested                    offered by the client, exercised by no step: ours to write
    blocked                     offered, but a required step stopped the run before it
    unsupported by emulator     the client asked and no capture answers it (a declared gap)
    wrong answer from emulator  the emulator answers, not as the set does (a known failure
                                on the emulator's side)
    client bug                  the client parses a correct answer wrongly (a known failure on
                                the client's side). A zone it has no API for at all is `no API`
    failed                      failed for no declared reason: a regression, until someone
                                says whose

A zone no step reached because a required step stopped the run first is `blocked`. A zone
with neither an offer nor a step is `not written`. When a binding declares no offer for a
zone, the zone is counted in steps instead of items.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import ZONE_NAMES, ZONE_OF, ClientSpec

KINDS = ("ok", "unsupported", "wrong", "client-bug", "failed")
LABELS = {"unsupported": "unsupported by emulator", "wrong": "wrong answer from emulator",
          "client-bug": "client bug", "failed": "**failed**"}


@dataclass
class Zone:
    name: str
    offered: list[str] | None = None
    steps: list[dict] = field(default_factory=list)
    items: dict[str, list[str]] = field(default_factory=lambda: {kind: [] for kind in KINDS})
    untested: list[str] = field(default_factory=list)
    unreached: list[str] = field(default_factory=list)   # offered, cut off by a stopped run
    no_api: str = ""
    blocked: bool = False

    @property
    def by_steps(self) -> bool:
        return self.offered is None

    @property
    def total(self) -> int:
        return len(self.steps) if self.by_steps else len(self.offered)

    def cell(self) -> str:
        if self.no_api:
            return "no API"
        if self.blocked:
            return f"blocked 0/{len(self.offered)}" if self.offered else "blocked"
        if self.by_steps and not self.steps:
            return "not written"
        return f"passed {len(self.items['ok'])}/{self.total}" + (" steps" if self.by_steps else "")

    def rest(self) -> dict[str, int]:
        """What happened to everything that did not pass, counted by kind."""
        counts = {"untested": len(self.untested), "blocked": len(self.unreached)}
        counts.update({kind: len(self.items[kind]) for kind in KINDS if kind != "ok"})
        return counts


def step_kind(spec: ClientSpec, step: dict) -> str:
    status = step.get("status")
    if status == "ok":
        return "ok"
    if status == "known-gap":
        return "unsupported"
    if status == "known-failure":
        side = next((entry.side for entry in spec.known_failures if entry.step == step.get("name")),
                    "emulator")
        return "wrong" if side == "emulator" else "client-bug"
    return "failed"


def _stopped(steps: list[dict]) -> dict | None:
    last = steps[-1] if steps else None
    return last if last and last.get("required") and last.get("status") != "ok" else None


def zones(spec: ClientSpec, profile: dict) -> list[Zone]:
    """One profile's record of a run, split zone by zone."""
    every = profile.get("steps") or []
    steps = [step for step in every if step.get("status") != "not-offered"]
    not_offered = {ZONE_OF.get(step.get("action")): step.get("detail") or "not offered"
                   for step in every if step.get("status") == "not-offered"}
    offers = profile.get("offers") or {}
    stopped = _stopped(steps)
    result = []
    for name in ZONE_NAMES:
        zone = Zone(name, offered=list(offers[name]) if name in offers else None,
                    steps=[step for step in steps if ZONE_OF.get(step.get("action")) == name])
        zone.no_api = spec.not_offered.get(name, "") or (
            not_offered.get(name, "") if not zone.steps and zone.offered is None else "")
        zone.blocked = bool(stopped) and not zone.steps and not zone.no_api
        if zone.by_steps:
            for step in zone.steps:
                zone.items[step_kind(spec, step)].append(step["name"])
        else:
            placed: set[str] = set()
            # An item shows its worst outcome: a problem one step met is not undone by another
            # step that passed over the same item.
            for kind in ("failed", "wrong", "client-bug", "unsupported", "ok"):
                for item in zone.offered:
                    if item not in placed and any(
                            item in (step.get("covers") or []) and step_kind(spec, step) == kind
                            for step in zone.steps):
                        zone.items[kind].append(item)
                        placed.add(item)
            zone.untested = [item for item in zone.offered if item not in placed]
            if stopped:
                # Nothing after the stop was reached: whether a step would have covered it is
                # unknown, so it is the stop's, not a test still to write.
                zone.unreached, zone.untested = zone.untested, []
        result.append(zone)
    return result


REST = ("untested", "blocked", "unsupported", "wrong", "client-bug", "failed")
REST_LABELS = {"untested": "untested", "blocked": "blocked", **LABELS}


def totals(spec: ClientSpec, profile: dict) -> tuple[int, int, dict[str, int]]:
    """One profile's run over every zone: passed, offered, and the rest by kind."""
    passed = offered = 0
    rest = dict.fromkeys(REST, 0)
    for zone in zones(spec, profile):
        if zone.no_api or (zone.by_steps and not zone.steps):
            continue
        passed += len(zone.items["ok"])
        offered += zone.total
        for kind, count in zone.rest().items():
            rest[kind] += count
    return passed, offered, rest


def stopped_zone(profile: dict) -> str:
    stopped = _stopped([step for step in profile.get("steps") or []
                        if step.get("status") != "not-offered"])
    return ZONE_OF.get(stopped.get("action"), "") if stopped else ""


def groups(spec: ClientSpec, record: dict) -> list[list[dict]]:
    """The profiles of one run, those with the same outcome in every zone side by side."""
    grouped: dict[tuple, list[dict]] = {}
    for profile in record["profiles"]:
        counted = zones(spec, profile)
        key = (tuple(zone.cell() for zone in counted),
               tuple(tuple(zone.rest().items()) for zone in counted))
        grouped.setdefault(key, []).append(profile)
    return list(grouped.values())


# -- the heatmap: what real clients have confirmed of each emulated television -------------------

HEAT = ((0.8, "🟩"), (0.4, "🟨"), (0.0, "🟥"))
HEAT_LEGEND = ("A cell is one zone of one emulated television, over every client that drove it: "
               "the best share any client passed of what it offers there, how many clients "
               "passed anything there, and ⚠ how many times they met the emulator's gap or wrong "
               "answer. 🟩 80 % or more, 🟨 40 % or more, 🟥 less, ⬛ every client was blocked "
               "before it, ⬜ no client has an API for it, *not written* no binding says anything "
               "about it, *not run* no client drives that television.")


def heat_cell(drove: list[Zone]) -> str:
    """One zone on one television, from the zones of every client that drove it."""
    if not drove:
        return "not run"
    api = [zone for zone in drove if not zone.no_api]
    if not api:
        return "⬜ no API"
    written = [zone for zone in api if not (zone.by_steps and not zone.steps)]
    if not written:
        return "not written"
    reached = [zone for zone in written if not zone.blocked
               and (zone.items["ok"] or zone.untested or any(zone.items[kind] for kind in KINDS))]
    if not reached:
        return "⬛ blocked"
    best = max(len(zone.items["ok"]) / zone.total for zone in reached)
    mark = next(mark for floor, mark in HEAT if best >= floor)
    passing = sum(1 for zone in written if zone.items["ok"])
    cell = f"{mark} {round(best * 100)} % · {passing}/{len(written)}"
    emulator = sum(len(zone.items[kind]) for zone in written for kind in ("unsupported", "wrong"))
    failed = sum(len(zone.items["failed"]) for zone in written)
    return cell + (f" · ⚠ {emulator}" if emulator else "") + (f" · **failed {failed}**" if failed else "")


def heatmap(profiles: list[str], columns: list[tuple[ClientSpec, dict]]) -> list[str]:
    """Zones down the side, emulated televisions across: `(spec, latest record)` per client."""
    counted = {profile_id: [zones(spec, profile) for spec, record in columns
                            for profile in record["profiles"] if profile["profile"] == profile_id]
               for profile_id in profiles}
    lines = ["| Zone | " + " | ".join(f"`{profile_id}`" for profile_id in profiles) + " |",
             "|---|" + "---|" * len(profiles)]
    for index, name in enumerate(ZONE_NAMES):
        cells = [heat_cell([client[index] for client in counted[profile_id]])
                 for profile_id in profiles]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


# -- the backlog: who moves next, and on what -------------------------------------------------

def _runs(pairs: list[tuple[str, str]]) -> str:
    return f"{len(pairs)} run" + ("" if len(pairs) == 1 else "s")


def _where(pairs: list[tuple[str, str]]) -> str:
    """Which clients on which televisions, each television list said once."""
    by_profiles: dict[tuple[str, ...], list[str]] = {}
    clients: dict[str, list[str]] = {}
    for client, profile in pairs:
        clients.setdefault(client, []).append(profile)
    for client, profiles in clients.items():
        by_profiles.setdefault(tuple(profiles), []).append(client)
    return "; ".join(
        f"{', '.join(names)} on "
        + (f"{len(profiles)} televisions" if len(profiles) > 3
           else ", ".join(f"`{profile}`" for profile in profiles))
        for profiles, names in by_profiles.items())


def _first_sentence(text: str) -> str:
    """The backlog says why in one sentence; the whole reason stays in client.toml."""
    end = text.find(". ")
    return text if end < 0 else text[:end + 1]


def _entries(entries: dict[str, dict], code: bool) -> list[str]:
    """One line per entry, entries met on the same runs under one heading."""
    by_where: dict[str, list[tuple[str, dict]]] = {}
    for name, entry in sorted(entries.items(), key=lambda pair: (-len(pair[1]["at"]), pair[0])):
        by_where.setdefault(_where(entry["at"]), []).append((name, entry))
    lines = []
    for where, group in by_where.items():
        runs = _runs(group[0][1]["at"])
        label = (lambda name: f"`{name}`") if code else (lambda name: name)
        if len(group) == 1:
            name, entry = group[0]
            lines.append(f"- **{label(name)}**, {runs} ({where}). "
                         f"{_first_sentence(entry['reason'])}")
            continue
        reasons = {_first_sentence(entry["reason"]) for _, entry in group}
        if len(reasons) == 1:
            names = ", ".join(label(name) for name, _ in group)
            lines.append(f"- {len(group)} items, {runs} each ({where}). {reasons.pop()} {names}")
            continue
        lines.append(f"- {len(group)} items, {runs} each ({where}):")
        lines += [f"  - **{label(name)}**: {_first_sentence(entry['reason'])}"
                  for name, entry in group]
    return lines


def backlog(columns: list[tuple[ClientSpec, dict]]) -> list[str]:
    """Everything that did not pass, as work: grouped by who moves, most runs first."""
    captures: dict[str, dict] = {}
    failures: dict[str, dict[str, dict]] = {"wrong": {}, "client-bug": {}, "failed": {}}
    blocked: dict[str, dict] = {}
    untested: dict[tuple[str, str], set[str]] = {}
    for spec, record in columns:
        for profile in record["profiles"]:
            pair = (spec.name, profile["profile"])
            for gap in profile.get("gaps") or []:
                captures.setdefault(gap["operation"], {"reason": gap.get("reason") or "",
                                                       "at": []})["at"].append(pair)
            for step in profile.get("steps") or []:
                if step.get("status") == "not-offered":
                    continue      # a fact about the client, shown as "no API" in its zones
                kind = step_kind(spec, step)
                if kind in failures:
                    reason = next((entry.reason for entry in spec.known_failures
                                   if entry.step == step["name"]), step.get("detail") or "")
                    failures[kind].setdefault(step["name"], {"reason": reason, "at": []})[
                        "at"].append(pair)
            stop = stopped_zone(profile)
            if stop:
                entry = blocked.setdefault(profile["profile"], {"zones": [], "items": 0})
                entry["zones"].append(f"{spec.name} at {stop}")
                entry["items"] += totals(spec, profile)[2]["blocked"]
            for zone in zones(spec, profile):
                for item in zone.untested:
                    untested.setdefault((zone.name, item), set()).add(spec.name)

    def ordered(entries: dict[str, dict]) -> list[tuple[str, dict]]:
        return sorted(entries.items(), key=lambda pair: (-len(pair[1]["at"]), pair[0]))

    def section(title: str, intro: str, body: list[str]) -> list[str]:
        return [f"### {title}", "", intro, "", *(body or ["None."]), ""]

    lines = section(
        "Emulator: captures to record",
        "Requests a client sent that no capture answers (unsupported by emulator).",
        _entries(captures, code=True))
    lines += section(
        "Emulator: wrong answers",
        "The emulator answers, but not as the set does (wrong answer from emulator).",
        _entries(failures["wrong"], code=False))
    lines += section(
        "Blocked televisions",
        "A required step stopped the run; nothing after it was reached.",
        [f"- **`{profile}`**: {', '.join(entry['zones'])}; {entry['items']} offered items "
         "never reached." for profile, entry in blocked.items()])
    lines += section(
        "Client bugs",
        "The client parses a correct answer wrongly.",
        _entries(failures["client-bug"], code=False))
    if failures["failed"]:
        lines += section(
            "Failed, not yet explained",
            "Failed for no declared reason: the run is red until someone says whose it is.",
            [f"- **{name}**, {_runs(entry['at'])} ({_where(entry['at'])}): `{entry['reason']}`"
             for name, entry in ordered(failures["failed"])])
    tests = []
    for zone in ZONE_NAMES:
        items = sorted(((item, len(clients)) for (name, item), clients in untested.items()
                        if name == zone), key=lambda pair: (-pair[1], pair[0]))
        if items:
            shown = ", ".join(f"`{item}` ×{count}" for item, count in items[:LIST_LIMIT])
            more = f" and {len(items) - LIST_LIMIT} more" if len(items) > LIST_LIMIT else ""
            tests.append(f"- **{zone}** ({len(items)}): {shown}{more}")
    lines += section(
        "Tests to write",
        "Offered by a client and exercised by no step (untested), by zone; ×N is how many "
        "clients offer it.", tests)
    return lines


LIST_LIMIT = 10


def _items(items: list[str]) -> str:
    shown = ", ".join(f"`{item}`" for item in items[:LIST_LIMIT])
    return shown + (f" and {len(items) - LIST_LIMIT} more" if len(items) > LIST_LIMIT else "")


def zone_lines(spec: ClientSpec, profile: dict) -> list[str]:
    """One bullet per zone, then what is untested, the emulator's and the client's."""
    lines = []
    for zone in zones(spec, profile):
        if zone.no_api:
            lines.append(f"- **{zone.name}**: no API. {zone.no_api}")
            continue
        if zone.blocked or (zone.by_steps and not zone.steps):
            lines.append(f"- **{zone.name}**: {zone.cell()}.")
            continue
        unit = " steps" if zone.by_steps else ""
        lines.append(f"- **{zone.name}**: passed {len(zone.items['ok'])}/{zone.total}{unit}.")
        if zone.untested:
            lines.append(f"  - untested: {_items(zone.untested)}")
        if zone.unreached:
            lines.append(f"  - blocked, not reached: {_items(zone.unreached)}")
        for step in zone.steps:
            kind = step_kind(spec, step)
            if kind != "ok":
                what = f" ({_items(step['covers'])})" if step.get("covers") else ""
                lines.append(f"  - {LABELS[kind]}: {step['name']}{what}: "
                             f"`{step.get('detail') or '-'}`")
    return lines


def answers_line(profile: dict) -> str:
    answers = profile.get("answers")
    if answers is None:
        return ""
    if not answers:
        return "The emulator sent no error status."
    statuses: dict[int, int] = {}
    for entry in answers:
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + entry["count"]
    return "Error statuses the emulator sent: " + ", ".join(
        f"{status} ×{count}" for status, count in sorted(statuses.items())) + "."
