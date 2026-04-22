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
  CONSTRAINT_CONFLICT  → Z3-verified contradiction between constraints
  SOLVER_COUNTEREXAMPLE → Z3 found a concrete counterexample
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
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    SOLVER_COUNTEREXAMPLE = "SOLVER_COUNTEREXAMPLE"


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
