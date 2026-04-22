"""Tests for IR schema construction and helpers."""

from __future__ import annotations

from eal.ir.schema import (
    Bounds, Constraint, ConstraintType, IRSnapshot,
    CodeConstant, CodeComparison, CodeEvidence, Mode, Requirement, Signal, SignalKind, State, Transition,
)


def _make_ir() -> IRSnapshot:
    return IRSnapshot(
        spec_file="test.md",
        signals=[
            Signal(name="speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=10)),
            Signal(name="torque", kind=SignalKind.ACTUATOR),
        ],
        states=[
            State(name="IDLE"),
            State(name="RUNNING"),
        ],
        modes=[
            Mode(name="NORMAL"),
        ],
        requirements=[
            Requirement(id="REQ-001", text="speed <= 5"),
        ],
        constraints=[
            Constraint(
                id="CON-001",
                expression_text="speed <= 5",
                constraint_type=ConstraintType.BOUND,
                related_signals=["speed"],
                numeric_value=5.0,
                operator="<=",
            ),
        ],
    )


def test_signal_names():
    ir = _make_ir()
    assert ir.signal_names() == {"speed", "torque"}


def test_state_names():
    ir = _make_ir()
    assert ir.state_names() == {"IDLE", "RUNNING"}


def test_mode_names():
    ir = _make_ir()
    assert ir.mode_names() == {"NORMAL"}


def test_signals_with_bounds():
    ir = _make_ir()
    bounded = ir.signals_with_bounds()
    assert len(bounded) == 1
    assert bounded[0].name == "speed"


def test_numeric_constraints():
    ir = _make_ir()
    nc = ir.numeric_constraints()
    assert len(nc) == 1
    assert nc[0].id == "CON-001"
    assert nc[0].numeric_value == 5.0


def test_constraint_by_id():
    ir = _make_ir()
    assert ir.constraint_by_id("CON-001") is not None
    assert ir.constraint_by_id("MISSING") is None


def test_ir_json_serializable():
    ir = _make_ir()
    ir.code_constants.append(
        CodeConstant(
            evidence_id="CC-001",
            file="controller.py",
            line=10,
            symbol="MAX_SPEED",
            normalized_name="speed",
            value=5.0,
        )
    )
    ir.code_comparisons.append(
        CodeComparison(
            evidence_id="CMP-001",
            file="controller.py",
            line=11,
            symbol="speed",
            normalized_name="speed",
            operator="<=",
            value=5.0,
        )
    )
    ir.code_evidence.append(
        CodeEvidence(
            evidence_id="CC-001",
            kind="constant",
            file="controller.py",
            line=10,
            symbol="MAX_SPEED",
            value=5.0,
        )
    )
    import json
    data = ir.extra_model_fields()
    text = json.dumps(data)  # must not raise
    assert "speed" in text


def test_ir_empty_is_valid():
    ir = IRSnapshot(spec_file="empty.md")
    assert ir.signal_names() == set()
    assert ir.state_names() == set()
    assert ir.numeric_constraints() == []
