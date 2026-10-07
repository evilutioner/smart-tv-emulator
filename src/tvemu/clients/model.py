"""Client declarations, run records and the verdict, without running anything.

A client is declared beside the platform it drives, in `platforms/<id>/clients/<name>/`:

    client.toml    where the upstream lives, how to install it, which profiles it drives,
                   and the gaps already known
    binding.py     the scenario, written against the client's public API
                   (binding.mjs, for a client installed from npm)
    expect.json    optional: what the event log must show afterwards (`tvemu.expect`)

The verdict has three sides. The client side is each step the binding reports. The emulator
side is the `expect` scenario over the event log. The wire side is every `unsupported` event:
a request the client sent that no capture answers. A gap that is declared, with its reason,
is known and does not fail the run; a declared gap the run never met is stale and does.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from tvemu import expect
from tvemu.platforms import platform_ids

PLATFORMS = Path(__file__).resolve().parents[1] / "platforms"
SCHEMA_VERSION = 1
RECORD_SCHEMA_VERSION = 1

# What a step can do. A binding names one per step, so the report can say which of these a
# client exercises and which it does not offer, across clients and platforms alike.
ACTIONS = (
    "discover", "identify", "pair", "reject", "connect", "reconnect", "query-state",
    "key", "key-long", "text", "launch", "power", "volume", "voice", "keepalive",
    "pointer", "search", "cast", "protocol-switch", "disconnect",
)
STEP_STATUSES = ("ok", "fail", "not-offered", "known-gap", "known-failure")
INSTALL_KINDS = ("pypi", "git", "npm", "none")
# The language a binding is written in follows from where its client comes from.
BINDING_FILES = {"pypi": "binding.py", "git": "binding.py", "none": "binding.py",
                 "npm": "binding.mjs"}


@dataclass(frozen=True)
class Gap:
    """A request the client sends that no capture answers, and why that is so."""

    operation: str                        # exact, or a prefix ending in `*`
    reason: str
    profiles: tuple[str, ...] = ()        # empty: every profile the client drives

    def covers(self, profile: str) -> bool:
        return not self.profiles or profile in self.profiles

    def matches(self, operation: str) -> bool:
        if self.operation.endswith("*"):
            return operation.startswith(self.operation[:-1])
        return operation == self.operation


@dataclass(frozen=True)
class KnownFailure:
    """A step that fails for a reason already understood, kept visible until it is fixed.

    Not a gap: the emulator answered, but not as the client expects, and closing it needs
    evidence nobody has recorded yet. A known failure that starts passing is stale.
    """

    step: str
    reason: str
    profiles: tuple[str, ...] = ()

    def covers(self, profile: str) -> bool:
        return not self.profiles or profile in self.profiles


@dataclass(frozen=True)
class ClientSpec:
    platform: str
    name: str
    summary: str
    upstream: str
    license: str
    install: str
    package: str
    track: str
    last_green: str
    profiles: tuple[str, ...]
    settings: dict
    timeout: int
    gaps: tuple[Gap, ...]
    known_failures: tuple[KnownFailure, ...]
    root: Path

    @property
    def key(self) -> str:
        return f"{self.platform}/{self.name}"

    @property
    def binding(self) -> Path:
        return self.root / BINDING_FILES[self.install]

    @property
    def scenario(self) -> dict | None:
        path = self.root / "expect.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _require(table: dict, name: str, kind: type, where: str):
    value = table.get(name)
    if not isinstance(value, kind):
        raise ValueError(f"{where}: `{name}` must be a {kind.__name__}")
    return value


def load_spec(root: Path, platform_id: str) -> ClientSpec:
    where = str(root / "client.toml")
    document = tomllib.loads((root / "client.toml").read_text(encoding="utf-8"))
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{where}: schema_version = {SCHEMA_VERSION} is required")
    install = _require(document, "install", dict, where)
    run = _require(document, "run", dict, where)
    kind = _require(install, "kind", str, where)
    if kind not in INSTALL_KINDS:
        raise ValueError(f"{where}: install.kind must be one of {', '.join(INSTALL_KINDS)}")
    profiles = _require(run, "profiles", list, where)
    if not profiles or not all(isinstance(item, str) for item in profiles):
        raise ValueError(f"{where}: run.profiles lists at least one profile id")

    def scope(entry: dict) -> tuple[str, ...]:
        named = tuple(entry.get("profiles") or ())
        unknown = [profile for profile in named if profile not in profiles]
        if unknown:
            raise ValueError(f"{where}: {', '.join(unknown)} is not in run.profiles")
        return named

    gaps = tuple(Gap(_require(gap, "operation", str, where), _require(gap, "reason", str, where),
                     scope(gap)) for gap in document.get("gaps") or [])
    known_failures = tuple(
        KnownFailure(_require(entry, "step", str, where), _require(entry, "reason", str, where),
                     scope(entry)) for entry in document.get("known_failures") or [])
    return ClientSpec(
        platform=platform_id,
        name=root.name,
        summary=_require(document, "summary", str, where),
        upstream=_require(document, "upstream", str, where),
        license=_require(document, "license", str, where),
        install=kind,
        package=str(install.get("package") or ""),
        track=str(install.get("track") or ""),
        last_green=str(install.get("last_green") or ""),
        profiles=tuple(profiles),
        settings=dict(run.get("settings") or {}),
        timeout=int(run.get("timeout") or 180),
        gaps=gaps,
        known_failures=known_failures,
        root=root,
    )


def client_specs(platforms: tuple[str, ...] | None = None) -> list[ClientSpec]:
    """Every client declared by the platforms this build includes."""
    specs = []
    for platform_id in platforms or platform_ids():
        directory = PLATFORMS / platform_id / "clients"
        if not directory.is_dir():
            continue
        for root in sorted(path for path in directory.iterdir() if (path / "client.toml").is_file()):
            specs.append(load_spec(root, platform_id))
    return specs


def find_spec(key: str) -> ClientSpec:
    for spec in client_specs():
        if spec.key == key:
            return spec
    known = ", ".join(spec.key for spec in client_specs()) or "none in this build"
    raise SystemExit(f"No client {key!r}; declared: {known}")


# -- the verdict ------------------------------------------------------------------------------

@dataclass
class ProfileVerdict:
    profile: str
    steps: list[dict]
    gaps: list[dict] = field(default_factory=list)
    expect: dict | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "fail" if self.problems else "pass"

    def as_record(self) -> dict:
        return {"profile": self.profile, "verdict": self.verdict, "problems": self.problems,
                "steps": self.steps, "gaps": self.gaps, "expect": self.expect}


def _within(event: dict, window: list) -> bool:
    first, last = window
    return first < int(event.get("id") or 0) <= last


def judge(spec: ClientSpec, profile: str, steps: list[dict], events: list[dict],
          since: int, binding_exit: str = "") -> ProfileVerdict:
    """Hold one profile's run to the client's declaration, from all three sides."""
    result = ProfileVerdict(profile=profile, steps=steps)
    covering = [gap for gap in spec.gaps if gap.covers(profile)]

    def declared(operation: str) -> Gap | None:
        return next((gap for gap in covering if gap.matches(operation)), None)

    failures = {entry.step: entry.reason for entry in spec.known_failures if entry.covers(profile)}
    events = [event for event in events if int(event.get("id") or 0) > since]

    unsupported = [event for event in events if event.get("kind") == "unsupported"]
    seen: dict[str, dict] = {}
    for event in unsupported:
        operation = str(event.get("operation") or "")
        gap = declared(operation)
        entry = seen.setdefault(operation, {
            "operation": operation, "status": event.get("status"), "count": 0,
            "known": gap is not None, "reason": gap.reason if gap else ""})
        entry["count"] += 1
    result.gaps = sorted(seen.values(), key=lambda entry: entry["operation"])
    for entry in result.gaps:
        if not entry["known"]:
            result.problems.append(
                f"gap: the client sent {entry['operation']} and no capture answers it")

    for step in steps:
        if step.get("action") not in ACTIONS:
            result.problems.append(f"step {step.get('name')!r}: unknown action {step.get('action')!r}")
        if step.get("status") not in STEP_STATUSES:
            result.problems.append(f"step {step.get('name')!r}: unknown status {step.get('status')!r}")
        name = step.get("name")
        if step.get("status") == "ok" and name in failures:
            result.problems.append(f"step {name!r} is declared a known failure and passed: "
                                   "the declaration is stale")
        if step.get("status") != "fail":
            continue
        own = [event for event in unsupported if _within(event, step.get("events") or [0, 0])]
        if own and all(declared(str(event.get("operation"))) for event in own):
            # The client failed because it asked for something no capture answers, and that
            # is already declared: the step is a known gap, not a regression.
            step["status"] = "known-gap"
        elif name in failures:
            step["status"] = "known-failure"
        else:
            result.problems.append(f"step {name!r} failed: {step.get('detail') or 'no detail'}")

    # A required step that failed for a declared reason stops the binding on purpose.
    stopped_on_purpose = bool(steps) and steps[-1].get("required") and \
        steps[-1]["status"] in ("known-gap", "known-failure")
    if binding_exit and not stopped_on_purpose:
        result.problems.insert(0, binding_exit)

    scenario = spec.scenario
    if scenario is not None and not stopped_on_purpose:
        problems = expect.check(events, scenario)
        result.expect = {"description": scenario.get("description", ""), "problems": problems}
        result.problems.extend(f"expect: {problem}" for problem in problems)
    return result


def stale_gaps(spec: ClientSpec, verdicts: list[ProfileVerdict]) -> list[str]:
    """Declared gaps no profile they cover met in this run: the declaration has gone stale."""
    stale = []
    for gap in spec.gaps:
        met = any(gap.matches(entry["operation"])
                  for verdict in verdicts if gap.covers(verdict.profile)
                  for entry in verdict.gaps)
        if not met:
            stale.append(gap.operation)
    return stale
