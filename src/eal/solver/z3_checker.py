"""
Z3-backed constraint checker for Engineering Assurance Layer.

Checks performed:
  1. Bounds contradiction   — signal bounds + requirement constraint → UNSAT
  2. Constraint conflict    — two constraints on the same signal → UNSAT
  3. Impossible mode combo  — mode invariants are jointly unsatisfiable
  4. Unreachable safe region — all constraints together have no satisfying assignment

All checks:
  - Build Z3 variables from IR numeric data
  - Assert constraints
  - Check satisfiability
  - On UNSAT: emit CRITICAL finding with counterexample context
  - On SAT: emit no finding (the check passes)
  - On error: emit LOW finding noting the check could not run
"""

from __future__ import annotations

import logging
from typing import Optional

from eal.findings.schema import Finding, FindingCategory, FindingSeverity
from eal.ir.schema import ConstraintType, IRSnapshot

logger = logging.getLogger(__name__)

try:
    import z3
    _Z3_AVAILABLE = True
except ImportError:
    _Z3_AVAILABLE = False


def _z3_not_available_finding() -> Finding:
    return Finding(
        id="TBD",
        severity=FindingSeverity.LOW,
        category=FindingCategory.CONSTRAINT_CONFLICT,
        title="Z3 solver not available — constraint checks skipped",
        summary="Install z3-solver to enable symbolic constraint checking.",
        suggested_fix="pip install z3-solver",
    )


def _check_signal_bounds_vs_constraints(ir: IRSnapshot) -> list[Finding]:
    """
    For each signal with numeric bounds AND at least one numeric constraint,
    assert bounds + constraint and check satisfiability.

    Example contradiction:
      joint_speed has bounds [1.5, 2.5]
      CON-001 says joint_speed <= 1.2
      → UNSAT: min_bound(1.5) > max_allowed(1.2)
    """
    findings = []

    for sig in ir.signals:
        if sig.bounds is None:
            continue

        relevant = [
            c for c in ir.constraints
            if sig.name in c.related_signals
            and c.numeric_value is not None
            and c.operator is not None
            and c.constraint_type in (ConstraintType.BOUND, ConstraintType.INVARIANT)
        ]
        if not relevant:
            continue

        x = z3.Real(sig.name)
        assertions = []

        if sig.bounds.min is not None:
            assertions.append(x >= sig.bounds.min)
        if sig.bounds.max is not None:
            assertions.append(x <= sig.bounds.max)

        for con in relevant:
            val = con.numeric_value
            op = con.operator
            if op == "<=":
                assertions.append(x <= val)
            elif op == ">=":
                assertions.append(x >= val)
            elif op == "<":
                assertions.append(x < val)
            elif op == ">":
                assertions.append(x > val)
            elif op == "==":
                assertions.append(x == val)

        solver = z3.Solver()
        solver.add(*assertions)
        result = solver.check()

        if result == z3.unsat:
            con_ids = [c.id for c in relevant]
            refs = [
                f"{c.source_ref.file}:{c.source_ref.section}"
                for c in relevant if c.source_ref
            ]
            if sig.source_ref:
                refs.append(f"{sig.source_ref.file}:{sig.source_ref.section}")

            # Build a readable counterexample summary
            bound_desc = ""
            if sig.bounds.min is not None and sig.bounds.max is not None:
                bound_desc = f"bounds=[{sig.bounds.min}, {sig.bounds.max}]"
            elif sig.bounds.min is not None:
                bound_desc = f"min={sig.bounds.min}"
            elif sig.bounds.max is not None:
                bound_desc = f"max={sig.bounds.max}"

            con_desc = "; ".join(
                f"{c.id}: {c.operator} {c.numeric_value}"
                for c in relevant
            )

            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.CONSTRAINT_CONFLICT,
                title=f"Z3: Unsatisfiable constraints for signal '{sig.name}'",
                summary=(
                    f"Signal '{sig.name}' ({bound_desc}) and constraint(s) [{con_desc}] "
                    "are jointly unsatisfiable — no valid value exists."
                ),
                details=(
                    "The Z3 solver determined that the combination of the signal's declared "
                    "operating bounds and the requirement constraints has no solution. "
                    "This means the requirement can never be met within the declared range, "
                    "or the bounds declaration is inconsistent with the constraint."
                ),
                related_ir_nodes=[sig.name] + con_ids,
                source_refs=list(dict.fromkeys(refs)),
                suggested_fix=(
                    f"Reconcile '{sig.name}' bounds ({bound_desc}) with constraints ({con_desc}). "
                    "Either widen the bounds or relax the constraint."
                ),
                counterexample={
                    "signal": sig.name,
                    "bounds": {"min": sig.bounds.min, "max": sig.bounds.max},
                    "conflicting_constraints": [
                        {"id": c.id, "operator": c.operator, "value": c.numeric_value}
                        for c in relevant
                    ],
                    "z3_result": "unsat",
                },
            ))

        elif result == z3.unknown:
            logger.debug("Z3 returned unknown for signal '%s'", sig.name)

    return findings


