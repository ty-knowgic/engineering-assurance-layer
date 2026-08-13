"""
Normalised finding schema for Engineering Assurance Layer.

A Finding is any identified issue — from a deterministic rule check or from
a Z3 solver check. The schema is stable and machine-readable.

Severity levels (adapted from Synthetic Danger's ImpactFinding severity):
  CRITICAL  → blocks sign-off; likely unsafe or unsatisfiable
  HIGH      → significant assurance gap; must be addressed before release
  MEDIUM    → notable gap or inconsistency; review recommended
  LOW       → minor quality issue or informational note

Categories:
  MISSING_ASSUMPTION   → undeclared assumption required for spec to be consistent
  MISSING_BOUND        → signal lacks required upper/lower bound
  UNDEFINED_REFERENCE  → requirement mentions signal/state not defined in model
  CONTRADICTORY_CONSTRAINT → two constraints that cannot hold simultaneously
  TIMING_GAP           → timing requirement but no timing parameter in model
  FORBIDDEN_UNCHECKED  → forbidden condition with no guard or detection mechanism
  UNREACHABLE_STATE    → state/mode reachable but blocked by constraints
  TRANSITION_GAP       → transition references undefined state
  CODE_BOUND_MISMATCH  → code constant/threshold is looser than spec/model bound
  CODE_TIMING_MISMATCH → code timing parameter exceeds required response limit
  CODE_UNMODELED_PARAMETER → code parameter appears engineering-relevant but unmodeled
  CONSTRAINT_CONFLICT  → legacy generic constraint contradiction category
  GLOBAL_CONSTRAINT_CONFLICT → contradiction present independent of active mode
  MODE_SCOPED_CONFLICT → contradiction appears when a specific mode is active
  UNSAT_IN_MODE        → signal-level unsatisfiable bound/constraint set in one mode
  SOLVER_COUNTEREXAMPLE → Z3 found a concrete counterexample
  NAV2_ACCEL_OVERDECLARED → controller assumes stronger accel/decel than the
      downstream velocity_smoother will pass through (unsafe-leaning direction)
  NAV2_VELOCITY_OVERDECLARED → controller plans at speeds the smoother clamps
      away (model-fidelity, not unsafe-leaning)
  NAV2_LIMIT_HEADROOM  → controller is configured more conservatively than the
      platform allows; informational
  NAV2_HORIZON_EXCEEDS_COSTMAP → MPPI prediction horizon at max speed exceeds
      the local costmap radius (upstream-documented rule)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FindingSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FindingCategory(str, Enum):
    MISSING_ASSUMPTION = "MISSING_ASSUMPTION"
    MISSING_BOUND = "MISSING_BOUND"
    UNDEFINED_REFERENCE = "UNDEFINED_REFERENCE"
    CONTRADICTORY_CONSTRAINT = "CONTRADICTORY_CONSTRAINT"
    TIMING_GAP = "TIMING_GAP"
    FORBIDDEN_UNCHECKED = "FORBIDDEN_UNCHECKED"
    UNREACHABLE_STATE = "UNREACHABLE_STATE"
    TRANSITION_GAP = "TRANSITION_GAP"
    CODE_BOUND_MISMATCH = "CODE_BOUND_MISMATCH"
    CODE_TIMING_MISMATCH = "CODE_TIMING_MISMATCH"
    CODE_UNMODELED_PARAMETER = "CODE_UNMODELED_PARAMETER"
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    GLOBAL_CONSTRAINT_CONFLICT = "GLOBAL_CONSTRAINT_CONFLICT"
    MODE_SCOPED_CONFLICT = "MODE_SCOPED_CONFLICT"
    UNSAT_IN_MODE = "UNSAT_IN_MODE"
    SOLVER_COUNTEREXAMPLE = "SOLVER_COUNTEREXAMPLE"
    NAV2_ACCEL_OVERDECLARED = "NAV2_ACCEL_OVERDECLARED"
    NAV2_VELOCITY_OVERDECLARED = "NAV2_VELOCITY_OVERDECLARED"
    NAV2_LIMIT_HEADROOM = "NAV2_LIMIT_HEADROOM"
    NAV2_HORIZON_EXCEEDS_COSTMAP = "NAV2_HORIZON_EXCEEDS_COSTMAP"


class Finding(BaseModel):
    """A single assurance finding from any check stage."""

    id: str = Field(description="Stable ID, e.g. F-001")
    severity: FindingSeverity
    category: FindingCategory
    title: str
    summary: str
    details: str = ""
    related_ir_nodes: list[str] = Field(default_factory=list, description="Signal/state/req IDs")
    source_refs: list[str] = Field(default_factory=list, description="file:section or file:line")
    evidence_refs: list[str] = Field(default_factory=list, description="Supporting IR evidence")
    suggested_fix: str = ""
    # Solver-specific: counterexample values
    counterexample: Optional[dict] = None


def assign_ids(findings: list[Finding]) -> list[Finding]:
    """Re-assign stable F-NNN IDs in severity order."""
    ordered = sorted(
        findings,
        key=lambda f: (
            ["CRITICAL", "HIGH", "MEDIUM", "LOW"].index(f.severity.value),
            f.category.value,
        ),
    )
    for i, f in enumerate(ordered, start=1):
        f.id = f"F-{i:03d}"
    return ordered


_SEVERITY_RANK: dict[str, int] = {
    "NONE": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def severity_rank(severity: str | FindingSeverity) -> int:
    """Return deterministic severity rank for threshold comparisons."""
    value = severity.value if isinstance(severity, FindingSeverity) else str(severity)
    return _SEVERITY_RANK.get(value.upper(), 0)


def highest_severity(findings: list[Finding]) -> str:
    """Return highest finding severity, or NONE when no findings exist."""
    if not findings:
        return "NONE"
    return max((f.severity.value for f in findings), key=severity_rank)


def meets_or_exceeds_threshold(
    severity: str | FindingSeverity,
    threshold: str | FindingSeverity,
) -> bool:
    """True when severity is >= threshold in deterministic rank order."""
    threshold_rank = severity_rank(threshold)
    if threshold_rank <= 0:
        return False
    return severity_rank(severity) >= threshold_rank
