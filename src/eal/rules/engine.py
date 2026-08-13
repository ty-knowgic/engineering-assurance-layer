"""
Deterministic rules engine for Engineering Assurance Layer.

Each rule is a plain function: (ir: IRSnapshot) -> list[Finding].
Rules are composable, independently testable, and have no side effects.

Rule catalogue:
  rule_missing_signal_bounds          → MISSING_BOUND
  rule_undefined_signal_in_req        → UNDEFINED_REFERENCE
  rule_undefined_state_in_transition  → TRANSITION_GAP
  rule_forbidden_condition_unguarded  → FORBIDDEN_UNCHECKED
  rule_timing_req_no_parameter        → TIMING_GAP
  rule_missing_failsafe_assumption    → MISSING_ASSUMPTION
  rule_contradictory_bounds           → CONTRADICTORY_CONSTRAINT
  rule_code_bound_mismatch            → CODE_BOUND_MISMATCH
  rule_code_timing_mismatch           → CODE_TIMING_MISMATCH
  rule_code_unmodeled_parameter       → CODE_UNMODELED_PARAMETER
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from eal.code_analysis import (
    classification_is_strong,
    has_min_hint,
    has_upper_hint,
    is_timing_name,
    names_match,
    normalize_symbol_name,
    token_overlap,
)
from eal.findings.schema import Finding, FindingCategory, FindingSeverity
from eal.ir.schema import CodeSymbolClass, ConstraintType, IRSnapshot

# ── Rule metadata and strictness ──────────────────────────────────────────────


class RuleConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RuleStrictnessSensitivity(str, Enum):
    ALWAYS_ON = "always_on"
    HEURISTIC = "heuristic"


class RuleStrictness(str, Enum):
    RELAXED = "relaxed"
    BALANCED = "balanced"
    STRICT = "strict"


@dataclass(frozen=True)
class RuleMetadata:
    rule_id: str
    default_severity: FindingSeverity
    confidence: RuleConfidence
    strictness_sensitivity: RuleStrictnessSensitivity
    description: str


@dataclass(frozen=True)
class RuleSpec:
    metadata: RuleMetadata
    fn: Callable[[IRSnapshot], list[Finding]]


@dataclass
class RuleRunResult:
    findings: list[Finding]
    suppressed_findings: list[Finding]
    applied_rules: list[RuleMetadata]
    suppressed_rules: list[RuleMetadata]


# ── Individual rules ──────────────────────────────────────────────────────────

def rule_missing_signal_bounds(ir: IRSnapshot) -> list[Finding]:
    """Actuator signals without a max bound are missing a safety-relevant limit."""
    findings = []
    for sig in ir.signals:
        from eal.ir.schema import SignalKind
        if sig.kind not in (SignalKind.ACTUATOR, SignalKind.SENSOR):
            continue
        if sig.bounds is None or sig.bounds.max is None:
            ref = f"{sig.source_ref.file}:{sig.source_ref.section}" if sig.source_ref else "spec"
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.MEDIUM,
                category=FindingCategory.MISSING_BOUND,
                title=f"Signal '{sig.name}' has no upper bound defined",
                summary=(
                    f"Signal '{sig.name}' (kind={sig.kind.value}) has no maximum bound. "
                    "Assurance checks require explicit bounds on observable/controllable signals."
                ),
                details=(
                    "Without an upper bound, constraint solvers cannot check whether "
                    "requirements referencing this signal are satisfiable. "
                    "Define bounds in the spec '## Signals' section or in the YAML model."
                ),
                related_ir_nodes=[sig.name],
                source_refs=[ref],
                suggested_fix=(
                    f"Add 'bounds=[<min>, <max>]' to '{sig.name}' in ## Signals, "
                    "or set 'bounds.max' in the model YAML."
                ),
            ))
    return findings


def rule_undefined_signal_in_req(ir: IRSnapshot) -> list[Finding]:
    """Requirements reference signals that are not defined in the model."""
    findings = []
    known_signals = ir.signal_names()
    known_lower = {s.lower() for s in known_signals}

    for req in ir.requirements:
        tokens = re.findall(r"\b([a-z][a-z_0-9]+)\b", req.text)
        for tok in tokens:
            if len(tok) < 3:
                continue
            # If a token looks like a signal name (snake_case, multiple tokens)
            if "_" in tok and tok not in known_lower:
                ref = f"{req.source_ref.file}:{req.source_ref.section}" if req.source_ref else "spec"
                findings.append(Finding(
                    id="TBD",
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.UNDEFINED_REFERENCE,
                    title=f"Requirement '{req.id}' references undefined signal '{tok}'",
                    summary=(
                        f"'{req.id}' mentions '{tok}' which is not defined in ## Signals "
                        "or in the model YAML."
                    ),
                    details=f"Requirement text: \"{req.text}\"",
                    related_ir_nodes=[req.id],
                    source_refs=[ref],
                    suggested_fix=(
                        f"Define signal '{tok}' in ## Signals section, "
                        "or confirm the name matches an existing signal."
                    ),
                ))
    return findings


def rule_undefined_state_in_transition(ir: IRSnapshot) -> list[Finding]:
    """Transitions reference states that are not defined in ## States."""
    findings = []
    known_states = ir.state_names()
    for trans in ir.transitions:
        for sname in (trans.from_state, trans.to_state):
            if sname not in known_states:
                ref = f"{trans.source_ref.file}:{trans.source_ref.section}" if trans.source_ref else "spec"
                findings.append(Finding(
                    id="TBD",
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.TRANSITION_GAP,
                    title=f"Transition references undefined state '{sname}'",
                    summary=(
                        f"Transition '{trans.from_state} -> {trans.to_state}' "
                        f"references state '{sname}' which is not defined in ## States."
                    ),
                    details=(
                        "Undefined state references indicate an incomplete state machine. "
                        "Missing states may hide unreachable or unbounded behaviors."
                    ),
                    related_ir_nodes=[trans.from_state, trans.to_state],
                    source_refs=[ref],
                    suggested_fix=f"Add '{sname}' to ## States section.",
                ))
    return findings


