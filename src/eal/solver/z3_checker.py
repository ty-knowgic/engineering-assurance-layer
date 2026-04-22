"""
Z3-backed constraint checker for Engineering Assurance Layer.

Checks performed:
  1. Global contradictions (mode-independent constraints)
  2. Mode-scoped contradictions (constraints unsat only in specific modes)
  3. Signal-level unsat in mode (bounds + mode-scoped limits)
  4. Impossible transition combinations (required + forbidden)
"""

from __future__ import annotations

import logging
from typing import Optional

from eal.findings.schema import Finding, FindingCategory, FindingSeverity
from eal.ir.schema import Constraint, ConstraintScopeType, ConstraintType, IRSnapshot

logger = logging.getLogger(__name__)

try:
    import z3

    _Z3_AVAILABLE = True
except ImportError:
    _Z3_AVAILABLE = False


_NUMERIC_OPS = {"<=", ">=", "<", ">", "==", "!="}


def _z3_not_available_finding() -> Finding:
    return Finding(
        id="TBD",
        severity=FindingSeverity.LOW,
        category=FindingCategory.CONSTRAINT_CONFLICT,
        title="Z3 solver not available — constraint checks skipped",
        summary="Install z3-solver to enable symbolic constraint checking.",
        suggested_fix="pip install z3-solver",
    )


def _numeric_constraints(ir: IRSnapshot) -> list[Constraint]:
    return [
        c
        for c in ir.constraints
        if c.numeric_value is not None
        and c.operator in _NUMERIC_OPS
        and c.related_signals
        and c.constraint_type in (ConstraintType.BOUND, ConstraintType.INVARIANT)
    ]


def _constraint_modes(con: Constraint) -> list[str]:
    modes = con.applies_in_modes or con.related_modes
    # stable unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for mode in modes:
        if mode not in seen:
            seen.add(mode)
            ordered.append(mode)
    return ordered


def _is_global_constraint(con: Constraint) -> bool:
    if con.scope_type == ConstraintScopeType.MODE:
        return False
    if _constraint_modes(con):
        return False
    return bool(con.applies_globally)


def _collect_modes(ir: IRSnapshot, constraints: list[Constraint]) -> list[str]:
    names: list[str] = [m.name for m in ir.modes]
    for con in constraints:
        for mode in _constraint_modes(con):
            if mode not in names:
                names.append(mode)
    return sorted(dict.fromkeys(names))


def _constraint_exprs(
    con: Constraint,
    signal_vars: dict[str, z3.ArithRef],
) -> list[tuple[str, z3.BoolRef]]:
    exprs: list[tuple[str, z3.BoolRef]] = []
    val = float(con.numeric_value) if con.numeric_value is not None else None
    op = con.operator
    if val is None or op is None:
        return exprs

    for sig_name in con.related_signals:
        if sig_name not in signal_vars:
            signal_vars[sig_name] = z3.Real(sig_name)
        x = signal_vars[sig_name]
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
        elif op == "!=":
            expr = x != val

        if expr is not None:
            exprs.append((sig_name, expr))

    return exprs


def _build_solver(
    ir: IRSnapshot,
    constraints: list[Constraint],
    with_mode_logic: bool,
) -> tuple[z3.Solver, dict[str, z3.ArithRef], dict[str, z3.BoolRef]]:
    solver = z3.Solver()
    signal_vars: dict[str, z3.ArithRef] = {}

    for sig in ir.signals:
        x = z3.Real(sig.name)
        signal_vars[sig.name] = x
        if sig.bounds is None:
            continue
        if sig.bounds.min is not None:
            solver.add(x >= sig.bounds.min)
        if sig.bounds.max is not None:
            solver.add(x <= sig.bounds.max)

    mode_vars: dict[str, z3.BoolRef] = {}
    if with_mode_logic:
        mode_names = _collect_modes(ir, constraints)
        for mode in mode_names:
            mode_vars[mode] = z3.Bool(f"mode_{mode}")
        if mode_vars:
            # Exactly one mode active.
            solver.add(z3.PbEq([(v, 1) for v in mode_vars.values()], 1))

    for con in constraints:
        exprs = _constraint_exprs(con, signal_vars)
        if not exprs:
            continue

        scoped_modes = [m for m in _constraint_modes(con) if m in mode_vars]
        if with_mode_logic and scoped_modes:
            cond = z3.Or([mode_vars[m] for m in scoped_modes])
            for _, expr in exprs:
                solver.add(z3.Implies(cond, expr))
        else:
            for _, expr in exprs:
                solver.add(expr)

    return solver, signal_vars, mode_vars


