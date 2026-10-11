"""Curated knowledge that raw captures cannot establish on their own.

Observed fields and wire types belong to the evidence-derived IR.  Claims are deliberately
smaller: requiredness, value domains, constraints, serialisation rules and conditional
behaviour.  Every claim owns its provenance so one message may combine captured facts, a
live probe and what clients expect without pretending they are the same source.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import EvidenceRef


@dataclass(frozen=True)
class Claim:
    path: str
    rationale: str
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if not self.rationale:
            raise ValueError(f"{self.path or '(document)'}: a claim needs a rationale")
        if not self.evidence:
            raise ValueError(f"{self.path or '(document)'}: a claim needs evidence")

    @property
    def kind(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class PresenceClaim(Claim):
    presence: str = "optional"     # required | optional | absent
    scope: str = "all"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.presence not in ("required", "optional", "absent"):
            raise ValueError(f"{self.path}: invalid presence {self.presence}")

    @property
    def kind(self) -> str: return "presence"


@dataclass(frozen=True)
class ClaimedValue:
    literal: Any
    evidence: tuple[EvidenceRef, ...]
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError(f"Value {self.literal!r} needs evidence")


@dataclass(frozen=True)
class ValueSetClaim(Claim):
    values: tuple[ClaimedValue, ...] = ()
    closed: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.values:
            raise ValueError(f"{self.path}: a value set cannot be empty")

    @property
    def kind(self) -> str: return "values"


@dataclass(frozen=True)
class ConstraintClaim(Claim):
    constraint: str = ""
    value: Any = None
    violation: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.constraint not in (
            "min_length", "max_length", "minimum", "maximum", "pattern", "nullable",
            "wire_type",
        ):
            raise ValueError(f"{self.path}: unsupported constraint {self.constraint!r}")

    @property
    def kind(self) -> str: return "constraint"


@dataclass(frozen=True)
class SerializationClaim(Claim):
    feature: str = ""
    value: Any = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.feature:
            raise ValueError(f"{self.path}: a serialization claim needs a feature")

    @property
    def kind(self) -> str: return "serialization"


@dataclass(frozen=True)
class BehaviorClaim(Claim):
    condition: str = ""
    outcome: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.condition or not self.outcome:
            raise ValueError("A behavior claim needs both a condition and an outcome")

    @property
    def kind(self) -> str: return "behavior"


@dataclass(frozen=True)
class OperationClaims:
    operation_id: str
    summary: str
    claims: tuple[Claim, ...] = ()

    def required_paths(self) -> frozenset[str]:
        return frozenset(claim.path for claim in self.claims
                         if isinstance(claim, PresenceClaim)
                         and claim.presence == "required")

    def at(self, path: str) -> tuple[Claim, ...]:
        return tuple(claim for claim in self.claims if claim.path == path)