def rule_forbidden_condition_unguarded(ir: IRSnapshot) -> list[Finding]:
    """Forbidden conditions have no corresponding transition guard or assumption."""
    findings = []
    forbidden_constraints = [c for c in ir.constraints if c.constraint_type == ConstraintType.FORBIDDEN]
    guard_texts = [
        (t.guard_condition or "").lower() for t in ir.transitions
    ]
    assumption_texts = [a.text.lower() for a in ir.assumptions]

    for fc in forbidden_constraints:
        fc_lower = fc.expression_text.lower()
        # Check if any transition guard or assumption addresses this condition
        signals_in_fc = set(fc.related_signals)
        guarded = any(
            any(sig.lower() in g for sig in signals_in_fc)
            for g in guard_texts
        )
        assumed = any(
            any(sig.lower() in a for sig in signals_in_fc)
            for a in assumption_texts
        )
        if not guarded and not assumed:
            ref = f"{fc.source_ref.file}:{fc.source_ref.section}" if fc.source_ref else "spec"
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.FORBIDDEN_UNCHECKED,
                title=f"Forbidden condition '{fc.id}' has no guard or assumption",
                summary=(
                    f"Forbidden condition '{fc.id}' ({fc.expression_text}) "
                    "is declared but no transition guard or assumption enforces it."
                ),
                details=(
                    "Forbidden conditions require either: "
                    "(1) a transition guard that prevents entry, "
                    "(2) an assumption that makes the condition structurally impossible, or "
                    "(3) a documented safety mechanism."
                ),
                related_ir_nodes=[fc.id] + fc.related_signals,
                source_refs=[ref],
                suggested_fix=(
                    f"Add a transition guard referencing the signals in '{fc.id}', "
                    "or add an assumption (ASM-NNN) stating the enforcement mechanism."
                ),
            ))
    return findings


def rule_timing_req_no_parameter(ir: IRSnapshot) -> list[Finding]:
    """Timing requirements exist but no timing parameter is defined in the model."""
    findings = []
    timing_constraints = [c for c in ir.constraints if c.constraint_type == ConstraintType.TIMING]
    timing_reqs = [
        r for r in ir.requirements
        if re.search(r"\b(within|ms|milliseconds?|seconds?|latency|response time)\b", r.text, re.I)
    ]

    if not timing_constraints and not timing_reqs:
        return []

    # Check if any PARAM constraint carries a timing value
    param_constraints = [c for c in ir.constraints if c.id.startswith("PARAM-")]
    timing_param_names = {
        c.id for c in param_constraints
        if re.search(r"(ms|time|latency|response|delay)", c.expression_text, re.I)
    }
    # An importer that types a constraint as TIMING and gives it a value has
    # already declared a timing parameter; requiring a `PARAM-` id prefix would
    # make that invisible purely because of a naming convention.
    timing_param_names |= {
        c.id for c in ir.constraints
        if c.constraint_type == ConstraintType.TIMING and c.numeric_value is not None
    }

    timing_asm_count = sum(
        1 for a in ir.assumptions
        if re.search(r"\b(ms|latency|response|timing|time)\b", a.text, re.I)
    )

    needs_finding = bool(timing_constraints or timing_reqs) and not timing_param_names and not timing_asm_count

    if needs_finding:
        refs = [
            f"{c.source_ref.file}:{c.source_ref.section}"
            for c in (timing_constraints or [])
            if c.source_ref
        ]
        for req in timing_reqs:
            if req.source_ref:
                refs.append(f"{req.source_ref.file}:{req.source_ref.section}")

        findings.append(Finding(
            id="TBD",
            severity=FindingSeverity.MEDIUM,
            category=FindingCategory.TIMING_GAP,
            title="Timing requirement present but no timing parameter defined in model",
            summary=(
                f"Found {len(timing_constraints)} timing constraint(s) and "
                f"{len(timing_reqs)} timing requirement(s), but no timing parameter "
                "(e.g., response_ms, latency_ms) is defined in the model YAML."
            ),
            details=(
                "Timing requirements cannot be verified by the constraint solver "
                "without a corresponding numeric parameter. "
                "The requirement may also be unverifiable without test infrastructure."
            ),
            related_ir_nodes=[c.id for c in timing_constraints] + [r.id for r in timing_reqs],
            source_refs=list(dict.fromkeys(refs)),
            suggested_fix=(
                "Add a timing parameter to the model YAML 'parameters:' section, "
                "e.g., 'estop_response_ms: 100'. "
                "Or add an assumption (ASM-NNN) stating the timing guarantee source."
            ),
        ))
    return findings


