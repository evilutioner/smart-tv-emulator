"""Build the case list from the selectable profiles and run each case over a real socket.

Every case starts a fresh `Core` and adapter, binds only the protocol it needs on an
ephemeral loopback port while the profile keeps advertising its captured endpoint, sends the
captured input, compares the output byte for byte, and then proves the adapter let go of
every listener and task. Nothing here calls a handler directly.
"""
from __future__ import annotations

import asyncio
import json
import time

import aiohttp
from dataclasses import dataclass
from importlib.resources import files

from tvemu.core import Core, Settings
from tvemu.platforms import create_platform, platform_descriptor, platform_ids
from tvemu.platforms.base import DISCOVERY_KINDS
from tvemu.platforms.common.adapter import LoopbackBinding
from tvemu.platforms.common.evidence import Exchange, Step
from tvemu.platforms.common.profile import ProfileReference, profile_capture

from . import compare, http, websocket
from .model import CaseResult, ConformanceCase, CoverageGap, Plan, Report

# A documentation address (RFC 5737): what the emulated set advertises during a run. It is
# never bound, so handlers render the same bytes they would on a lab network.
ADVERTISED_HOST = "192.0.2.10"
HTTP_TRANSPORTS = ("http", "https")
SETTLE_ROUNDS = 50


class PlanError(ValueError):
    """Evidence or a profile the harness cannot turn into cases."""


@dataclass(frozen=True)
class Selection:
    platform: str = ""
    profile: str = ""
    case: str = ""


@dataclass(frozen=True)
class _Route:
    protocol: str
    auth: bool
    tls: bool


def profiles(platform_id: str) -> dict[str, ProfileReference]:
    """The evidence-backed profiles a platform offers, keyed by id."""
    package = f"tvemu.platforms.{platform_id}"
    root = files(package).joinpath("profiles")
    if not root.is_dir():
        return {}
    found: dict[str, ProfileReference] = {}
    for directory in sorted((item for item in root.iterdir() if item.is_dir()),
                            key=lambda item: item.name):
        reference = profile_capture(directory, package)
        found[reference.id] = reference
    return found


def fresh_adapter(platform_id: str, profile_id: str):
    core = Core(platform_descriptor(platform_id), Settings(device_profile=profile_id))
    core.host = ADVERTISED_HOST
    adapter = create_platform(platform_id, core)
    adapter.listener_binding = LoopbackBinding()
    return adapter


async def _routes(platform_id: str, profile_id: str
                  ) -> tuple[dict[str, list[_Route]], dict[str, list[_Route]]]:
    """Which listener answers each operation, and each GET path, read off the running apps."""
    adapter = fresh_adapter(platform_id, profile_id)
    found: dict[str, list[_Route]] = {}
    paths: dict[str, list[_Route]] = {}
    try:
        for protocol_id, listener in adapter.listeners.items():
            spec = adapter.specs[protocol_id]
            if (listener.app is None or spec.kind in DISCOVERY_KINDS
                    or adapter.profile.binding(protocol_id) is None):
                continue
            await adapter.start_protocol(protocol_id)
            tls = listener.ssl_context is not None
            for route in adapter.runners[protocol_id].app.router.routes():
                for declared in getattr(route.handler, "wire_routes", ()):
                    entry = _Route(protocol_id, declared.auth, tls)
                    for key, table in ((declared.operation_id, found),
                                       (f"{declared.method} {declared.path}", paths)):
                        rows = table.setdefault(key, [])
                        if entry not in rows:
                            rows.append(entry)
    finally:
        await adapter.stop_all()
    return found, paths