def _source_refs_for_constraints(constraints: list[Constraint]) -> list[str]:
    refs = [
        f"{c.source_ref.file}:{c.source_ref.section}"
        for c in constraints
        if c.source_ref
    ]
    return list(dict.fromkeys(refs))


def _check_signal_bounds_vs_constraints(ir: IRSnapshot) -> list[Finding]:
    """
    Check signal-level satisfiability with mode awareness.

    Emits:
      - GLOBAL_CONSTRAINT_CONFLICT when global constraints conflict with bounds
      - UNSAT_IN_MODE when a mode-specific subset conflicts with bounds
    """
    findings: list[Finding] = []
    all_numeric = _numeric_constraints(ir)

    for sig in ir.signals:
        if sig.bounds is None:
            continue

        relevant = [c for c in all_numeric if sig.name in c.related_signals]
        if not relevant:
            continue

        global_relevant = [c for c in relevant if _is_global_constraint(c)]

        if global_relevant:
            solver, _, _ = _build_solver(ir, global_relevant, with_mode_logic=False)
            if solver.check() == z3.unsat:
                con_ids = [c.id for c in global_relevant]
                findings.append(
                    Finding(
                        id="TBD",
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.GLOBAL_CONSTRAINT_CONFLICT,
                        title=f"Z3: Unsatisfiable global constraints for signal '{sig.name}'",
                        summary=(
                            f"Signal '{sig.name}' bounds and global constraint set "
                            f"[{', '.join(con_ids)}] are unsatisfiable."
                        ),
                        details=(
                            "Mode-independent constraints already contradict this signal's "
                            "declared bounds."
                        ),
                        related_ir_nodes=[sig.name] + con_ids,
                        source_refs=_source_refs_for_constraints(global_relevant),
                        suggested_fix=(
                            f"Reconcile global limits for '{sig.name}' with its declared bounds."
                        ),
                        counterexample={
                            "scope": "global",
                            "signal": sig.name,
                            "conflicting_constraints": con_ids,
                            "z3_result": "unsat",
                        },
                    )
                )

        mode_names = sorted(
            {
                m
                for con in relevant
                for m in _constraint_modes(con)
            }
        )
        for mode in mode_names:
            mode_constraints = global_relevant + [
                c for c in relevant if mode in _constraint_modes(c)
            ]
            has_scoped = any(mode in _constraint_modes(c) for c in mode_constraints)
            if not has_scoped:
                continue

            solver, _, mode_vars = _build_solver(ir, mode_constraints, with_mode_logic=True)
            if mode not in mode_vars:
                continue

            solver.push()
            solver.add(mode_vars[mode])
            result = solver.check()
            solver.pop()

            if result == z3.unsat:
                con_ids = [c.id for c in mode_constraints]
                findings.append(
                    Finding(
                        id="TBD",
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.UNSAT_IN_MODE,
                        title=f"Z3: Unsatisfiable constraints for signal '{sig.name}' in mode '{mode}'",
                        summary=(
                            f"Signal '{sig.name}' is unsatisfiable when mode '{mode}' is active "
                            f"under constraints [{', '.join(con_ids)}]."
                        ),
                        details=(
                            "This conflict is mode-scoped: the same signal may remain satisfiable "
                            "outside the failing mode."
                        ),
                        related_ir_nodes=[sig.name] + con_ids,
                        source_refs=_source_refs_for_constraints(mode_constraints),
                        suggested_fix=(
                            f"Reconcile '{sig.name}' bounds and limits specific to mode '{mode}'."
                        ),
                        counterexample={
                            "scope": "mode",
                            "mode": mode,
                            "signal": sig.name,
                            "conflicting_constraints": con_ids,
                            "z3_result": "unsat",
                        },
                    )
                )

    return findings