def rule_missing_failsafe_assumption(ir: IRSnapshot) -> list[Finding]:
    """
    Safety constraints involving human detection or emergency stop
    lack a corresponding assumption about sensor reliability or response time.
    """
    findings = []
    safety_keywords = {"human_detected", "e_stop", "estop", "emergency", "fault"}
    assumption_texts_lower = [a.text.lower() for a in ir.assumptions]

    relevant_constraints = [
        c for c in ir.constraints
        if any(kw in c.expression_text.lower() for kw in safety_keywords)
    ]
    relevant_reqs = [
        r for r in ir.requirements
        if any(kw in r.text.lower() for kw in safety_keywords)
    ]

    if not relevant_constraints and not relevant_reqs:
        return []

    # Check whether any assumption covers sensor reliability or response guarantee
    has_safety_assumption = any(
        re.search(r"(sensor|detector|latency|response|guaranteed|reliable|certified)", a, re.I)
        for a in assumption_texts_lower
    )

    if not has_safety_assumption:
        all_items = relevant_constraints + relevant_reqs  # type: ignore[operator]
        refs = [
            f"{item.source_ref.file}:{item.source_ref.section}"
            for item in all_items
            if item.source_ref
        ]
        signal_names = list({
            s for c in relevant_constraints for s in c.related_signals
        } | {
            s for r in relevant_reqs for s in r.parsed_signals
        })
        findings.append(Finding(
            id="TBD",
            severity=FindingSeverity.HIGH,
            category=FindingCategory.MISSING_ASSUMPTION,
            title="Safety-critical constraint lacks supporting sensor reliability assumption",
            summary=(
                "Constraints and/or requirements reference safety-critical signals "
                f"({', '.join(signal_names) or 'e_stop / human_detected'}) "
                "but no assumption declares sensor latency, reliability, or hardware guarantee."
            ),
            details=(
                "Safety constraints that depend on sensor inputs require explicit assumptions "
                "about sensor response time, false-negative rate, or certification level. "
                "Without these, the constraint cannot be validated as safe."
            ),
            related_ir_nodes=signal_names,
            source_refs=list(dict.fromkeys(refs)),
            suggested_fix=(
                "Add an assumption such as: "
                "'ASM-XXX: The human detection sensor has a maximum latency of N ms "
                "and a false-negative rate within certified limits.'"
            ),
        ))
    return findings


def rule_contradictory_bounds(ir: IRSnapshot) -> list[Finding]:
    """
    Detect signals where spec bounds and requirement bounds are contradictory
    without invoking Z3 (pure arithmetic check).
    """
    findings = []

    for sig in ir.signals:
        if sig.bounds is None:
            continue
        sig_min = sig.bounds.min
        sig_max = sig.bounds.max

        # Find all numeric constraints that reference this signal
        relevant = [
            c for c in ir.constraints
            if sig.name in c.related_signals and c.numeric_value is not None and c.operator
            and c.applies_globally
        ]

        for con in relevant:
            op, val = con.operator, con.numeric_value
            assert val is not None  # guarded above

            contradiction = False
            detail = ""

            # Constraint says <= val, but signal's minimum is already > val
            if op == "<=" and sig_min is not None and sig_min > val:
                contradiction = True
                detail = (
                    f"Signal '{sig.name}' has min bound {sig_min} "
                    f"but constraint '{con.id}' requires {op} {val}. "
                    "The minimum bound already violates the constraint — "
                    "the safe region is unreachable."
                )
            # Constraint says >= val, but signal's maximum is already < val
            elif op == ">=" and sig_max is not None and sig_max < val:
                contradiction = True
                detail = (
                    f"Signal '{sig.name}' has max bound {sig_max} "
                    f"but constraint '{con.id}' requires {op} {val}. "
                    "The maximum bound already violates the constraint — "
                    "the safe region is unreachable."
                )

            if contradiction:
                ref = f"{con.source_ref.file}:{con.source_ref.section}" if con.source_ref else "spec"
                sig_ref = f"{sig.source_ref.file}:{sig.source_ref.section}" if sig.source_ref else "spec"
                findings.append(Finding(
                    id="TBD",
                    severity=FindingSeverity.CRITICAL,
                    category=FindingCategory.CONTRADICTORY_CONSTRAINT,
                    title=f"Contradictory bounds for signal '{sig.name}'",
                    summary=detail,
                    details=(
                        "This contradiction means the constraint can never be satisfied "
                        "given the signal's declared operating range. "
                        "Either the bound or the constraint must be corrected."
                    ),
                    related_ir_nodes=[sig.name, con.id],
                    source_refs=list(dict.fromkeys([ref, sig_ref])),
                    suggested_fix=(
                        f"Reconcile the bounds for '{sig.name}' with constraint '{con.id}'. "
                        f"Either lower the min bound below {val} or relax the constraint."
                    ),
                    counterexample={
                        "signal": sig.name,
                        "signal_min": sig_min,
                        "signal_max": sig_max,
                        "constraint_id": con.id,
                        "constraint_op": op,
                        "constraint_val": val,
                    },
                ))
    return findings


