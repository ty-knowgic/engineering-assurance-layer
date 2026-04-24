"""
Spec extractor — deterministic, regex/section-based extraction from markdown.

Current deterministic conventions (documented in README):
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

from dataclasses import dataclass
import re
from typing import Optional

from eal.code_analysis.matching import is_timing_name, normalize_symbol_name
from eal.ingestion.loaders import SpecDocument
from eal.ir.schema import (
    Assumption, AssumptionType, Bounds, Constraint, ConstraintScopeType, ConstraintType,
    Entity, IRSnapshot, Mode, Requirement, RequirementLinkClass, Signal, SignalKind,
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
_MODE_PATTERNS = (
    re.compile(r"\bonly\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s+mode\b", re.IGNORECASE),
    re.compile(r"\bin\s+([A-Za-z_][A-Za-z0-9_]*)\s+mode\b", re.IGNORECASE),
    re.compile(r"\bwhen\s+mode\s*(?:=|==)\s*([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE),
)
_TIMING_WITHIN_RE = re.compile(
    r"\bwithin\s+(\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds)\b",
    re.IGNORECASE,
)
_TIMING_HINT_RE = re.compile(
    r"\b(within|latency|timeout|delay|deadline|response(?:\s+time)?)\b",
    re.IGNORECASE,
)
_GENERIC_LINK_TOKENS = {
    "activation",
    "complete",
    "completed",
    "mode",
    "must",
    "remain",
    "shall",
    "should",
    "when",
    "within",
}


@dataclass(frozen=True)
class _LinkFeatures:
    signals: frozenset[str]
    states: frozenset[str]
    modes: frozenset[str]
    classes: frozenset[RequirementLinkClass]
    operator: Optional[str]
    numeric_value: Optional[float]
    timing_limit_ms: Optional[float]
    is_timing: bool
    is_parameter: bool = False
    parameter_name: Optional[str] = None


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


def _extract_mode_scope(text: str, mode_name_map: dict[str, str]) -> list[str]:
    """Extract deterministic mode qualifiers from constraint/requirement text."""
    modes: list[str] = []
    for pattern in _MODE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            canonical = mode_name_map.get(raw.lower(), raw.upper())
            if canonical not in modes:
                modes.append(canonical)
    return modes


def _scope_fields(applies_in_modes: list[str]) -> tuple[ConstraintScopeType, bool]:
    if applies_in_modes:
        return (ConstraintScopeType.MODE, False)
    return (ConstraintScopeType.GLOBAL, True)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _same_number(a: Optional[float], b: Optional[float], tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def _parse_timing_limit_ms(text: str) -> Optional[float]:
    m = _TIMING_WITHIN_RE.search(text)
    if not m:
        return None
    return float(m.group(1))


def _has_timing_vocabulary(text: str) -> bool:
    return _TIMING_HINT_RE.search(text) is not None


def _normalized_variants(name: str) -> list[str]:
    variants = [name.lower()]
    normalized = normalize_symbol_name(name)
    if normalized:
        variants.append(normalized.replace("_", " "))
    if "_" in name:
        variants.append(name.lower().replace("_", " "))
    return _dedupe([v for v in variants if v])


def _text_mentions_name(text: str, name: str) -> bool:
    for variant in _normalized_variants(name):
        parts = variant.split()
        if not parts:
            continue
        if len(parts) == 1:
            pattern = rf"\b{re.escape(parts[0])}\b"
        else:
            pattern = r"\b" + r"\s+".join(re.escape(part) for part in parts) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _match_known_names(text: str, names: list[str]) -> list[str]:
    matches = [name for name in names if _text_mentions_name(text, name)]
    return _dedupe(matches)


def _bound_compatibility_reason(
    req_op: Optional[str],
    req_value: Optional[float],
    con_op: Optional[str],
    con_value: Optional[float],
) -> Optional[str]:
    if req_op is None or req_value is None or con_op is None or con_value is None:
        return None

    if req_op == con_op and _same_number(req_value, con_value):
        return f"matching bound {req_op} {req_value:g}"

    upper_ops = {"<", "<="}
    lower_ops = {">", ">="}
    if req_op in upper_ops and con_op in upper_ops and con_value <= req_value:
        return f"compatible upper bound {con_op} {con_value:g}"
    if req_op in lower_ops and con_op in lower_ops and con_value >= req_value:
        return f"compatible lower bound {con_op} {con_value:g}"
    return None


def _parameter_name_from_expr(expr: str) -> Optional[str]:
    m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=", expr)
    return m.group(1) if m else None


def _requirement_features(
    req: Requirement,
    signals: list[Signal],
    states: list[State],
    modes: list[Mode],
) -> _LinkFeatures:
    signal_names = [s.name for s in signals]
    state_names = [s.name for s in states]
    mode_names = [m.name for m in modes]
    timing_signals = {s.name for s in signals if s.kind == SignalKind.TIMING}

    parsed_signals = _match_known_names(req.text, signal_names)
    parsed_states = _match_known_names(req.text, state_names)
    parsed_modes = _match_known_names(req.text, mode_names)
    mode_name_map = {m.name.lower(): m.name for m in modes}
    for mode in _extract_mode_scope(req.text, mode_name_map):
        if mode not in parsed_modes:
            parsed_modes.append(mode)

    op, value, _ = _parse_bounds_from_text(req.text)
    timing_limit_ms = _parse_timing_limit_ms(req.text)
    classes: list[RequirementLinkClass] = []

    if timing_limit_ms is not None or _has_timing_vocabulary(req.text) or any(
        signal in timing_signals or is_timing_name(signal)
        for signal in parsed_signals
    ):
        classes.append(RequirementLinkClass.TIMING)
    if parsed_modes:
        classes.append(RequirementLinkClass.MODE_SCOPED)
    if op is not None and value is not None and parsed_signals:
        classes.append(RequirementLinkClass.SIGNAL_BOUND)

    return _LinkFeatures(
        signals=frozenset(parsed_signals),
        states=frozenset(parsed_states),
        modes=frozenset(parsed_modes),
        classes=frozenset(classes),
        operator=op,
        numeric_value=value,
        timing_limit_ms=timing_limit_ms,
        is_timing=RequirementLinkClass.TIMING in classes,
    )


def _constraint_features(
    con: Constraint,
    signals: list[Signal],
    states: list[State],
    modes: list[Mode],
) -> _LinkFeatures:
    signal_names = {s.name for s in signals}
    state_names = {s.name for s in states}
    mode_names = {m.name for m in modes}
    timing_signals = {s.name for s in signals if s.kind == SignalKind.TIMING}

    parsed_signals = [name for name in con.related_signals if name in signal_names]
    parsed_states = [name for name in con.related_states if name in state_names]
    parsed_modes = [name for name in con.applies_in_modes if name in mode_names]

    for name in _match_known_names(con.expression_text, sorted(signal_names)):
        if name not in parsed_signals:
            parsed_signals.append(name)
    for name in _match_known_names(con.expression_text, sorted(state_names)):
        if name not in parsed_states:
            parsed_states.append(name)
    for name in _match_known_names(con.expression_text, sorted(mode_names)):
        if name not in parsed_modes:
            parsed_modes.append(name)

    parameter_name = _parameter_name_from_expr(con.expression_text)
    timing_limit_ms = _parse_timing_limit_ms(con.expression_text)
    is_timing = (
        con.constraint_type == ConstraintType.TIMING
        or timing_limit_ms is not None
        or any(signal in timing_signals or is_timing_name(signal) for signal in parsed_signals)
        or (parameter_name is not None and is_timing_name(parameter_name))
    )

    if timing_limit_ms is None and is_timing and con.numeric_value is not None:
        timing_limit_ms = con.numeric_value

    return _LinkFeatures(
        signals=frozenset(parsed_signals),
        states=frozenset(parsed_states),
        modes=frozenset(parsed_modes),
        classes=frozenset(),
        operator=con.operator,
        numeric_value=con.numeric_value,
        timing_limit_ms=timing_limit_ms,
        is_timing=is_timing,
        is_parameter=parameter_name is not None,
        parameter_name=parameter_name,
    )


def _link_reasons(req: Requirement, reqf: _LinkFeatures, con: Constraint, conf: _LinkFeatures) -> list[str]:
    reasons: list[str] = []
    derived_from_req = con.id.startswith(f"REQC-{req.id}-")
    shared_signals = sorted(reqf.signals & conf.signals)
    shared_states = sorted(reqf.states & conf.states)
    shared_modes = sorted(reqf.modes & conf.modes)
    mode_mismatch = bool(reqf.modes and conf.modes and not shared_modes)

    if derived_from_req:
        reasons.append("derived from requirement text")

    if reqf.is_timing:
        if not conf.is_timing:
            return reasons if derived_from_req else []
        reasons.append("timing-oriented requirement")

        if reqf.modes and not conf.modes and not derived_from_req:
            limit_match = _same_number(reqf.timing_limit_ms, conf.timing_limit_ms)
            if not limit_match:
                return []
        if mode_mismatch:
            return []

        if _same_number(reqf.timing_limit_ms, conf.timing_limit_ms):
            reasons.append(f"matching timing limit {reqf.timing_limit_ms:g} ms")
        if shared_states:
            reasons.append(f"shared state scope {', '.join(shared_states)}")
        if shared_signals:
            reasons.append(f"shared signal scope {', '.join(shared_signals)}")
        if shared_modes:
            reasons.append(f"matching mode scope {', '.join(shared_modes)}")
        if conf.is_parameter and conf.parameter_name:
            reasons.append(f"timing-related parameter {conf.parameter_name}")

        strong_match = (
            derived_from_req
            or _same_number(reqf.timing_limit_ms, conf.timing_limit_ms)
            or bool(shared_states)
            or bool(shared_signals)
            or bool(shared_modes)
        )
        return reasons if strong_match else []

    if reqf.signals and not shared_signals:
        return reasons if derived_from_req else []

    mode_scoped = RequirementLinkClass.MODE_SCOPED in reqf.classes
    signal_bound = RequirementLinkClass.SIGNAL_BOUND in reqf.classes

    if mode_scoped:
        if mode_mismatch:
            return []
        if reqf.modes and not conf.modes and not derived_from_req:
            return []

    if shared_signals:
        reasons.append(f"shared signal {', '.join(shared_signals)}")
    if shared_states:
        reasons.append(f"shared state {', '.join(shared_states)}")
    if shared_modes:
        reasons.append(f"matching mode scope {', '.join(shared_modes)}")

    compat_reason = _bound_compatibility_reason(
        reqf.operator,
        reqf.numeric_value,
        conf.operator,
        conf.numeric_value,
    )
    if compat_reason:
        reasons.append(compat_reason)
    elif signal_bound and reqf.operator is not None and reqf.numeric_value is not None and not derived_from_req:
        return []

    if signal_bound:
        strong_match = derived_from_req or bool(shared_signals)
        return reasons if strong_match and (compat_reason is not None or derived_from_req) else []

    return reasons


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
    mode_name_map: dict[str, str],
) -> list[Constraint]:
    constraints = []
    for i, line in enumerate(lines):
        m = pattern.match(line.strip())
        if not m:
            continue
        cid, text = m.group(1).upper(), m.group(2).strip()

        op, val, unit = _parse_bounds_from_text(text)

        # Extract signal/state/mode references by token matching
        tokens = re.findall(r"\b([A-Z][A-Za-z_0-9]+|[a-z][a-z_0-9]+)\b", text)
        # Heuristic: uppercase tokens tend to be states/modes, lowercase are signals
        related_signals = [
            t for t in tokens
            if t and t[0].islower() and len(t) > 2 and t.lower() not in _GENERIC_LINK_TOKENS
        ]
        upper_tokens = [t for t in tokens if t and t[0].isupper() and len(t) > 2]
        mode_scope = _extract_mode_scope(text, mode_name_map)
        token_modes = [t for t in upper_tokens if t.lower() in mode_name_map]
        related_modes = list(dict.fromkeys(mode_scope + token_modes))
        related_states = [t for t in upper_tokens if t not in related_modes]
        scope_type, applies_globally = _scope_fields(related_modes)

        constraints.append(Constraint(
            id=cid,
            expression_text=text,
            constraint_type=ctype,
            scope_type=scope_type,
            applies_globally=applies_globally,
            applies_in_modes=related_modes,
            related_signals=list(dict.fromkeys(related_signals)),
            related_states=related_states,
            related_modes=related_modes,
            numeric_value=val,
            operator=op,
            source_ref=_source(spec, section, i),
        ))
    return constraints


def _derive_constraints_from_requirements(
    reqs: list[Requirement],
    signals: list[Signal],
    mode_name_map: dict[str, str],
) -> list[Constraint]:
    """
    Derive numeric constraints from requirement text when deterministic structure is present.

    Supported pattern:
      - requirement contains numeric comparison (<=, >=, <, >, ==)
      - requirement mentions a known signal token
      - optional mode qualifiers (in X mode / when mode = X / only in X mode)
    """
    constraints: list[Constraint] = []
    signal_names = [s.name for s in signals]
    signal_name_map = {s.name.lower(): s.name for s in signals}

    for req in reqs:
        op, val, _ = _parse_bounds_from_text(req.text)
        if op is None or val is None:
            continue

        text_lower = req.text.lower()
        related_signals: list[str] = []
        for sname in signal_names:
            signal_snake = sname.lower()
            signal_words = signal_snake.replace("_", " ")
            if re.search(rf"\b{re.escape(signal_snake)}\b", text_lower) or re.search(
                rf"\b{re.escape(signal_words)}\b", text_lower
            ):
                related_signals.append(sname)

        if not related_signals:
            # fallback: detect simple snake_case signal-like references
            for token in re.findall(r"\b([a-z][a-z_0-9]+)\b", text_lower):
                if token in signal_name_map and signal_name_map[token] not in related_signals:
                    related_signals.append(signal_name_map[token])

        if not related_signals:
            continue

        related_modes = _extract_mode_scope(req.text, mode_name_map)
        scope_type, applies_globally = _scope_fields(related_modes)

        for idx, signal_name in enumerate(sorted(related_signals), start=1):
            constraints.append(Constraint(
                id=f"REQC-{req.id}-{idx:02d}",
                expression_text=req.text,
                normalized_form=f"{signal_name} {op} {val}",
                constraint_type=ConstraintType.BOUND,
                scope_type=scope_type,
                applies_globally=applies_globally,
                applies_in_modes=related_modes,
                related_signals=[signal_name],
                related_modes=related_modes,
                numeric_value=val,
                operator=op,
                source_ref=req.source_ref,
            ))

    return constraints


def _link_requirements_to_ir(
    reqs: list[Requirement],
    signals: list[Signal],
    states: list[State],
    modes: list[Mode],
    constraints: list[Constraint],
) -> None:
    """Back-fill requirement linkage fields using selective, typed matching."""
    constraint_features = {
        con.id: _constraint_features(con, signals, states, modes)
        for con in constraints
    }

    for req in reqs:
        req.parsed_signals.clear()
        req.parsed_states.clear()
        req.parsed_modes.clear()
        req.requirement_classes.clear()
        req.parsed_constraints.clear()
        req.linkage_reasons.clear()

        reqf = _requirement_features(req, signals, states, modes)
        req.parsed_signals.extend(sorted(reqf.signals))
        req.parsed_states.extend(sorted(reqf.states))
        req.parsed_modes.extend(sorted(reqf.modes))
        req.requirement_classes.extend(sorted(reqf.classes, key=lambda item: item.value))

        linked: list[tuple[str, list[str]]] = []
        for con in constraints:
            reasons = _link_reasons(req, reqf, con, constraint_features[con.id])
            if reasons:
                linked.append((con.id, reasons))

        for cid, reasons in linked:
            req.parsed_constraints.append(cid)
            req.linkage_reasons[cid] = reasons


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
    mode_name_map = {m.name.lower(): m.name for m in modes}

    safety_constraints = _parse_constraints(
        get("Safety Constraints"), spec, "Safety Constraints", _CON_RE,
        ConstraintType.INVARIANT, mode_name_map,
    )
    forbidden_conditions = _parse_constraints(
        get("Forbidden Conditions"), spec, "Forbidden Conditions", _FC_RE,
        ConstraintType.FORBIDDEN, mode_name_map,
    )
    timing_constraints = _parse_constraints(
        get("Timing Constraints"), spec, "Timing Constraints", _TC_RE,
        ConstraintType.TIMING, mode_name_map,
    )
    requirement_constraints = _derive_constraints_from_requirements(
        requirements,
        signals,
        mode_name_map,
    )

    all_constraints = safety_constraints + forbidden_conditions + timing_constraints + requirement_constraints

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