def _check_joint_constraint_satisfiability(ir: IRSnapshot) -> list[Finding]:
    """
    Check system-level satisfiability globally and per mode.

    Emits:
      - GLOBAL_CONSTRAINT_CONFLICT if global constraint system is UNSAT
      - MODE_SCOPED_CONFLICT if mode-qualified system is UNSAT in one mode
    """
    findings: list[Finding] = []
    all_numeric = _numeric_constraints(ir)
    if len(all_numeric) < 2:
        return findings

    global_numeric = [c for c in all_numeric if _is_global_constraint(c)]
    if len(global_numeric) >= 2:
        solver, _, _ = _build_solver(ir, global_numeric, with_mode_logic=False)
        if solver.check() == z3.unsat:
            con_ids = [c.id for c in global_numeric]
            findings.append(
                Finding(
                    id="TBD",
                    severity=FindingSeverity.CRITICAL,
                    category=FindingCategory.GLOBAL_CONSTRAINT_CONFLICT,
                    title="Z3: Global constraint system is unsatisfiable",
                    summary=(
                        "Mode-independent constraints and bounds have no satisfying assignment."
                    ),
                    details=(
                        f"Constraints checked: {', '.join(con_ids)}. "
                        "The contradiction exists regardless of active mode."
                    ),
                    related_ir_nodes=con_ids,
                    source_refs=_source_refs_for_constraints(global_numeric),
                    suggested_fix="Resolve contradictions in global bounds/constraints.",
                    counterexample={
                        "scope": "global",
                        "constraints_asserted": con_ids,
                        "z3_result": "unsat",
                    },
                )
            )

    has_mode_scoped = any(_constraint_modes(c) for c in all_numeric)
    if not has_mode_scoped:
        return findings

    solver, _, mode_vars = _build_solver(ir, all_numeric, with_mode_logic=True)
    for mode in sorted(mode_vars):
        solver.push()
        solver.add(mode_vars[mode])
        result = solver.check()
        solver.pop()

        if result != z3.unsat:
            continue

        active_constraints = [
            c.id
            for c in all_numeric
            if _is_global_constraint(c) or mode in _constraint_modes(c)
        ]
        active_nodes = list(dict.fromkeys(active_constraints))
        findings.append(
            Finding(
                id="TBD",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.MODE_SCOPED_CONFLICT,
                title=f"Z3: Constraint system is unsatisfiable in mode '{mode}'",
                summary=(
                    f"When mode '{mode}' is active, numeric constraints are jointly unsatisfiable."
                ),
                details=(
                    "This is a mode-local contradiction; other modes may still be satisfiable."
                ),
                related_ir_nodes=active_nodes,
                source_refs=_source_refs_for_constraints(all_numeric),
                suggested_fix=(
                    f"Reconcile constraints that apply in mode '{mode}' or relax mode-specific bounds."
                ),
                counterexample={
                    "scope": "mode",
                    "mode": mode,
                    "constraints_asserted": active_nodes,
                    "z3_result": "unsat",
                },
            )
        )

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
            findings.append(
                Finding(
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
                        if trans.source_ref
                        else "spec"
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
                )
            )

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
        findings.append(
            Finding(
                id="TBD",
                severity=FindingSeverity.LOW,
                category=FindingCategory.CONSTRAINT_CONFLICT,
                title="Z3 bounds check encountered an error",
                summary=str(exc),
            )
        )

    try:
        findings.extend(_check_joint_constraint_satisfiability(ir))
    except Exception as exc:
        logger.warning("Z3 joint check failed: %s", exc)
        findings.append(
            Finding(
                id="TBD",
                severity=FindingSeverity.LOW,
                category=FindingCategory.CONSTRAINT_CONFLICT,
                title="Z3 joint satisfiability check encountered an error",
                summary=str(exc),
            )
        )

    try:
        findings.extend(_check_impossible_mode_combinations(ir))
    except Exception as exc:
        logger.warning("Z3 mode check failed: %s", exc)

    return findings