@dataclass
class _BoundCandidate:
    name: str
    normalized_name: str
    max_value: float
    ref: str
    node: str
    reason: str


@dataclass
class _TimingCandidate:
    name: str
    normalized_name: str
    max_ms: float
    ref: str
    source_text: str
    reason: str


def _line_ref(file: str, line: int) -> str:
    return f"{file}:{line}"


def _source_ref(file: Optional[str], section: Optional[str], line: Optional[int]) -> str:
    if not file:
        return "spec"
    if line is not None:
        return f"{file}:{line}"
    if section:
        return f"{file}:{section}"
    return file


def _parameter_name_from_expr(expr: str) -> Optional[str]:
    m = re.match(r"\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=", expr)
    return m.group(1) if m else None


def _timing_within_ms(text: str) -> Optional[float]:
    m = re.search(r"\bwithin\s+(\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds)\b", text, re.I)
    if not m:
        return None
    return float(m.group(1))


def _timing_name_candidates_from_text(text: str) -> list[str]:
    names: list[str] = []
    generic_timing_words = {"ms", "time", "timing", "latency", "response", "timeout", "delay", "deadline"}
    for token in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text):
        if is_timing_name(token):
            normalized = normalize_symbol_name(token)
            if normalized in generic_timing_words:
                continue
            names.append(token)
    return list(dict.fromkeys(names))


def _record_match_metadata(item: object, candidate: str, confidence: float, reason: str) -> None:
    candidates = getattr(item, "match_candidates", None)
    if isinstance(candidates, list) and candidate not in candidates:
        candidates.append(candidate)

    prev_conf = getattr(item, "match_confidence", None)
    best_conf = confidence if prev_conf is None else max(float(prev_conf), confidence)
    setattr(item, "match_confidence", best_conf)

    prev_reason = getattr(item, "match_reason", None)
    if prev_reason is None or confidence >= (float(prev_conf) if prev_conf is not None else 0.0):
        setattr(item, "match_reason", reason)


def _code_detail(
    snippet: Optional[str],
    classification: CodeSymbolClass,
    class_conf: float,
    class_reason: Optional[str],
    match_reason: str,
) -> str:
    return (
        f"Code snippet: {snippet or '<unknown>'}. "
        f"Classification: {classification.value} (confidence={class_conf:.2f}; {class_reason or 'n/a'}). "
        f"Match rationale: {match_reason}."
    )


def _best_upper_bounds(ir: IRSnapshot) -> dict[str, _BoundCandidate]:
    best: dict[str, _BoundCandidate] = {}

    for sig in ir.signals:
        if sig.bounds is None or sig.bounds.max is None:
            continue
        key = normalize_symbol_name(sig.name)
        if not key:
            continue
        candidate = _BoundCandidate(
            name=sig.name,
            normalized_name=key,
            max_value=float(sig.bounds.max),
            ref=_source_ref(
                sig.source_ref.file if sig.source_ref else None,
                sig.source_ref.section if sig.source_ref else None,
                sig.source_ref.line if sig.source_ref else None,
            ),
            node=sig.name,
            reason="signal bounds declaration",
        )
        existing = best.get(key)
        if existing is None or candidate.max_value < existing.max_value:
            best[key] = candidate

    for con in ir.constraints:
        if con.numeric_value is None:
            continue

        if con.operator in {"<", "<="}:
            for sig_name in con.related_signals:
                key = normalize_symbol_name(sig_name)
                if not key:
                    continue
                candidate = _BoundCandidate(
                    name=sig_name,
                    normalized_name=key,
                    max_value=float(con.numeric_value),
                    ref=_source_ref(
                        con.source_ref.file if con.source_ref else None,
                        con.source_ref.section if con.source_ref else None,
                        con.source_ref.line if con.source_ref else None,
                    ),
                    node=con.id,
                    reason=f"constraint {con.id} upper bound",
                )
                existing = best.get(key)
                if existing is None or candidate.max_value < existing.max_value:
                    best[key] = candidate

        if con.id.startswith("PARAM-"):
            pname = _parameter_name_from_expr(con.expression_text or "")
            if not pname or not has_upper_hint(pname):
                continue
            key = normalize_symbol_name(pname)
            if not key:
                continue
            candidate = _BoundCandidate(
                name=pname,
                normalized_name=key,
                max_value=float(con.numeric_value),
                ref=_source_ref(
                    con.source_ref.file if con.source_ref else None,
                    con.source_ref.section if con.source_ref else None,
                    con.source_ref.line if con.source_ref else None,
                ),
                node=con.id,
                reason=f"model parameter {con.id}",
            )
            existing = best.get(key)
            if existing is None or candidate.max_value < existing.max_value:
                best[key] = candidate

    return best


