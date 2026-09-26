"""Check what a client did against the event log: the assertion half of a driver test.

A scenario is JSON:

    {"description": "pair, then press Home",
     "ordered": true,
     "expect": [{"operation": "keypress/Home", "status": 200}],
     "forbid": [{"status": 403}]}

Each pattern matches an event when every field it names is equal; a string ending in `*`
matches by prefix. `expect` is a subsequence when `ordered` (the default) and a set of
independent matches otherwise; any event matching a `forbid` pattern fails the check.

    python -m tvemu.expect scenario.json                      # the running emulator
    python -m tvemu.expect scenario.json --events log.jsonl   # an exported log
    python -m tvemu.expect scenario.json --since 41           # only events after id 41

Exit status 0 when the scenario holds, 1 with the first unmet expectation otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8888"
# The fields an explanation prints for each nearby event: enough to see what arrived.
SUMMARY = ("id", "kind", "operation", "transport", "status", "detail")


def matches(event: dict, pattern: dict) -> bool:
    for name, wanted in pattern.items():
        value = event.get(name)
        if isinstance(wanted, str) and wanted.endswith("*"):
            if not isinstance(value, str) or not value.startswith(wanted[:-1]):
                return False
        elif value != wanted:
            return False
    return True


def summary(event: dict) -> str:
    return " ".join(f"{name}={event[name]!r}" for name in SUMMARY
                    if event.get(name) not in (None, ""))


def check(events: list[dict], scenario: dict, since: int = 0) -> list[str]:
    """Every way the events fall short of the scenario; empty when it holds."""
    if not isinstance(scenario, dict):
        raise ValueError("A scenario is a JSON object")
    expect = scenario.get("expect") or []
    forbid = scenario.get("forbid") or []
    for pattern in (*expect, *forbid):
        if not isinstance(pattern, dict) or not pattern:
            raise ValueError(f"A pattern is a non-empty JSON object, not {pattern!r}")
    events = [event for event in events if int(event.get("id") or 0) > since]
    problems: list[str] = []

    if scenario.get("ordered", True):
        position = 0
        for number, pattern in enumerate(expect, 1):
            found = next((index for index in range(position, len(events))
                          if matches(events[index], pattern)), None)
            if found is None:
                problems.append(_unmet(number, pattern, events[position:]))
                break
            position = found + 1
    else:
        for number, pattern in enumerate(expect, 1):
            if not any(matches(event, pattern) for event in events):
                problems.append(_unmet(number, pattern, events))

    for pattern in forbid:
        for event in events:
            if matches(event, pattern):
                problems.append(f"forbidden {json.dumps(pattern)} matched: {summary(event)}")
    return problems


def _unmet(number: int, pattern: dict, rest: list[dict]) -> str:
    tail = rest[-5:]
    lines = [f"expectation {number} {json.dumps(pattern)} was not met"]
    lines += ["  the last events considered:" if tail else "  no events were considered"]
    lines += [f"    {summary(event)}" for event in tail]
    return "\n".join(lines)


def read_jsonl(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def fetch_events(url: str = DEFAULT_URL) -> list[dict]:
    from aiohttp import ClientSession
    async with ClientSession() as session:
        async with session.get(f"{url.rstrip('/')}/api/v1/events/export") as response:
            response.raise_for_status()
            return read_jsonl(await response.text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tvemu.expect", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--url", default=DEFAULT_URL, help="the emulator's dashboard address")
    parser.add_argument("--events", type=Path, help="check an exported JSONL log instead")
    parser.add_argument("--since", type=int, default=0, help="ignore events up to this id")
    args = parser.parse_args(argv)
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    events = (read_jsonl(args.events.read_text(encoding="utf-8")) if args.events
              else asyncio.run(fetch_events(args.url)))
    problems = check(events, scenario, since=args.since)
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"ok: {scenario.get('description') or args.scenario.name}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