def _choose(exchange: Exchange, candidates: list[_Route], adapter) -> _Route | None:
    tls = exchange.transport == "https"
    rows = [route for route in candidates if route.tls == tls]
    port = exchange.steps[0].metadata.get("port")
    if isinstance(port, int) and len(rows) > 1:
        rows = [route for route in rows if adapter.protocol_port(route.protocol) == port]
    if len(rows) > 1:
        primary = [route for route in rows
                   if adapter.profile.binding(route.protocol).primary]
        rows = primary or rows
    if len(rows) > 1:
        raise PlanError(f"{exchange.id}: {exchange.operation_id} is served by "
                        f"{', '.join(route.protocol for route in rows)}; the capture does "
                        f"not say which port it came from")
    return rows[0] if rows else None


def coverage_complete(platform_id: str) -> bool:
    """Whether a platform declares every replay of every profile covered."""
    declared = getattr(websocket.platform_package(platform_id), "COVERAGE", "")
    if declared not in ("", "complete"):
        raise PlanError(f"{platform_id}: COVERAGE must be 'complete' when set")
    return declared == "complete"


async def build_plan(selection: Selection = Selection()) -> Plan:
    plan = Plan()
    for platform_id in platform_ids():
        if selection.platform and platform_id != selection.platform:
            continue
        for profile_id, reference in profiles(platform_id).items():
            if selection.profile and profile_id != selection.profile:
                continue
            await _plan_profile(plan, platform_id, reference, selection)
    return plan


# What a profile's conformance data may declare about an exchange, and how its gap reads.
# `stateful`: the output depends on state earlier steps established; nothing in a lone request
# says the set was paired or an app launched first. `transcribed`: the capture keeps a
# decoded rendering of the answer rather than the bytes on the wire, so no run can compare
# bytes. Each stays an uncovered replay until a recipe, or a new capture, closes it.
DECLARATIONS = {"stateful": "needs a stateful recipe",
                "transcribed": "the capture holds a transcription, not wire bytes"}


def declared_exchanges(platform_id: str, reference: ProfileReference) -> dict[str, str]:
    """Exchanges a profile's conformance data declares uncoverable for now, with the reason.

    Platform data in `platforms/<id>/conformance/<profile>.json`.
    """
    source = files(f"tvemu.platforms.{platform_id}").joinpath("conformance",
                                                               f"{reference.id}.json")
    if not source.is_file():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    owner = f"conformance data for {platform_id}/{reference.id}"
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("profile") != reference.id):
        raise PlanError(f"{owner}: needs schema_version 1 and its own profile id")
    unexpected = set(data) - {"schema_version", "profile", *DECLARATIONS}
    if unexpected:
        raise PlanError(f"{owner}: unknown keys {', '.join(sorted(unexpected))}")
    found: dict[str, str] = {}
    for key, prefix in DECLARATIONS.items():
        rows = data.get(key, {})
        if not isinstance(rows, dict) or not all(
                isinstance(reason, str) and reason for reason in rows.values()):
            raise PlanError(f"{owner}: {key} maps exchange ids to reasons")
        unknown = set(rows) - set(reference.replays.values())
        if unknown:
            raise PlanError(f"{owner}: {', '.join(sorted(unknown))} is not replayed by the "
                            f"profile")
        twice = set(rows) & set(found)
        if twice:
            raise PlanError(f"{owner}: {', '.join(sorted(twice))} is declared twice")
        found.update({exchange: f"{prefix}: {reason}" for exchange, reason in rows.items()})
    return found