def _timing_limits(ir: IRSnapshot) -> list[_TimingCandidate]:
    limits: list[_TimingCandidate] = []

    for con in ir.constraints:
        if con.numeric_value is not None and con.id.startswith("PARAM-"):
            pname = _parameter_name_from_expr(con.expression_text or "")
            if pname and is_timing_name(pname):
                normalized = normalize_symbol_name(pname)
                if not normalized:
                    continue
                limits.append(_TimingCandidate(
                    name=pname,
                    normalized_name=normalized,
                    max_ms=float(con.numeric_value),
                    ref=_source_ref(
                        con.source_ref.file if con.source_ref else None,
                        con.source_ref.section if con.source_ref else None,
                        con.source_ref.line if con.source_ref else None,
                    ),
                    source_text=con.expression_text,
                    reason=f"model timing parameter {con.id}",
                ))

        if con.constraint_type == ConstraintType.TIMING:
            limit = _timing_within_ms(con.expression_text)
            if limit is None:
                continue
            names = _timing_name_candidates_from_text(con.expression_text) or ["timing"]
            for name in names:
                normalized = normalize_symbol_name(name)
                if not normalized:
                    continue
                limits.append(_TimingCandidate(
                    name=name,
                    normalized_name=normalized,
                    max_ms=limit,
                    ref=_source_ref(
                        con.source_ref.file if con.source_ref else None,
                        con.source_ref.section if con.source_ref else None,
                        con.source_ref.line if con.source_ref else None,
                    ),
                    source_text=con.expression_text,
                    reason=f"timing constraint {con.id}",
                ))

    for req in ir.requirements:
        limit = _timing_within_ms(req.text)
        if limit is None:
            continue
        names = _timing_name_candidates_from_text(req.text) or ["timing"]
        for name in names:
            normalized = normalize_symbol_name(name)
            if not normalized:
                continue
            limits.append(_TimingCandidate(
                name=name,
                normalized_name=normalized,
                max_ms=limit,
                ref=_source_ref(
                    req.source_ref.file if req.source_ref else None,
                    req.source_ref.section if req.source_ref else None,
                    req.source_ref.line if req.source_ref else None,
                ),
                source_text=req.text,
                reason=f"timing requirement {req.id}",
            ))

    # Keep strictest limit per normalized name.
    by_name: dict[str, _TimingCandidate] = {}
    for entry in limits:
        key = entry.normalized_name
        current = by_name.get(key)
        if current is None or entry.max_ms < current.max_ms:
            by_name[key] = entry

    # Global fallback: strictest declared timing target.
    if by_name:
        global_strict = min(by_name.values(), key=lambda item: item.max_ms)
        if "timing" not in by_name:
            by_name["timing"] = _TimingCandidate(
                name="timing",
                normalized_name="timing",
                max_ms=global_strict.max_ms,
                ref=global_strict.ref,
                source_text=global_strict.source_text,
                reason="strictest declared timing limit (global fallback)",
            )

    return sorted(by_name.values(), key=lambda item: (item.name, item.max_ms, item.ref))