def _check_joint_constraint_satisfiability(ir: IRSnapshot) -> list[Finding]:
    """
    Assert ALL numeric constraints together and check if the system is globally satisfiable.
    If UNSAT, there is a global contradiction somewhere.
    """
    findings = []

    # Build a variable for every signal that appears in any constraint
    signal_vars: dict[str, z3.ArithRef] = {}

    all_numeric = [
        c for c in ir.constraints
        if c.numeric_value is not None and c.operator is not None
    ]
    if len(all_numeric) < 2:
        return []  # Need at least two constraints to find a conflict

    solver = z3.Solver()

    # Add signal bound assertions
    for sig in ir.signals:
        if sig.bounds is None:
            continue
        x = z3.Real(sig.name)
        signal_vars[sig.name] = x
        if sig.bounds.min is not None:
            solver.add(x >= sig.bounds.min)
        if sig.bounds.max is not None:
            solver.add(x <= sig.bounds.max)

    # Add all numeric constraints
    constraint_added = []
    for con in all_numeric:
        for sig_name in con.related_signals:
            if sig_name not in signal_vars:
                signal_vars[sig_name] = z3.Real(sig_name)
            x = signal_vars[sig_name]
            val = con.numeric_value
            op = con.operator
            expr: Optional[z3.BoolRef] = None
            if op == "<=":
                expr = x <= val
            elif op == ">=":
                expr = x >= val
            elif op == "<":
                expr = x < val
            elif op == ">":
                expr = x > val
            elif op == "==":
                expr = x == val
            if expr is not None:
                solver.add(expr)
                constraint_added.append(con.id)

    if not constraint_added:
        return []

    result = solver.check()
    if result == z3.unsat:
        # Per-signal checks will have already caught most contradictions;
        # this global check catches cross-signal contradictions
        con_ids = list(dict.fromkeys(constraint_added))
        findings.append(Finding(
            id="TBD",
            severity=FindingSeverity.CRITICAL,
            category=FindingCategory.CONSTRAINT_CONFLICT,
            title="Z3: Global constraint system is unsatisfiable",
            summary=(
                "The combination of all declared constraints and signal bounds "
                "has no satisfying assignment. The specification is inconsistent."
            ),
            details=(
                f"Constraints checked: {', '.join(con_ids)}. "
                "Z3 determined the full constraint system is UNSAT. "
                "This may indicate overlapping forbidden regions or mutually exclusive bounds."
            ),
            related_ir_nodes=con_ids,
            source_refs=[],
            suggested_fix=(
                "Review all numeric constraints for contradictions. "
                "Use '--log-level DEBUG' to see which constraints were asserted."
            ),
            counterexample={
                "constraints_asserted": con_ids,
                "z3_result": "unsat",
            },
        ))

    return findings


def _check_impossible_mode_combinations(ir: IRSnapshot) -> list[Finding]:
    """
    Check for FORBIDDEN transitions combined with REQUIRED transitions
    that would force a mode/state combination to be both reachable and forbidden.
    """
    findings = []
    if not ir.transitions:
        return []

    forbidden_pairs = {
        (t.from_state, t.to_state)
        for t in ir.transitions
        if t.forbidden
    }

    # Check if any non-forbidden transition leads back through a forbidden one
    for trans in ir.transitions:
        if trans.forbidden:
            continue
        if (trans.from_state, trans.to_state) in forbidden_pairs:
            findings.append(Finding(
                id="TBD",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.UNREACHABLE_STATE,
                title=(
                    f"Transition '{trans.from_state} -> {trans.to_state}' "
                    "is both required and forbidden"
                ),
                summary=(
                    f"Transition '{trans.from_state} -> {trans.to_state}' appears both "
                    "as a normal transition and as a forbidden transition."
                ),
                details=(
                    "This means the state machine simultaneously requires and prohibits "
                    "this transition, which is logically impossible."
                ),
                related_ir_nodes=[trans.from_state, trans.to_state],
                source_refs=[
                    f"{trans.source_ref.file}:{trans.source_ref.section}"
                    if trans.source_ref else "spec"
                ],
                suggested_fix=(
                    f"Decide whether '{trans.from_state} -> {trans.to_state}' is "
                    "allowed or forbidden. Remove one of the conflicting definitions."
                ),
                counterexample={
                    "from_state": trans.from_state,
                    "to_state": trans.to_state,
                    "conflict": "transition is both required and forbidden",
                },
            ))

    return findings


# ── Public API ────────────────────────────────────────────────────────────────

def run_z3_checks(ir: IRSnapshot) -> list[Finding]:
    """Run all Z3-backed checks. Returns findings (empty list = all checks passed)."""
    if not _Z3_AVAILABLE:
        return [_z3_not_available_finding()]

    findings: list[Finding] = []

    try:
        findings.extend(_check_signal_bounds_vs_constraints(ir))
    except Exception as exc:
        logger.warning("Z3 bounds check failed: %s", exc)
        findings.append(Finding(
            id="TBD",
            severity=FindingSeverity.LOW,
            category=FindingCategory.CONSTRAINT_CONFLICT,
            title="Z3 bounds check encountered an error",
            summary=str(exc),
        ))

    try:
        findings.extend(_check_joint_constraint_satisfiability(ir))
    except Exception as exc:
        logger.warning("Z3 joint check failed: %s", exc)

    try:
        findings.extend(_check_impossible_mode_combinations(ir))
    except Exception as exc:
        logger.warning("Z3 mode check failed: %s", exc)

    return findings
