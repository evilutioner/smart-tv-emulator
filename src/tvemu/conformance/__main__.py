"""python -m tvemu.conformance: replay captured traffic through the real listeners.

Exit 0 only when every selected case passes and every replay of the selected profiles is
covered; 1 for a wire mismatch, a leak, a timeout or uncovered coverage; 2 when evidence or
a profile cannot be turned into cases.

`--gate` is the merge gate: a failed case still fails everywhere, but an uncovered replay
fails only on a platform whose conformance package declares `COVERAGE = "complete"`.
Evidence scenarios are counted separately and use EVIDENCE_COVERAGE for the same gate.
Elsewhere a gap stays visible in the report without failing the build.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .model import CaseResult, Report
from .runner import (PlanError, Selection, build_plan, coverage_complete,
                     evidence_coverage_complete, run)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tvemu.conformance",
                                     description=__doc__.splitlines()[0])
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="every platform and profile")
    scope.add_argument("--platform", help="one platform id")
    scope.add_argument("--case", help="one case id, as --list prints it")
    parser.add_argument("--profile", help="one profile of --platform")
    parser.add_argument("--list", action="store_true",
                        help="print the cases and the uncovered replays without running")
    parser.add_argument("--json-report", type=Path, help="write a machine-readable report")
    parser.add_argument("--verbose", action="store_true", help="print notes as well")
    parser.add_argument("--gate", action="store_true",
                        help="fail on uncovered replays only where coverage is declared "
                             "complete")
    return parser


def _selection(args: argparse.Namespace) -> Selection:
    if args.case:
        platform, _, rest = args.case.partition("/")
        return Selection(platform, rest.partition("/")[0], args.case)
    return Selection(args.platform or "", args.profile or "")


def _line(result: CaseResult, verbose: bool) -> str:
    mark = "PASS" if result.passed else "FAIL"
    lines = [f"{mark}  {result.case.id}  ({result.duration * 1000:.0f} ms)"]
    lines += [f"      {problem}" for problem in result.problems]
    if verbose:
        lines += [f"      note: {note}" for note in result.notes]
    return "\n".join(lines)


def _print_gaps(plan) -> None:
    if plan.gaps:
        print(f"\nUncovered replays ({len(plan.gaps)}):")
    for gap in plan.gaps:
        print(f"GAP   {gap.platform}/{gap.profile}/{gap.exchange}  [{gap.replay}]  "
              f"{gap.reason}")
    if plan.evidence_gaps:
        print(f"\nUncovered evidence scenarios ({len(plan.evidence_gaps)}):")
    for gap in plan.evidence_gaps:
        print(f"EVIDENCE GAP   {gap.platform}/{gap.profile}/{gap.replay}: {gap.reason}")


def _print_summary(report: Report) -> None:
    print("\nSummary (replays):")
    for key, row in sorted(report.summary().items()):
        print(f"  {key:60} passed {row['passed']:4}  failed {row['failed']:4}  "
              f"uncovered {row['uncovered']:4}")
    totals = report.totals()
    print(f"\n{totals['passed']}/{totals['cases']} cases passed; "
          f"{totals['passed_replays']}/{totals['replays']} replays verified, "
          f"{totals['uncovered_replays']} uncovered")
    if totals["evidence_scenarios"]:
        print(f"Evidence scenarios: {totals['passed_evidence_scenarios']}/"
              f"{totals['evidence_scenarios']} passed; "
              f"{totals['uncovered_evidence_scenarios']} uncovered")


async def _main(args: argparse.Namespace) -> int:
    if args.profile and not args.platform:
        print("--profile needs --platform", file=sys.stderr)
        return 2
    selection = _selection(args)
    try:
        if args.list:
            plan = await build_plan(selection)
            for case in plan.cases:
                label = "EVIDENCE" if case.scope == "evidence" else "CASE"
                source = (f"{case.capture}/{case.exchanges[0]} steps {case.evidence_steps}"
                          if case.scope == "evidence" else ', '.join(case.replays))
                print(f"{label}  {case.id}  [{source}]  {case.driver} via {case.protocol}")
            _print_gaps(plan)
            print(f"\n{len(plan.cases)} cases, {len(plan.gaps)} uncovered of "
                  f"{plan.replays} replays; {plan.evidence_scenarios} evidence scenarios, "
                  f"{len(plan.evidence_gaps)} uncovered")
            return 0 if plan.cases or plan.gaps or plan.evidence_gaps else 2
        report = await run(selection, lambda result: print(_line(result, args.verbose)))
    except PlanError as exc:
        print(f"conformance: {exc}", file=sys.stderr)
        return 2
    if not report.plan.cases and not report.plan.gaps and not report.plan.evidence_gaps:
        print("conformance: nothing matched the selection", file=sys.stderr)
        return 2
    _print_gaps(report.plan)
    _print_summary(report)
    if args.json_report:
        args.json_report.write_text(json.dumps(report.to_json(), indent=2) + "\n",
                                    encoding="utf-8")
    if not report.passed:
        return 1
    if args.gate:
        owed = sorted({gap.platform for gap in report.plan.gaps
                       if coverage_complete(gap.platform)})
        owed += sorted({gap.platform for gap in report.plan.evidence_gaps
                        if evidence_coverage_complete(gap.platform)})
        if owed:
            print(f"conformance: coverage is declared complete but replays are uncovered on "
                  f"{', '.join(owed)}", file=sys.stderr)
            return 1
        return 0
    return 0 if report.complete else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main(_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