def rule_code_bound_mismatch(ir: IRSnapshot) -> list[Finding]:
    """Code constants/thresholds declare looser upper bounds than spec/model constraints."""
    findings: list[Finding] = []
    bounds = _best_upper_bounds(ir)
    if not bounds:
        return findings

    emitted: set[tuple[str, str]] = set()
    bound_values = list(bounds.values())

    for const in ir.code_constants:
        if has_min_hint(const.symbol):
            continue
        if const.classification != CodeSymbolClass.SIGNAL_BOUND_CANDIDATE:
            continue
        if const.classification_confidence < 0.70:
            continue
        if not has_upper_hint(const.symbol) and const.normalized_name not in bounds:
            continue
        for b in bound_values:
            if not names_match(const.symbol, b.name):
                continue
            if const.value <= b.max_value:
                continue
            key = (const.evidence_id, b.ref)
            if key in emitted:
                continue
            emitted.add(key)
            match_reason = (
                f"normalized symbol '{const.normalized_name}' matches bound target "
                f"'{b.normalized_name}' from {b.reason}"
            )
            _record_match_metadata(const, b.name, 0.95, match_reason)
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.CODE_BOUND_MISMATCH,
                title=f"Code constant '{const.symbol}' exceeds declared bound for '{b.name}'",
                summary=(
                    f"Spec/model upper bound for '{b.name}' is <= {b.max_value}, "
                    f"but code constant '{const.symbol}' is {const.value}."
                ),
                details=_code_detail(
                    const.snippet,
                    const.classification,
                    const.classification_confidence,
                    const.classification_reason,
                    match_reason,
                ),
                related_ir_nodes=[b.node, const.symbol],
                source_refs=[b.ref, _line_ref(const.file, const.line)],
                evidence_refs=[const.evidence_id],
                suggested_fix=(
                    f"Align '{const.symbol}' with the declared upper bound <= {b.max_value}, "
                    "or update spec/model if the implemented value is intended."
                ),
            ))

    for cmp_item in ir.code_comparisons:
        if has_min_hint(cmp_item.symbol):
            continue
        if cmp_item.classification != CodeSymbolClass.SIGNAL_BOUND_CANDIDATE:
            continue
        if cmp_item.classification_confidence < 0.70:
            continue
        if cmp_item.operator not in {"<", "<=", ">", ">="}:
            continue

        for b in bound_values:
            if not names_match(cmp_item.symbol, b.name):
                continue

            # '<=' and '<' are direct upper-bound checks.
            # '>' / '>=' in guards are treated as threshold limits for violation detection.
            if cmp_item.operator in {"<", "<=", ">", ">="} and cmp_item.value > b.max_value:
                key = (cmp_item.evidence_id, b.ref)
                if key in emitted:
                    continue
                emitted.add(key)
                match_reason = (
                    f"normalized symbol '{cmp_item.normalized_name}' matches bound target "
                    f"'{b.normalized_name}' from {b.reason}"
                )
                _record_match_metadata(cmp_item, b.name, 0.92, match_reason)
                findings.append(Finding(
                    id="TBD",
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.CODE_BOUND_MISMATCH,
                    title=f"Code comparison for '{cmp_item.symbol}' is looser than declared bound",
                    summary=(
                        f"Spec/model upper bound for '{b.name}' is <= {b.max_value}, "
                        f"but code uses threshold '{cmp_item.symbol} {cmp_item.operator} {cmp_item.value}'."
                    ),
                    details=_code_detail(
                        cmp_item.snippet,
                        cmp_item.classification,
                        cmp_item.classification_confidence,
                        cmp_item.classification_reason,
                        match_reason,
                    ),
                    related_ir_nodes=[b.node, cmp_item.symbol],
                    source_refs=[b.ref, _line_ref(cmp_item.file, cmp_item.line)],
                    evidence_refs=[cmp_item.evidence_id],
                    suggested_fix=(
                        f"Adjust the code threshold to <= {b.max_value} or reconcile the spec/model limit."
                    ),
                ))
    return findings


def rule_code_timing_mismatch(ir: IRSnapshot) -> list[Finding]:
    """Code timing constants/thresholds exceed required timing limits."""
    findings: list[Finding] = []
    timing_limits = _timing_limits(ir)
    if not timing_limits:
        return findings

    emitted: set[tuple[str, str]] = set()

    def _relevant_limits(symbol: str) -> tuple[list[_TimingCandidate], str]:
        normalized = normalize_symbol_name(symbol)
        if not normalized:
            return ([], "no normalized symbol")

        named: list[_TimingCandidate] = []
        for tl in timing_limits:
            if tl.normalized_name == "timing":
                continue
            if names_match(symbol, tl.name):
                named.append(tl)
        if named:
            return (
                named,
                f"matched explicit timing declaration(s): {', '.join(sorted({n.name for n in named}))}",
            )
        global_limit = next((tl for tl in timing_limits if tl.name == "timing"), None)
        if global_limit is not None:
            return ([global_limit], "used global timing limit fallback")
        return ([], "no timing limit found")

    for const in ir.code_constants:
        if const.classification != CodeSymbolClass.TIMING_PARAMETER_CANDIDATE:
            continue
        if const.classification_confidence < 0.78:
            continue
        limits, rationale = _relevant_limits(const.symbol)
        for limit in limits:
            if limit is None or const.value <= limit.max_ms:
                continue
            key = (const.evidence_id, limit.ref)
            if key in emitted:
                continue
            emitted.add(key)
            match_reason = f"{rationale}; evidence from {limit.reason}"
            _record_match_metadata(const, limit.name, 0.95, match_reason)
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.CODE_TIMING_MISMATCH,
                title=f"Code timing constant '{const.symbol}' exceeds declared response limit",
                summary=(
                    f"Declared timing limit is <= {limit.max_ms} ms, "
                    f"but code constant '{const.symbol}' is {const.value} ms."
                ),
                details=_code_detail(
                    const.snippet,
                    const.classification,
                    const.classification_confidence,
                    const.classification_reason,
                    match_reason,
                ),
                related_ir_nodes=[const.symbol],
                source_refs=[limit.ref, _line_ref(const.file, const.line)],
                evidence_refs=[const.evidence_id],
                suggested_fix=(
                    f"Reduce '{const.symbol}' to <= {limit.max_ms} ms or update the timing requirement/model."
                ),
            ))

    for cmp_item in ir.code_comparisons:
        if cmp_item.classification != CodeSymbolClass.TIMING_PARAMETER_CANDIDATE:
            continue
        if cmp_item.classification_confidence < 0.78:
            continue
        limits, rationale = _relevant_limits(cmp_item.symbol)
        for limit in limits:
            if limit is None or cmp_item.value <= limit.max_ms:
                continue
            key = (cmp_item.evidence_id, limit.ref)
            if key in emitted:
                continue
            emitted.add(key)
            match_reason = f"{rationale}; evidence from {limit.reason}"
            _record_match_metadata(cmp_item, limit.name, 0.93, match_reason)
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.HIGH,
                category=FindingCategory.CODE_TIMING_MISMATCH,
                title=f"Code timing threshold for '{cmp_item.symbol}' exceeds declared response limit",
                summary=(
                    f"Declared timing limit is <= {limit.max_ms} ms, "
                    f"but code uses '{cmp_item.symbol} {cmp_item.operator} {cmp_item.value}'."
                ),
                details=_code_detail(
                    cmp_item.snippet,
                    cmp_item.classification,
                    cmp_item.classification_confidence,
                    cmp_item.classification_reason,
                    match_reason,
                ),
                related_ir_nodes=[cmp_item.symbol],
                source_refs=[limit.ref, _line_ref(cmp_item.file, cmp_item.line)],
                evidence_refs=[cmp_item.evidence_id],
                suggested_fix=(
                    f"Adjust timing threshold to <= {limit.max_ms} ms or reconcile timing declarations."
                ),
            ))

    return findings