async def _plan_profile(plan: Plan, platform_id: str, reference: ProfileReference,
                        selection: Selection) -> None:
    routes, paths = await _routes(platform_id, reference.id)
    declared = declared_exchanges(platform_id, reference)
    sockets = websocket.channels(platform_id)
    adapter = fresh_adapter(platform_id, reference.id)
    by_exchange: dict[str, list[str]] = {}
    for name, exchange_id in reference.replays.items():
        by_exchange.setdefault(exchange_id, []).append(name)
    for exchange_id, names in by_exchange.items():
        exchange = reference.capture.exchange(exchange_id)
        case_id = f"{platform_id}/{reference.id}/{exchange_id}"
        if selection.case and case_id != selection.case:
            continue
        plan.replays += len(names)
        reason = ""
        route = None
        exchanges = (exchange_id,)
        if exchange_id in declared:
            reason = declared[exchange_id]
        elif exchange.transport == "websocket":
            channel = sockets.get(websocket.channel_of(exchange))
            reason = websocket.replay_gap(exchange, channel)
            if not reason:
                exchanges = (*channel.opening, exchange_id)
                opening = [reference.capture.exchange(item) for item in channel.opening]
                reason = next((f"opening exchange {item.id}: {gap}" for item in opening
                               if (gap := websocket.replay_gap(item, channel))), "")
            if not reason:
                rows = paths.get(f"GET {channel.path}", [])
                if len(rows) != 1:
                    raise PlanError(f"{exchange_id}: {len(rows)} listeners serve the "
                                    f"{channel.id} upgrade path {channel.path}")
                route = rows[0]
                if route.auth:
                    reason = "the upgrade requires pairing, so it needs a stateful recipe"
        elif exchange.transport not in HTTP_TRANSPORTS:
            reason = f"no conformance driver for {exchange.transport} yet"
        elif [step.direction for step in exchange.steps] != ["in", "out"]:
            reason = "a multi-step HTTP exchange needs a stateful recipe"
        elif owned := _client_placeholders(exchange.steps[0]):
            reason = (f"the captured request carries client-owned {', '.join(owned)}, so it "
                      f"needs a recipe to materialise them")
        else:
            route = _choose(exchange, routes.get(exchange.operation_id, []), adapter)
            if route is None:
                reason = (f"no {exchange.transport} listener of this profile serves "
                          f"{exchange.operation_id}")
            elif route.auth:
                reason = "the route requires pairing, so it needs a stateful recipe"
        if reason:
            plan.gaps.extend(CoverageGap(platform_id, reference.id, name, exchange_id,
                                         exchange.transport, reason) for name in names)
            continue
        plan.cases.append(ConformanceCase(
            id=case_id, platform=platform_id, profile=reference.id,
            exchanges=exchanges, protocol=route.protocol, driver=exchange.transport,
            replays=tuple(names)))


def _client_placeholders(step: Step) -> list[str]:
    """Placeholders in a captured request: values the client owned, which were not kept."""
    headers = step.metadata.get("headers", {})
    text = " ".join([str(step.metadata.get("path", "")),
                     *(f"{name}: {value}" for name, value in
                       (headers.items() if isinstance(headers, dict) else ()))])
    return sorted(set(compare.PLACEHOLDER.findall(text)))


# ── execution ────────────────────────────────────────────────────────────────────────────


async def run_case(case: ConformanceCase, reference: ProfileReference) -> CaseResult:
    started = time.monotonic()
    result = CaseResult(case, "pass")
    before = set(asyncio.all_tasks())
    adapter = fresh_adapter(case.platform, case.profile)
    bound: tuple[str, int] | None = None
    try:
        await adapter.start_protocol(case.protocol)
        bound = adapter.bound[case.protocol]
        authority = f"{ADVERTISED_HOST}:{adapter.protocol_port(case.protocol)}"
        substitutions = tuple(path for name in case.replays
                              for path in reference.substitutions.get(name, ()))
        if case.driver == "websocket":
            await _websocket(case, reference, adapter, bound, authority, substitutions, result)
        else:
            for exchange_id in case.exchanges:
                _check(await _exchange(case, reference, exchange_id, bound, authority),
                       reference.capture.exchange(exchange_id), substitutions, result)
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError,
            aiohttp.ClientError) as exc:
        result.problems.append(f"{type(exc).__name__}: {exc}")
    finally:
        await adapter.stop_all()
        await adapter.disconnect()
    result.problems += await _leaks(adapter, before, bound)
    result.status = "fail" if result.problems else "pass"
    result.duration = time.monotonic() - started
    return result


