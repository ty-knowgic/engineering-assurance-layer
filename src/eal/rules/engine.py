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
"""

from __future__ import annotations

import re

from eal.findings.schema import Finding, FindingCategory, FindingSeverity
from eal.ir.schema import ConstraintType, IRSnapshot

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


# ── Rule registry and runner ──────────────────────────────────────────────────

_RULES = [
    rule_missing_signal_bounds,
    rule_undefined_signal_in_req,
    rule_undefined_state_in_transition,
    rule_forbidden_condition_unguarded,
    rule_timing_req_no_parameter,
    rule_missing_failsafe_assumption,
    rule_contradictory_bounds,
]


def run_rules(ir: IRSnapshot) -> list[Finding]:
    """Run all deterministic rules against the IR. Returns unnumbered findings."""
    results: list[Finding] = []
    for rule in _RULES:
        try:
            results.extend(rule(ir))
        except Exception as exc:
            # Rules should never crash the pipeline — log and continue
            results.append(Finding(
                id="TBD",
                severity=FindingSeverity.LOW,
                category=FindingCategory.MISSING_ASSUMPTION,
                title=f"Rule '{rule.__name__}' raised an internal error",
                summary=str(exc),
                suggested_fix="Report this as a bug in the EAL rules engine.",
            ))
    return results