def rule_code_unmodeled_parameter(ir: IRSnapshot) -> list[Finding]:
    """
    Detect engineering-style code constants that appear related to known system names
    but are not declared in spec/model signals or parameters.
    """
    findings: list[Finding] = []
    bound_targets = _best_upper_bounds(ir)
    timing_targets = _timing_limits(ir)

    known_bound_names = list(bound_targets.values())
    known_bound_norms = {b.normalized_name for b in known_bound_names}

    timing_named = [t for t in timing_targets if t.normalized_name != "timing"]
    known_timing_norms = {t.normalized_name for t in timing_named}
    has_timing_context = any(c.constraint_type == ConstraintType.TIMING for c in ir.constraints) or any(
        _timing_within_ms(r.text) is not None for r in ir.requirements
    )

    if not known_bound_norms and not has_timing_context and not known_timing_norms:
        return findings

    emitted_symbols: set[str] = set()
    for const in ir.code_constants:
        if const.evidence_id in emitted_symbols:
            continue
        if not classification_is_strong(const.classification, const.classification_confidence):
            continue
        if const.classification == CodeSymbolClass.GENERIC_NUMERIC_CONSTANT:
            continue

        if const.classification == CodeSymbolClass.TIMING_PARAMETER_CANDIDATE:
            if const.normalized_name in known_timing_norms:
                continue
            if not has_timing_context:
                continue
            timing_ref = timing_targets[0].ref if timing_targets else "spec"
            match_reason = (
                "classified as timing parameter candidate but no matching timing parameter "
                "declaration was found in model/spec timing parameter set"
            )
            _record_match_metadata(const, "timing", 0.90, match_reason)
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.MEDIUM,
                category=FindingCategory.CODE_UNMODELED_PARAMETER,
                title=f"Code timing parameter '{const.symbol}' is not modeled",
                summary=(
                    f"'{const.symbol}' is a timing parameter candidate, but no corresponding "
                    "timing parameter declaration exists in model/spec."
                ),
                details=_code_detail(
                    const.snippet,
                    const.classification,
                    const.classification_confidence,
                    const.classification_reason,
                    match_reason,
                ),
                related_ir_nodes=[const.symbol],
                source_refs=[timing_ref, _line_ref(const.file, const.line)],
                evidence_refs=[const.evidence_id],
                suggested_fix=(
                    f"Add a timing parameter declaration for '{const.symbol}' in model YAML "
                    "or rename the constant if it is not assurance-relevant."
                ),
            ))
            emitted_symbols.add(const.evidence_id)
            continue

        if const.classification == CodeSymbolClass.SIGNAL_BOUND_CANDIDATE:
            if const.normalized_name in known_bound_norms:
                continue
            if not has_upper_hint(const.symbol):
                continue

            best: Optional[_BoundCandidate] = None
            best_overlap = 0
            for target in known_bound_names:
                overlap = len(token_overlap(const.symbol, target.name))
                if overlap > best_overlap:
                    best = target
                    best_overlap = overlap

            # Require at least two shared tokens to avoid weak lexical matches.
            if best is None or best_overlap < 2:
                continue

            severity = FindingSeverity.MEDIUM if best_overlap >= 2 else FindingSeverity.LOW
            match_reason = (
                f"bound candidate has no exact declaration; nearest modeled bound target "
                f"is '{best.name}' with token overlap={best_overlap}"
            )
            _record_match_metadata(const, best.name, 0.86, match_reason)
            findings.append(Finding(
                id="TBD",
                severity=severity,
                category=FindingCategory.CODE_UNMODELED_PARAMETER,
                title=f"Code bound parameter '{const.symbol}' is not modeled",
                summary=(
                    f"'{const.symbol}' is classified as a bound candidate but has no direct "
                    f"spec/model declaration (closest modeled target: '{best.name}')."
                ),
                details=_code_detail(
                    const.snippet,
                    const.classification,
                    const.classification_confidence,
                    const.classification_reason,
                    match_reason,
                ),
                related_ir_nodes=[best.node, const.symbol],
                source_refs=[best.ref, _line_ref(const.file, const.line)],
                evidence_refs=[const.evidence_id],
                suggested_fix=(
                    f"Declare '{const.symbol}' (or mapped equivalent) in spec/model bounds, "
                    "or rename it to avoid assurance ambiguity."
                ),
            ))
            emitted_symbols.add(const.evidence_id)

    return findings


