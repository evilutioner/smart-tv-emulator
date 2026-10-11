"""Run upstream open-source clients against the emulator and keep the result.

    python -m tvemu.clients list
    python -m tvemu.clients run <platform>/<client>               # the last green version
    python -m tvemu.clients run <platform>/<client> --version latest
    python -m tvemu.clients run <platform>/<client> --record      # keep it under docs/clients/
    python -m tvemu.clients report [--check]

A run downloads the client, so it is never part of the offline gates. Exit status is 0 when
every profile passes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import report
from .model import client_specs, find_spec
from .runner import repository_root, run


def _print_summary(record: dict) -> None:
    client = record["client"]
    print(f"{record['platform']}/{client['name']} {client['version'] or client['requested']}"
          f"{' @ ' + client['commit'][:12] if client['commit'] else ''} → {record['verdict'].upper()}")
    for profile in record["profiles"]:
        counts: dict[str, int] = {}
        for step in profile["steps"]:
            counts[step["status"]] = counts.get(step["status"], 0) + 1
        summary = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
        print(f"  {profile['profile']:<40} {profile['verdict']:<5} {summary}")
        for problem in profile["problems"]:
            print(f"    - {problem}")
        for gap in profile["gaps"]:
            print(f"    · {'known gap' if gap['known'] else 'GAP'} {gap['operation']} ×{gap['count']}")
    for operation in record["stale_gaps"]:
        print(f"  - declared gap never met, stale: {operation}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tvemu.clients", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    lister = commands.add_parser("list", help="the clients this build declares")
    lister.add_argument("--json", action="store_true",
                        help="one object per client, for a CI matrix")
    runner = commands.add_parser("run", help="install one client and drive the emulator with it")
    runner.add_argument("client", help="<platform>/<client>, as `list` prints it")
    runner.add_argument("--version", default="",
                        help="a release, a git ref, or `latest` (default: the last green one)")
    runner.add_argument("--profile", action="append", default=[],
                        help="drive only this profile; repeatable (stale gaps are then not judged)")
    runner.add_argument("--record", action="store_true",
                        help="write the run under docs/clients/ and re-render the page; "
                             "needs a clean checkout")
    runner.add_argument("--json", type=Path, help="also write the run record here")
    runner.add_argument("--events", type=Path, help="keep each profile's event log in this directory")
    pages = commands.add_parser("report", help="re-render docs/clients/<platform>.md")
    pages.add_argument("--check", action="store_true", help="fail when a page is out of date")
    args = parser.parse_args(argv)

    if args.command == "list":
        if args.json:
            print(json.dumps([{"client": spec.key, "id": f"{spec.platform}-{spec.name}",
                               "install": spec.install, "last_green": spec.last_green}
                              for spec in client_specs()]))
            return 0
        for spec in client_specs():
            print(f"{spec.key:<32} {spec.install:<5} last green {spec.last_green or '-':<12} "
                  f"{', '.join(spec.profiles)}")
        return 0

    root = repository_root()
    if args.command == "report":
        if root is None:
            parser.error("report renders into a checkout; this emulator runs from a wheel")
        stale = []
        for path, text in report.pages(root).items():
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current == text:
                continue
            if args.check:
                stale.append(path.relative_to(root).as_posix())
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                print(f"wrote {path.relative_to(root)}")
        for name in stale:
            print(f"out of date: {name}", file=sys.stderr)
        return 1 if stale else 0

    spec = find_spec(args.client)
    if args.record and root is None:
        parser.error("--record writes into a checkout; this emulator runs from a wheel")
    record = run(spec, args.version, tuple(args.profile), args.events)
    _print_summary(record)
    if args.json:
        args.json.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.record:
        if not record["emulator"]["clean"]:
            print("Not recorded: src/ has uncommitted changes, so the version does not name "
                  "what ran. Commit, then run again.", file=sys.stderr)
            return 1
        if args.profile:
            print("Not recorded: a record covers every declared profile.", file=sys.stderr)
            return 1
        path = report.write_record(root, record)
        print(f"recorded {path.relative_to(root)}")
        text = report.render(root, spec.platform)
        if text is not None:
            page = report.page_path(root, spec.platform)
            page.write_text(text, encoding="utf-8")
            print(f"wrote {page.relative_to(root)}")
    version = record["client"]["commit"] or record["client"]["version"]
    if record["verdict"] == "pass" and version and version != spec.last_green:
        print(f"Passed on {version}; last_green in {spec.root.name}/client.toml can move to it.")
    return 0 if record["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
