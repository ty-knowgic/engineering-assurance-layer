"""
Spec extractor — deterministic, regex/section-based extraction from markdown.

Conventions for V0.0.1 (documented in README):
  ## Signals       → Signal definitions
  ## States        → State definitions
  ## Modes         → Mode definitions
  ## Transitions   → State transition definitions
  ## Entities      → Entity definitions
  ## Requirements  → REQ-NNN: ... lines
  ## Assumptions   → ASM-NNN: ... lines
  ## Safety Constraints  → CON-NNN: ... lines
  ## Forbidden Conditions → FC-NNN: ... lines
  ## Timing Constraints   → TC-NNN: ... lines

All extraction is best-effort — partial results are valid.
Warnings are appended to ir.extraction_warnings.
"""

from __future__ import annotations

import re
from typing import Optional

from eal.ingestion.loaders import SpecDocument
from eal.ir.schema import (
    Assumption, AssumptionType, Bounds, Constraint, ConstraintType,
    Entity, IRSnapshot, Mode, Requirement, Signal, SignalKind,
    SourceRef, State, Transition,
)

# ── Regex patterns ────────────────────────────────────────────────────────────

# REQ-001: text...
_REQ_RE = re.compile(r"^[-*]?\s*(REQ-\d+)\s*:\s*(.+)$", re.IGNORECASE)
_ASM_RE = re.compile(r"^[-*]?\s*(ASM-\d+)\s*:\s*(.+)$", re.IGNORECASE)
_CON_RE = re.compile(r"^[-*]?\s*(CON-\d+)\s*:\s*(.+)$", re.IGNORECASE)
_FC_RE  = re.compile(r"^[-*]?\s*(FC-\d+)\s*:\s*(.+)$", re.IGNORECASE)
_TC_RE  = re.compile(r"^[-*]?\s*(TC-\d+)\s*:\s*(.+)$", re.IGNORECASE)

# signal_name: kind, unit, bounds=[min, max]
_SIGNAL_RE = re.compile(
    r"^[-*]?\s*(\w+)\s*:\s*(sensor|actuator|internal|mode|timing|derived)"
    r"(?:\s*,\s*([^,\[]+?))?(?:\s*,\s*bounds=\[([^\]]*)\])?\s*$",
    re.IGNORECASE,
)
# state_name: description
_STATE_RE = re.compile(r"^[-*]?\s*(\w+)\s*:\s*(.+)$")
# entity_name: description
_ENTITY_RE = re.compile(r"^[-*]?\s*(\w+)\s*:\s*(.+)$")
# mode_name: description
_MODE_RE = re.compile(r"^[-*]?\s*(\w+)\s*:\s*(.+)$")
# FROM_STATE -> TO_STATE: guard=...
_TRANSITION_RE = re.compile(
    r"^[-*]?\s*(\w+)\s*->\s*(\w+)(?:\s*:\s*(.*))?$"
)

# Extract numeric bounds from requirement text:  <= 1.2, >= 0, < 100, > 0
_BOUND_RE = re.compile(r"([<>]=?)\s*([\d.]+)\s*([a-zA-Z/_]+)?")
# Extract operator + value groups: "must remain <= 1.2 rad/s"
_OP_VALUE_RE = re.compile(r"(<=|>=|<(?!=)|>(?!=)|==|!=)\s*([\d.]+)")


def _source(spec: SpecDocument, section: str, line_idx: Optional[int] = None) -> SourceRef:
    return SourceRef(file=str(spec.path), section=section, line=line_idx)


