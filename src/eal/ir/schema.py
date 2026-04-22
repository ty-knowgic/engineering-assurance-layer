"""
Intermediate Representation (IR) schema for Engineering Assurance Layer.

The IR is the central data structure that all pipeline stages read/write.
It is engineering-domain-neutral by design — no hazard jargon, no ECO terminology.

Key design rules:
- Every item carries a source_ref so findings can point back to origin
- All fields are optional-safe: partial extraction is valid
- The IR is serialisable to JSON at any point (ir_snapshot.json)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Source traceability ───────────────────────────────────────────────────────

class SourceRef(BaseModel):
    file: str
    section: Optional[str] = None
    line: Optional[int] = None
    raw_text: Optional[str] = None


# ── Enumerations ──────────────────────────────────────────────────────────────

class SignalKind(str, Enum):
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    INTERNAL = "internal"
    MODE = "mode"
    TIMING = "timing"
    DERIVED = "derived"
    UNKNOWN = "unknown"


class ConstraintType(str, Enum):
    BOUND = "bound"           # value <= X, value >= Y
    INVARIANT = "invariant"   # always-true condition
    TRANSITION = "transition" # applies during a state change
    TIMING = "timing"         # temporal: within N ms
    RELATION = "relation"     # A implies B, A requires B
    FORBIDDEN = "forbidden"   # must never hold


class AssumptionType(str, Enum):
    HARDWARE = "hardware"
    ENVIRONMENT = "environment"
    TIMING = "timing"
    OPERATOR = "operator"
    EXTERNAL = "external"
    UNCLASSIFIED = "unclassified"


# ── Core IR nodes ─────────────────────────────────────────────────────────────

class Bounds(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    unit: Optional[str] = None


class Signal(BaseModel):
    name: str
    kind: SignalKind = SignalKind.UNKNOWN
    unit: Optional[str] = None
    bounds: Optional[Bounds] = None
    source_ref: Optional[SourceRef] = None


class State(BaseModel):
    name: str
    description: Optional[str] = None
    source_ref: Optional[SourceRef] = None


class Mode(BaseModel):
    name: str
    description: Optional[str] = None
    source_ref: Optional[SourceRef] = None


class Transition(BaseModel):
    from_state: str
    to_state: str
    guard_condition: Optional[str] = None
    forbidden: bool = False
    source_ref: Optional[SourceRef] = None


class Constraint(BaseModel):
    id: str
    expression_text: str
    normalized_form: Optional[str] = None
    constraint_type: ConstraintType = ConstraintType.BOUND
    related_signals: list[str] = Field(default_factory=list)
    related_states: list[str] = Field(default_factory=list)
    related_modes: list[str] = Field(default_factory=list)
    numeric_value: Optional[float] = None
    operator: Optional[str] = None  # "<=", ">=", "==", "!="
    source_ref: Optional[SourceRef] = None


class Assumption(BaseModel):
    id: str
    text: str
    assumption_type: AssumptionType = AssumptionType.UNCLASSIFIED
    source_ref: Optional[SourceRef] = None


class Requirement(BaseModel):
    id: str
    text: str
    parsed_signals: list[str] = Field(default_factory=list)
    parsed_states: list[str] = Field(default_factory=list)
    parsed_modes: list[str] = Field(default_factory=list)
    parsed_constraints: list[str] = Field(default_factory=list)  # constraint IDs
    source_ref: Optional[SourceRef] = None


class Entity(BaseModel):
    name: str
    description: Optional[str] = None
    source_ref: Optional[SourceRef] = None


# ── Top-level IR container ────────────────────────────────────────────────────

class IRSnapshot(BaseModel):
    """Complete intermediate representation for one review run."""

    # Metadata
    spec_file: str
    model_file: Optional[str] = None
    code_files: list[str] = Field(default_factory=list)

    # Structural elements
    entities: list[Entity] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    states: list[State] = Field(default_factory=list)
    modes: list[Mode] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)

    # Semantic elements
    requirements: list[Requirement] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)

    # Extraction notes
    extraction_warnings: list[str] = Field(default_factory=list)

    # ── Lookup helpers ────────────────────────────────────────────────────────

    def signal_names(self) -> set[str]:
        return {s.name for s in self.signals}

    def state_names(self) -> set[str]:
        return {s.name for s in self.states}

    def mode_names(self) -> set[str]:
        return {m.name for m in self.modes}

    def constraint_by_id(self, cid: str) -> Optional[Constraint]:
        return next((c for c in self.constraints if c.id == cid), None)

    def signals_with_bounds(self) -> list[Signal]:
        return [s for s in self.signals if s.bounds is not None]

    def numeric_constraints(self) -> list[Constraint]:
        return [
            c for c in self.constraints
            if c.numeric_value is not None and c.operator is not None
        ]

    def extra_model_fields(self) -> dict[str, Any]:
        """Return dict representation safe for JSON serialisation."""
        return self.model_dump(mode="json")