# ── Rule registry and runner ──────────────────────────────────────────────────

_RULES: list[RuleSpec] = [
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.MISSING_BOUND.value,
            default_severity=FindingSeverity.MEDIUM,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Actuator/sensor signal lacks an explicit upper bound.",
        ),
        fn=rule_missing_signal_bounds,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.UNDEFINED_REFERENCE.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.MEDIUM,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Requirement references an undefined signal token.",
        ),
        fn=rule_undefined_signal_in_req,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.TRANSITION_GAP.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Transition references a state not declared in the model/spec.",
        ),
        fn=rule_undefined_state_in_transition,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.FORBIDDEN_UNCHECKED.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Forbidden condition has no explicit guard/assumption enforcement.",
        ),
        fn=rule_forbidden_condition_unguarded,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.TIMING_GAP.value,
            default_severity=FindingSeverity.MEDIUM,
            confidence=RuleConfidence.MEDIUM,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Timing requirement exists without a matching timing parameter.",
        ),
        fn=rule_timing_req_no_parameter,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.MISSING_ASSUMPTION.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.MEDIUM,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Safety-critical behavior lacks explicit reliability assumptions.",
        ),
        fn=rule_missing_failsafe_assumption,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.CONTRADICTORY_CONSTRAINT.value,
            default_severity=FindingSeverity.CRITICAL,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Declared numeric bounds and constraints are arithmetically contradictory.",
        ),
        fn=rule_contradictory_bounds,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.CODE_BOUND_MISMATCH.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Code-side bound constant/comparison is looser than declared limit.",
        ),
        fn=rule_code_bound_mismatch,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.CODE_TIMING_MISMATCH.value,
            default_severity=FindingSeverity.HIGH,
            confidence=RuleConfidence.HIGH,
            strictness_sensitivity=RuleStrictnessSensitivity.ALWAYS_ON,
            description="Code-side timing constant/comparison exceeds declared timing limit.",
        ),
        fn=rule_code_timing_mismatch,
    ),
    RuleSpec(
        metadata=RuleMetadata(
            rule_id=FindingCategory.CODE_UNMODELED_PARAMETER.value,
            default_severity=FindingSeverity.MEDIUM,
            confidence=RuleConfidence.LOW,
            strictness_sensitivity=RuleStrictnessSensitivity.HEURISTIC,
            description="Code symbol appears assurance-relevant but has no direct model/spec declaration.",
        ),
        fn=rule_code_unmodeled_parameter,
    ),
]


def _should_suppress_rule(metadata: RuleMetadata, strictness: RuleStrictness) -> bool:
    """Return True when this rule should be suppressed for the selected strictness."""
    return (
        strictness == RuleStrictness.RELAXED
        and metadata.strictness_sensitivity == RuleStrictnessSensitivity.HEURISTIC
    )


def available_rule_metadata() -> list[RuleMetadata]:
    """Return deterministic rule catalogue metadata."""
    return [spec.metadata for spec in _RULES]


def run_rules_detailed(
    ir: IRSnapshot,
    strictness: RuleStrictness | str = RuleStrictness.BALANCED,
) -> RuleRunResult:
    """Run deterministic rules with strictness-aware suppression metadata."""
    level = strictness if isinstance(strictness, RuleStrictness) else RuleStrictness(str(strictness).lower())
    findings: list[Finding] = []
    suppressed_findings: list[Finding] = []
    applied_rules: list[RuleMetadata] = []
    suppressed_rules: list[RuleMetadata] = []

    for spec in _RULES:
        try:
            produced = spec.fn(ir)
        except Exception as exc:
            # Rules should never crash the pipeline — capture as a low finding.
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.LOW,
                category=FindingCategory.MISSING_ASSUMPTION,
                title=f"Rule '{spec.fn.__name__}' raised an internal error",
                summary=str(exc),
                suggested_fix="Report this as a bug in the EAL rules engine.",
            ))
            applied_rules.append(spec.metadata)
            continue

        if _should_suppress_rule(spec.metadata, level):
            if produced:
                suppressed_rules.append(spec.metadata)
                suppressed_findings.extend(produced)
            continue

        applied_rules.append(spec.metadata)
        findings.extend(produced)

    return RuleRunResult(
        findings=findings,
        suppressed_findings=suppressed_findings,
        applied_rules=applied_rules,
        suppressed_rules=suppressed_rules,
    )


def run_rules(
    ir: IRSnapshot,
    strictness: RuleStrictness | str = RuleStrictness.BALANCED,
) -> list[Finding]:
    """Run deterministic rules against the IR. Returns unnumbered findings."""
    return run_rules_detailed(ir, strictness=strictness).findings
