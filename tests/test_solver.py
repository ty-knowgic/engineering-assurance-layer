"""Tests for Z3-backed constraint checks."""

from __future__ import annotations

import pytest

from eal.findings.schema import FindingCategory, FindingSeverity
from eal.ir.schema import (
    Bounds,
    Constraint,
    ConstraintScopeType,
    ConstraintType,
    IRSnapshot,
    Mode,
    Signal,
    SignalKind,
    Transition,
)
from eal.solver.z3_checker import run_z3_checks

z3 = pytest.importorskip("z3", reason="z3-solver not installed")


def _ir(**kwargs) -> IRSnapshot:
    return IRSnapshot(spec_file="test.md", **kwargs)


# ── Bounds vs constraint contradiction ────────────────────────────────────────

def test_z3_detects_unsat_bounds():
    """
    joint_speed has min=1.5, constraint says <= 1.2.
    Z3 should detect this as UNSAT.
    """
    ir = _ir(
        signals=[
            Signal(
                name="joint_speed",
                kind=SignalKind.SENSOR,
                bounds=Bounds(min=1.5, max=2.5),
            )
        ],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="joint_speed <= 1.2",
                constraint_type=ConstraintType.INVARIANT,
                related_signals=["joint_speed"],
                numeric_value=1.2,
                operator="<=",
            )
        ],
    )
    findings = run_z3_checks(ir)
    assert len(findings) >= 1
    assert any(f.severity == FindingSeverity.CRITICAL for f in findings)
    assert any(
        f.category == FindingCategory.GLOBAL_CONSTRAINT_CONFLICT for f in findings
    )
    # Counterexample should be present
    ce_findings = [f for f in findings if f.counterexample is not None]
    assert len(ce_findings) >= 1
    assert ce_findings[0].counterexample["z3_result"] == "unsat"


def test_z3_satisfiable_no_finding():
    """
    speed has bounds [0, 10], constraint says <= 5.
    This is satisfiable — Z3 should produce no critical finding.
    """
    ir = _ir(
        signals=[
            Signal(name="speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=10))
        ],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="speed <= 5",
                constraint_type=ConstraintType.INVARIANT,
                related_signals=["speed"],
                numeric_value=5.0,
                operator="<=",
            )
        ],
    )
    findings = run_z3_checks(ir)
    critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
    assert len(critical) == 0


def test_z3_max_bound_violation():
    """
    torque has max=8, constraint says >= 10.
    8 < 10 → UNSAT.
    """
    ir = _ir(
        signals=[
            Signal(name="torque", kind=SignalKind.ACTUATOR, bounds=Bounds(min=0, max=8))
        ],
        constraints=[
            Constraint(
                id="CON-002",
                expression_text="torque >= 10",
                constraint_type=ConstraintType.INVARIANT,
                related_signals=["torque"],
                numeric_value=10.0,
                operator=">=",
            )
        ],
    )
    findings = run_z3_checks(ir)
    assert any(f.severity == FindingSeverity.CRITICAL for f in findings)
    assert any(
        f.category == FindingCategory.GLOBAL_CONSTRAINT_CONFLICT for f in findings
    )


def test_z3_mode_scoped_unsat_not_global():
    """
    joint_speed bound min=1.5 conflicts with <=1.2 only in CALIBRATION mode.
    Global system remains satisfiable but CALIBRATION is UNSAT.
    """
    ir = _ir(
        modes=[Mode(name="CALIBRATION"), Mode(name="NORMAL")],
        signals=[
            Signal(
                name="joint_speed",
                kind=SignalKind.SENSOR,
                bounds=Bounds(min=1.5, max=2.5),
            )
        ],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="joint_speed <= 1.2 when mode = CALIBRATION",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.MODE,
                applies_globally=False,
                applies_in_modes=["CALIBRATION"],
                related_signals=["joint_speed"],
                related_modes=["CALIBRATION"],
                numeric_value=1.2,
                operator="<=",
            )
        ],
    )
    findings = run_z3_checks(ir)
    categories = {f.category for f in findings}
    assert FindingCategory.UNSAT_IN_MODE in categories
    assert FindingCategory.GLOBAL_CONSTRAINT_CONFLICT not in categories