async def _websocket(case: ConformanceCase, reference: ProfileReference, adapter,
                     bound: tuple[str, int], authority: str, substitutions: tuple[str, ...],
                     result: CaseResult) -> None:
    exchanges = [reference.capture.exchange(item) for item in case.exchanges]
    channel = websocket.channels(case.platform)[websocket.channel_of(exchanges[-1])]
    tls = adapter.listeners[case.protocol].ssl_context is not None
    url = f"{'wss' if tls else 'ws'}://{bound[0]}:{bound[1]}{channel.path}"
    # The profile's substitutions belong to the replay; an opening exchange has only the
    # channel's own masks.
    problems, notes = await websocket.run(
        url, authority, channel, exchanges, {exchanges[-1].id: substitutions},
        {"host": ADVERTISED_HOST}, case.timeout, tls)
    result.problems += problems
    result.notes += notes


async def _exchange(case: ConformanceCase, reference: ProfileReference, exchange_id: str,
                    bound: tuple[str, int], authority: str) -> http.HTTPResponse:
    exchange = reference.capture.exchange(exchange_id)
    request = exchange.steps[0]
    return await http.send(bound[0], bound[1], http.request_bytes(request, authority),
                           tls=exchange.transport == "https", timeout=case.timeout,
                           head=request.metadata["method"] == "HEAD")


def _check(response: http.HTTPResponse, exchange: Exchange, substitutions: tuple[str, ...],
           result: CaseResult) -> None:
    expected = exchange.response()
    outcome = compare.Outcome()
    status = expected.metadata["status"]
    if response.status != status:
        outcome.problems.append(f"status: expected {status}, observed {response.status}")
    headers = expected.metadata.get("headers", {})
    values = {"host": ADVERTISED_HOST}
    compare.compare_headers(headers, list(response.headers), substitutions, values, outcome)
    compare.compare_body(expected.payload, response.body, substitutions, values, outcome,
                         frozenset(name.lower() for name in headers))
    result.problems += [f"{exchange.id}: {problem}" for problem in outcome.problems]
    result.notes += [f"{exchange.id}: {note}" for note in outcome.notes]
    result.notes += [f"{exchange.id}: substitution {path!r} was not exercised"
                     for path in compare.unaccounted(substitutions, outcome)
                     if not any(repr(path) in note for note in outcome.notes)]


async def _leaks(adapter, before: set[asyncio.Task], bound: tuple[str, int] | None
                 ) -> list[str]:
    """Anything the case left behind: listeners, bookkeeping, sockets or tasks."""
    problems = []
    for name in ("active", "runners", "sites", "servers", "bound"):
        if getattr(adapter, name):
            problems.append(f"leak: adapter.{name} still holds {sorted(getattr(adapter, name))}")
    current = asyncio.current_task()
    left: set[asyncio.Task] = set()
    for _ in range(SETTLE_ROUNDS):
        left = {task for task in asyncio.all_tasks() - before
                if task is not current and not task.done()}
        if not left:
            break
        await asyncio.sleep(0.01)
    problems += [f"leak: task {task.get_name()} ({task.get_coro()!r}) outlived the case"
                 for task in left]
    if bound is not None:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(*bound), 1)
        except (OSError, asyncio.TimeoutError):
            pass
        else:
            writer.close()
            problems.append(f"leak: {bound[0]}:{bound[1]} still accepts connections")
    return problems


async def run(selection: Selection = Selection(), progress=None) -> Report:
    plan = await build_plan(selection)
    report = Report(plan)
    references: dict[tuple[str, str], ProfileReference] = {}
    for case in plan.cases:
        key = (case.platform, case.profile)
        if key not in references:
            references[key] = profiles(case.platform)[case.profile]
        result = await run_case(case, references[key])
        report.results.append(result)
        if progress is not None:
            progress(result)
    return report