def _parse_bounds_from_text(text: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
    """Return (operator, value, unit) from constraint text, or (None, None, None)."""
    m = _OP_VALUE_RE.search(text)
    if not m:
        return None, None, None
    op = m.group(1)
    val = float(m.group(2))
    # Try to grab unit after the value
    rest = text[m.end():].strip().split()[0] if text[m.end():].strip() else None
    unit = rest if rest and re.match(r"^[a-zA-Z/_]+$", rest) else None
    return op, val, unit


def _parse_signals(lines: list[str], spec: SpecDocument, section: str) -> list[Signal]:
    signals = []
    for i, line in enumerate(lines):
        m = _SIGNAL_RE.match(line.strip())
        if not m:
            continue
        name, kind_raw, unit_raw, bounds_raw = m.groups()
        kind = SignalKind(kind_raw.lower()) if kind_raw else SignalKind.UNKNOWN
        unit = unit_raw.strip() if unit_raw else None

        bounds: Optional[Bounds] = None
        if bounds_raw:
            parts = [p.strip() for p in bounds_raw.split(",")]
            try:
                bmin = float(parts[0]) if parts[0] not in ("", "null", "None") else None
                bmax = float(parts[1]) if len(parts) > 1 and parts[1] not in ("", "null", "None") else None
                bounds = Bounds(min=bmin, max=bmax, unit=unit)
            except (ValueError, IndexError):
                pass

        signals.append(Signal(
            name=name,
            kind=kind,
            unit=unit,
            bounds=bounds,
            source_ref=_source(spec, section, i),
        ))
    return signals


def _parse_states(lines: list[str], spec: SpecDocument, section: str) -> list[State]:
    states = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _STATE_RE.match(stripped)
        if m:
            states.append(State(
                name=m.group(1),
                description=m.group(2).strip(),
                source_ref=_source(spec, section, i),
            ))
    return states


def _parse_modes(lines: list[str], spec: SpecDocument, section: str) -> list[Mode]:
    modes = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _MODE_RE.match(stripped)
        if m:
            modes.append(Mode(
                name=m.group(1),
                description=m.group(2).strip(),
                source_ref=_source(spec, section, i),
            ))
    return modes


def _parse_entities(lines: list[str], spec: SpecDocument, section: str) -> list[Entity]:
    entities = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _ENTITY_RE.match(stripped)
        if m:
            entities.append(Entity(
                name=m.group(1),
                description=m.group(2).strip(),
                source_ref=_source(spec, section, i),
            ))
    return entities


def _parse_transitions(lines: list[str], spec: SpecDocument, section: str) -> list[Transition]:
    transitions = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _TRANSITION_RE.match(stripped)
        if m:
            from_s, to_s, guard = m.group(1), m.group(2), m.group(3)
            guard_clean: Optional[str] = None
            if guard:
                # Strip "guard=" prefix if present
                guard_clean = re.sub(r"^guard\s*=\s*", "", guard.strip())
            transitions.append(Transition(
                from_state=from_s,
                to_state=to_s,
                guard_condition=guard_clean or None,
                source_ref=_source(spec, section, i),
            ))
    return transitions


def _parse_requirements(lines: list[str], spec: SpecDocument, section: str) -> list[Requirement]:
    reqs = []
    for i, line in enumerate(lines):
        m = _REQ_RE.match(line.strip())
        if not m:
            continue
        req_id, text = m.group(1).upper(), m.group(2).strip()
        reqs.append(Requirement(
            id=req_id,
            text=text,
            source_ref=_source(spec, section, i),
        ))
    return reqs


def _parse_assumptions(lines: list[str], spec: SpecDocument, section: str) -> list[Assumption]:
    assumptions = []
    for i, line in enumerate(lines):
        m = _ASM_RE.match(line.strip())
        if not m:
            continue
        asm_id, text = m.group(1).upper(), m.group(2).strip()
        # Classify by keywords
        text_lower = text.lower()
        if any(w in text_lower for w in ("latency", "response time", "ms", "timing")):
            atype = AssumptionType.TIMING
        elif any(w in text_lower for w in ("hardware", "vendor", "sensor", "actuator")):
            atype = AssumptionType.HARDWARE
        elif any(w in text_lower for w in ("environment", "temperature", "humidity")):
            atype = AssumptionType.ENVIRONMENT
        elif any(w in text_lower for w in ("operator", "human", "user")):
            atype = AssumptionType.OPERATOR
        else:
            atype = AssumptionType.UNCLASSIFIED
        assumptions.append(Assumption(
            id=asm_id,
            text=text,
            assumption_type=atype,
            source_ref=_source(spec, section, i),
        ))
    return assumptions


def _parse_constraints(
    lines: list[str],
    spec: SpecDocument,
    section: str,
    pattern: re.Pattern,
    ctype: ConstraintType,
    prefix: str,
) -> list[Constraint]:
    constraints = []
    for i, line in enumerate(lines):
        m = pattern.match(line.strip())
        if not m:
            continue
        cid, text = m.group(1).upper(), m.group(2).strip()

        op, val, unit = _parse_bounds_from_text(text)

        # Extract signal/state/mode references by token matching
        tokens = re.findall(r"\b([A-Z][A-Z_0-9]+|[a-z][a-z_0-9]+)\b", text)
        # Heuristic: uppercase tokens tend to be states/modes, lowercase are signals
        related_signals = [t for t in tokens if t and t[0].islower() and len(t) > 2]
        related_states_modes = [t for t in tokens if t and t[0].isupper() and len(t) > 2]

        constraints.append(Constraint(
            id=cid,
            expression_text=text,
            constraint_type=ctype,
            related_signals=list(dict.fromkeys(related_signals)),
            related_states=related_states_modes,
            numeric_value=val,
            operator=op,
            source_ref=_source(spec, section, i),
        ))
    return constraints


def _link_requirements_to_ir(
    reqs: list[Requirement],
    signals: list[Signal],
    states: list[State],
    modes: list[Mode],
    constraints: list[Constraint],
) -> None:
    """Back-fill parsed_signals/states/modes on requirements by token matching."""
    signal_names = {s.name.lower(): s.name for s in signals}
    state_names = {s.name.lower(): s.name for s in states}
    mode_names = {m.name.lower(): m.name for m in modes}
    constraint_ids = {c.id for c in constraints}

    for req in reqs:
        tokens = re.findall(r"\b\w+\b", req.text)
        for tok in tokens:
            tl = tok.lower()
            if tl in signal_names:
                if signal_names[tl] not in req.parsed_signals:
                    req.parsed_signals.append(signal_names[tl])
            if tok in state_names.values() or tok in {v for v in state_names.values()}:
                if tok not in req.parsed_states:
                    req.parsed_states.append(tok)
            if tok in mode_names.values():
                if tok not in req.parsed_modes:
                    req.parsed_modes.append(tok)
        # Link constraints by shared signal
        for con in constraints:
            if any(s in req.parsed_signals for s in con.related_signals):
                if con.id not in req.parsed_constraints:
                    req.parsed_constraints.append(con.id)


# ── Public API ────────────────────────────────────────────────────────────────

def extract_ir_from_spec(spec: SpecDocument) -> IRSnapshot:
    """
    Extract an IRSnapshot from a SpecDocument.
    All sections are optional — absent sections produce empty lists.
    """
    sections = spec.sections()
    warnings: list[str] = []

    def get(key: str) -> list[str]:
        # Case-insensitive section lookup
        for k, v in sections.items():
            if k.lower() == key.lower():
                return v
        return []

    signals   = _parse_signals(get("Signals"), spec, "Signals")
    states    = _parse_states(get("States"), spec, "States")
    modes     = _parse_modes(get("Modes"), spec, "Modes")
    entities  = _parse_entities(get("Entities"), spec, "Entities")
    transitions = _parse_transitions(get("Transitions"), spec, "Transitions")
    requirements = _parse_requirements(get("Requirements"), spec, "Requirements")
    assumptions  = _parse_assumptions(get("Assumptions"), spec, "Assumptions")

    safety_constraints = _parse_constraints(
        get("Safety Constraints"), spec, "Safety Constraints", _CON_RE,
        ConstraintType.INVARIANT, "CON",
    )
    forbidden_conditions = _parse_constraints(
        get("Forbidden Conditions"), spec, "Forbidden Conditions", _FC_RE,
        ConstraintType.FORBIDDEN, "FC",
    )
    timing_constraints = _parse_constraints(
        get("Timing Constraints"), spec, "Timing Constraints", _TC_RE,
        ConstraintType.TIMING, "TC",
    )

    all_constraints = safety_constraints + forbidden_conditions + timing_constraints

    if not signals:
        warnings.append("No signals found. Add a '## Signals' section to your spec.")
    if not states:
        warnings.append("No states found. Add a '## States' section to your spec.")
    if not requirements:
        warnings.append("No requirements found. Add a '## Requirements' section with REQ-NNN: format.")

    _link_requirements_to_ir(requirements, signals, states, modes, all_constraints)

    return IRSnapshot(
        spec_file=str(spec.path),
        entities=entities,
        signals=signals,
        states=states,
        modes=modes,
        transitions=transitions,
        requirements=requirements,
        constraints=all_constraints,
        assumptions=assumptions,
        extraction_warnings=warnings,
    )