def test_z3_mode_scoped_satisfiable_in_other_mode():
    ir = _ir(
        modes=[Mode(name="CALIBRATION"), Mode(name="NORMAL")],
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=2.5))],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="joint_speed <= 1.2 when mode = CALIBRATION",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.MODE,
                applies_globally=False,
                applies_in_modes=["CALIBRATION"],
                related_signals=["joint_speed"],
                related_modes=["CALIBRATION"],
                numeric_value=1.2,
                operator="<=",
            )
        ],
    )
    findings = run_z3_checks(ir)
    # No contradiction expected.
    assert not any(f.severity == FindingSeverity.CRITICAL for f in findings)


def test_z3_mode_scoped_joint_conflict_category():
    ir = _ir(
        modes=[Mode(name="CALIBRATION"), Mode(name="NORMAL")],
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=3.0))],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="joint_speed <= 1.0 when mode = CALIBRATION",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.MODE,
                applies_globally=False,
                applies_in_modes=["CALIBRATION"],
                related_signals=["joint_speed"],
                related_modes=["CALIBRATION"],
                numeric_value=1.0,
                operator="<=",
            ),
            Constraint(
                id="CON-002",
                expression_text="joint_speed >= 2.0 when mode = CALIBRATION",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.MODE,
                applies_globally=False,
                applies_in_modes=["CALIBRATION"],
                related_signals=["joint_speed"],
                related_modes=["CALIBRATION"],
                numeric_value=2.0,
                operator=">=",
            ),
        ],
    )
    findings = run_z3_checks(ir)
    categories = {f.category for f in findings}
    assert FindingCategory.MODE_SCOPED_CONFLICT in categories
    assert FindingCategory.GLOBAL_CONSTRAINT_CONFLICT not in categories


# ── Impossible mode combinations ─────────────────────────────────────────────

def test_z3_detects_both_required_and_forbidden():
    """
    Transition A->B exists both as a normal transition and as a forbidden one.
    """
    ir = _ir(
        transitions=[
            Transition(from_state="A", to_state="B", forbidden=False),
            Transition(from_state="A", to_state="B", forbidden=True),
        ]
    )
    findings = run_z3_checks(ir)
    assert any(f.category == FindingCategory.UNREACHABLE_STATE for f in findings)


def test_z3_no_forbidden_pair_no_finding():
    ir = _ir(
        transitions=[
            Transition(from_state="IDLE", to_state="RUNNING", forbidden=False),
            Transition(from_state="RUNNING", to_state="STOPPED", forbidden=False),
        ]
    )
    findings = run_z3_checks(ir)
    unreachable = [f for f in findings if f.category == FindingCategory.UNREACHABLE_STATE]
    assert len(unreachable) == 0


# ── Full example ──────────────────────────────────────────────────────────────

def test_z3_robotics_arm_detects_contradiction(robotics_arm_spec, robotics_arm_model):
    """
    Robotics arm has mode-scoped UNSAT in CALIBRATION:
    joint_speed min=1.5 > calibration limit 1.2.
    """
    from eal.ingestion import load_spec, load_model
    from eal.extraction import extract_ir_from_spec, merge_model_into_ir
    spec = load_spec(robotics_arm_spec)
    model = load_model(robotics_arm_model)
    ir = extract_ir_from_spec(spec)
    merge_model_into_ir(ir, model)
    findings = run_z3_checks(ir)
    critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
    assert len(critical) >= 1
    categories = {f.category for f in critical}
    assert FindingCategory.UNSAT_IN_MODE in categories or FindingCategory.MODE_SCOPED_CONFLICT in categories


def test_z3_empty_ir_no_crash():
    ir = IRSnapshot(spec_file="empty.md")
    findings = run_z3_checks(ir)
    assert isinstance(findings, list)
