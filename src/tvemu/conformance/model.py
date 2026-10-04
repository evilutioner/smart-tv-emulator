"""What a conformance run is made of: cases, the replays nothing covers yet, and results."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True)
class ConformanceCase:
    """One run of captured client input through a real listener of a fresh adapter.

    `exchanges` are ordered and share one adapter; `replays` are the profile's replay names
    whose output this case compares directly.
    """

    id: str
    platform: str
    profile: str
    exchanges: tuple[str, ...]
    protocol: str
    driver: str
    replays: tuple[str, ...]
    timeout: float = DEFAULT_TIMEOUT
    setup: str = ""

    def __post_init__(self) -> None:
        if not self.exchanges:
            raise ValueError(f"{self.id}: a case needs at least one exchange")
        if not self.replays:
            raise ValueError(f"{self.id}: a case covers at least one replay")
        if self.timeout <= 0:
            raise ValueError(f"{self.id}: timeout must be positive")


@dataclass(frozen=True)
class CoverageGap:
    """A replay that no executable case compares. Never a pass: it is red until covered."""

    platform: str
    profile: str
    replay: str
    exchange: str
    transport: str
    reason: str


@dataclass
class CaseResult:
    case: ConformanceCase
    status: str                          # pass | fail
    duration: float = 0.0
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass
class Plan:
    """Every case to run and every replay left uncovered, for the selected profiles."""

    cases: list[ConformanceCase] = field(default_factory=list)
    gaps: list[CoverageGap] = field(default_factory=list)
    replays: int = 0


@dataclass
class Report:
    plan: Plan
    results: list[CaseResult] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.plan.gaps

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def totals(self) -> dict[str, Any]:
        covered = sum(len(result.case.replays) for result in self.results)
        return {
            "cases": len(self.results),
            "passed": sum(result.passed for result in self.results),
            "failed": sum(not result.passed for result in self.results),
            "replays": self.plan.replays,
            "covered_replays": covered,
            "passed_replays": sum(len(result.case.replays)
                                  for result in self.results if result.passed),
            "uncovered_replays": len(self.plan.gaps),
        }

    def summary(self) -> dict[str, dict[str, int]]:
        """Pass/fail/gap counts per platform, profile and transport driver."""
        rows: dict[str, dict[str, int]] = {}

        def bump(key: str, column: str, amount: int = 1) -> None:
            row = rows.setdefault(key, {"passed": 0, "failed": 0, "uncovered": 0})
            row[column] += amount

        for result in self.results:
            column = "passed" if result.passed else "failed"
            case = result.case
            for key in (f"platform {case.platform}",
                        f"profile {case.platform}/{case.profile}",
                        f"driver {case.driver}"):
                bump(key, column, len(case.replays))
        for gap in self.plan.gaps:
            for key in (f"platform {gap.platform}", f"profile {gap.platform}/{gap.profile}",
                        f"transport {gap.transport}"):
                bump(key, "uncovered")
        return rows

    def to_json(self) -> dict[str, Any]:
        return {
            "totals": self.totals(),
            "complete": self.complete,
            "results": [{
                "case": asdict(result.case),
                "status": result.status,
                "duration": round(result.duration, 4),
                "problems": result.problems,
                "notes": result.notes,
            } for result in self.results],
            "uncovered": [asdict(gap) for gap in self.plan.gaps],
        }
