"""
Z3-backed constraint checker for Engineering Assurance Layer.

Checks performed:
  1. Global contradictions (mode-independent constraints)
  2. Mode-scoped contradictions (constraints unsat only in specific modes)
  3. Signal-level unsat in mode (bounds + mode-scoped limits)
  4. Impossible transition combinations (required + forbidden)

## Unsat cores are not counterexamples

An UNSAT system has no satisfying assignment, so there is no model to report and
nothing that can honestly be called a counterexample. What can be reported is a
*minimal unsat core*: the smallest subset of asserted facts that is still
contradictory. That is the useful artifact anyway — it names the handful of
declarations a human has to reconcile, instead of the whole asserted set.

Every assertion is tracked, so cores can name signal bounds and the
one-mode-active rule, not only constraint IDs. Z3's own `unsat_core()` gives an
unsat but not necessarily irreducible subset, so each core is then minimized by
deletion: drop one element, re-check, keep the drop if the remainder is still
unsat. The result is irreducible — no proper subset of it is unsat — which is
what lets `minimal: true` be asserted rather than hoped for.

Findings carry these under `evidence.kind == "unsat_core"`. Nothing here emits
`kind == "witness"`; producing genuine counterexamples would mean searching for
a model that violates a desired property, which this module does not do.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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


@dataclass
class _SolverBundle:
    """
    A built solver plus everything needed to explain an UNSAT result.

    Facts are added as `selector => fact` with a fresh boolean selector, and
    satisfiability is queried as `check(*selectors)`. They are deliberately not
    added with `assert_and_track`: that asserts each fact *hard*, so omitting a
    tracker from a later `check()` does not actually retract the fact, the
    system stays unsat no matter what is dropped, and deletion-based
    minimization happily shrinks the core to the empty set. Selector
    implications make omission real, which is what the minimization below
    depends on.
    """

    solver: z3.Solver
    signal_vars: dict[str, z3.ArithRef] = field(default_factory=dict)
    mode_vars: dict[str, z3.BoolRef] = field(default_factory=dict)
    # selector label -> the boolean literal enabling that fact
    selectors: dict[str, z3.BoolRef] = field(default_factory=dict)
    # selector label -> human-readable description of the fact
    labels: dict[str, str] = field(default_factory=dict)
    # selector label -> constraint id, for the subset that came from constraints
    label_constraints: dict[str, str] = field(default_factory=dict)

    def check(self, assumptions: Optional[list[z3.BoolRef]] = None):
        """Satisfiability with every fact enabled, plus any scenario assumptions."""
        return self.solver.check(*list(self.selectors.values()), *(assumptions or []))


def _build_solver(
    ir: IRSnapshot,
    constraints: list[Constraint],
    with_mode_logic: bool,
) -> _SolverBundle:
    """
    Build a solver with every assertion individually tracked.

    Tracking is unconditional rather than enabled only on failure: a second,
    differently-built solver could disagree with the first about whether the
    system is UNSAT at all, and then the reported core would not explain the
    reported finding.
    """
    solver = z3.Solver()
    solver.set(unsat_core=True)
    bundle = _SolverBundle(solver=solver)

    def track(label: str, expr: z3.BoolRef, description: str, con_id: str | None = None) -> None:
        # Selector names must be unique within a solver.
        unique = label
        suffix = 2
        while unique in bundle.labels:
            unique = f"{label}#{suffix}"
            suffix += 1
        selector = z3.Bool(unique)
        bundle.selectors[unique] = selector
        bundle.labels[unique] = description
        if con_id is not None:
            bundle.label_constraints[unique] = con_id
        solver.add(z3.Implies(selector, expr))

    for sig in ir.signals:
        x = z3.Real(sig.name)
        bundle.signal_vars[sig.name] = x
        if sig.bounds is None:
            continue
        if sig.bounds.min is not None:
            track(
                f"BOUND:{sig.name}:min", x >= sig.bounds.min,
                f"declared bound {sig.name} >= {sig.bounds.min}",
            )
        if sig.bounds.max is not None:
            track(
                f"BOUND:{sig.name}:max", x <= sig.bounds.max,
                f"declared bound {sig.name} <= {sig.bounds.max}",
            )

    if with_mode_logic:
        for mode in _collect_modes(ir, constraints):
            bundle.mode_vars[mode] = z3.Bool(f"mode_{mode}")
        if bundle.mode_vars:
            track(
                "MODE:exactly_one_active",
                z3.PbEq([(v, 1) for v in bundle.mode_vars.values()], 1),
                "exactly one mode is active at a time",
            )

    for con in constraints:
        exprs = _constraint_exprs(con, bundle.signal_vars)
        if not exprs:
            continue

        scoped_modes = [m for m in _constraint_modes(con) if m in bundle.mode_vars]
        for sig_name, expr in exprs:
            if with_mode_logic and scoped_modes:
                cond = z3.Or([bundle.mode_vars[m] for m in scoped_modes])
                asserted = z3.Implies(cond, expr)
                description = (
                    f"{con.expression_text} (applies in "
                    f"{', '.join(scoped_modes)})"
                )
            else:
                asserted = expr
                description = con.expression_text
            track(f"{con.id}:{sig_name}", asserted, description, con_id=con.id)

    return bundle


def _minimal_unsat_core(
    bundle: _SolverBundle,
    assumptions: Optional[list[z3.BoolRef]] = None,
) -> list[str]:
    """
    Return an irreducible unsat core as tracker labels.

    Z3's `unsat_core()` is unsat but not guaranteed minimal, so this shrinks it
    by deletion: for each element, re-check without it and keep the removal when
    the remainder is still unsat. On return, no proper subset of the result is
    unsat — which is what makes `minimal: true` a claim and not a hope.

    Scenario assumptions (such as "mode X is active") are held fixed throughout.
    They frame the question being asked rather than being facts under suspicion,
    so they are never minimized away and never reported as part of the core.
    """
    assumptions = assumptions or []
    core_names = [str(c) for c in bundle.solver.unsat_core()]
    # Keep only our own selectors; scenario assumptions can appear here too.
    core = [name for name in core_names if name in bundle.selectors]

    i = 0
    while i < len(core):
        candidate = core[:i] + core[i + 1:]
        literals = [bundle.selectors[name] for name in candidate]
        if bundle.solver.check(*(literals + assumptions)) == z3.unsat:
            core = candidate  # this fact was not needed
        else:
            i += 1
    return sorted(core)


def _core_evidence(
    bundle: _SolverBundle,
    core_labels: list[str],
    **extra,
) -> dict:
    """Build the machine-readable explanation attached to an UNSAT finding."""
    return {
        "kind": "unsat_core",
        "z3_result": "unsat",
        "minimal": True,
        "note": (
            "An unsatisfiable system has no model, so there is no counterexample "
            "to report. This is a minimal unsat core: the listed facts are jointly "
            "contradictory and no proper subset of them is."
        ),
        "core_size": len(core_labels),
        "core": [
            {
                "label": label,
                "constraint_id": bundle.label_constraints.get(label),
                "fact": bundle.labels.get(label, label),
            }
            for label in core_labels
        ],
        "core_constraint_ids": sorted(
            {
                bundle.label_constraints[label]
                for label in core_labels
                if label in bundle.label_constraints
            }
        ),
        **extra,
    }


def _core_summary(bundle: _SolverBundle, core_labels: list[str]) -> str:
    return "; ".join(bundle.labels.get(label, label) for label in core_labels)


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
            bundle = _build_solver(ir, global_relevant, with_mode_logic=False)
            if bundle.check() == z3.unsat:
                core = _minimal_unsat_core(bundle)
                core_ids = sorted(
                    {bundle.label_constraints[c] for c in core if c in bundle.label_constraints}
                )
                findings.append(
                    Finding(
                        id="TBD",
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.GLOBAL_CONSTRAINT_CONFLICT,
                        title=f"Z3: Unsatisfiable global constraints for signal '{sig.name}'",
                        summary=(
                            f"Signal '{sig.name}' cannot take any value. Minimal "
                            f"contradictory set ({len(core)} fact(s)): "
                            f"{_core_summary(bundle, core)}."
                        ),
                        details=(
                            "Mode-independent constraints already contradict this signal's "
                            "declared bounds. Only the facts listed in the core need to be "
                            "reconciled; the rest of the constraint set is not involved."
                        ),
                        related_ir_nodes=[sig.name] + core_ids,
                        source_refs=_source_refs_for_constraints(
                            [c for c in global_relevant if c.id in core_ids]
                        ) or _source_refs_for_constraints(global_relevant),
                        suggested_fix=(
                            f"Reconcile global limits for '{sig.name}' with its declared bounds."
                        ),
                        counterexample=_core_evidence(
                            bundle, core, scope="global", signal=sig.name,
                        ),
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

            bundle = _build_solver(ir, mode_constraints, with_mode_logic=True)
            if mode not in bundle.mode_vars:
                continue

            active = [bundle.mode_vars[mode]]
            if bundle.check(active) == z3.unsat:
                core = _minimal_unsat_core(bundle, assumptions=active)
                core_ids = sorted(
                    {bundle.label_constraints[c] for c in core if c in bundle.label_constraints}
                )
                findings.append(
                    Finding(
                        id="TBD",
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.UNSAT_IN_MODE,
                        title=f"Z3: Unsatisfiable constraints for signal '{sig.name}' in mode '{mode}'",
                        summary=(
                            f"Signal '{sig.name}' cannot take any value while mode '{mode}' is "
                            f"active. Minimal contradictory set ({len(core)} fact(s)): "
                            f"{_core_summary(bundle, core)}."
                        ),
                        details=(
                            "This conflict is mode-scoped: the same signal may remain satisfiable "
                            "outside the failing mode. Only the facts listed in the core need to "
                            "be reconciled."
                        ),
                        related_ir_nodes=[sig.name] + core_ids,
                        source_refs=_source_refs_for_constraints(
                            [c for c in mode_constraints if c.id in core_ids]
                        ) or _source_refs_for_constraints(mode_constraints),
                        suggested_fix=(
                            f"Reconcile '{sig.name}' bounds and limits specific to mode '{mode}'."
                        ),
                        counterexample=_core_evidence(
                            bundle, core, scope="mode", mode=mode, signal=sig.name,
                        ),
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
        bundle = _build_solver(ir, global_numeric, with_mode_logic=False)
        if bundle.check() == z3.unsat:
            core = _minimal_unsat_core(bundle)
            core_ids = sorted(
                {bundle.label_constraints[c] for c in core if c in bundle.label_constraints}
            )
            findings.append(
                Finding(
                    id="TBD",
                    severity=FindingSeverity.CRITICAL,
                    category=FindingCategory.GLOBAL_CONSTRAINT_CONFLICT,
                    title="Z3: Global constraint system is unsatisfiable",
                    summary=(
                        f"Mode-independent constraints and bounds have no satisfying "
                        f"assignment. Minimal contradictory set ({len(core)} fact(s)): "
                        f"{_core_summary(bundle, core)}."
                    ),
                    details=(
                        f"{len(global_numeric)} constraint(s) were asserted; only "
                        f"{len(core_ids)} of them appear in the minimal core. "
                        "The contradiction exists regardless of active mode."
                    ),
                    related_ir_nodes=core_ids,
                    source_refs=_source_refs_for_constraints(
                        [c for c in global_numeric if c.id in core_ids]
                    ) or _source_refs_for_constraints(global_numeric),
                    suggested_fix="Resolve contradictions in global bounds/constraints.",
                    counterexample=_core_evidence(bundle, core, scope="global"),
                )
            )

    has_mode_scoped = any(_constraint_modes(c) for c in all_numeric)
    if not has_mode_scoped:
        return findings

    bundle = _build_solver(ir, all_numeric, with_mode_logic=True)
    for mode in sorted(bundle.mode_vars):
        active = [bundle.mode_vars[mode]]
        if bundle.check(active) != z3.unsat:
            continue

        core = _minimal_unsat_core(bundle, assumptions=active)
        core_ids = sorted(
            {bundle.label_constraints[c] for c in core if c in bundle.label_constraints}
        )
        asserted_count = len([
            c for c in all_numeric
            if _is_global_constraint(c) or mode in _constraint_modes(c)
        ])
        findings.append(
            Finding(
                id="TBD",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.MODE_SCOPED_CONFLICT,
                title=f"Z3: Constraint system is unsatisfiable in mode '{mode}'",
                summary=(
                    f"When mode '{mode}' is active, numeric constraints are jointly "
                    f"unsatisfiable. Minimal contradictory set ({len(core)} fact(s)): "
                    f"{_core_summary(bundle, core)}."
                ),
                details=(
                    f"{asserted_count} constraint(s) apply in this mode; only "
                    f"{len(core_ids)} of them appear in the minimal core. "
                    "This is a mode-local contradiction; other modes may still be satisfiable."
                ),
                related_ir_nodes=core_ids,
                source_refs=_source_refs_for_constraints(
                    [c for c in all_numeric if c.id in core_ids]
                ) or _source_refs_for_constraints(all_numeric),
                suggested_fix=(
                    f"Reconcile constraints that apply in mode '{mode}' or relax mode-specific bounds."
                ),
                counterexample=_core_evidence(bundle, core, scope="mode", mode=mode),
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
                        # Structural contradiction found by direct comparison, not
                        # by the solver — labelled so it is not mistaken for either
                        # a solver core or a model witness.
                        "kind": "structural_conflict",
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
