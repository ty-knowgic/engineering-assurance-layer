"""Tests for markdown spec extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from eal.ingestion.loaders import load_spec
from eal.extraction.spec_extractor import extract_ir_from_spec
from eal.ir.schema import SignalKind, ConstraintType


# ── Signal extraction ─────────────────────────────────────────────────────────

def test_signal_extraction_basic(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- joint_speed: sensor, rad/s, bounds=[0, 2.5]
- motor_torque: actuator, Nm
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.signals) == 2
    names = {s.name for s in ir.signals}
    assert "joint_speed" in names
    assert "motor_torque" in names


def test_signal_bounds_parsed(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- joint_speed: sensor, rad/s, bounds=[0, 2.5]
"""))
    ir = extract_ir_from_spec(spec)
    sig = ir.signals[0]
    assert sig.bounds is not None
    assert sig.bounds.min == 0.0
    assert sig.bounds.max == 2.5


def test_signal_kind_parsed(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- torque: actuator, Nm, bounds=[0, 100]
- speed: sensor, m/s, bounds=[0, 5]
"""))
    ir = extract_ir_from_spec(spec)
    kinds = {s.name: s.kind for s in ir.signals}
    assert kinds["torque"] == SignalKind.ACTUATOR
    assert kinds["speed"] == SignalKind.SENSOR


def test_signal_no_bounds(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- temperature: sensor, C
"""))
    ir = extract_ir_from_spec(spec)
    assert ir.signals[0].bounds is None


# ── State extraction ──────────────────────────────────────────────────────────

def test_state_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## States

- IDLE: waiting for task
- OPERATING: executing motion plan
- SAFE_STOP: controlled halt
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.states) == 3
    names = {s.name for s in ir.states}
    assert "IDLE" in names
    assert "SAFE_STOP" in names


# ── Requirement extraction ────────────────────────────────────────────────────

def test_requirement_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Requirements

- REQ-001: Joint speed must remain <= 1.2 rad/s in CALIBRATION mode.
- REQ-002: The gripper must not close when human_detected = true.
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.requirements) == 2
    ids = {r.id for r in ir.requirements}
    assert "REQ-001" in ids
    assert "REQ-002" in ids


def test_requirement_text_preserved(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Requirements

- REQ-001: speed must remain <= 5.0 m/s.
"""))
    ir = extract_ir_from_spec(spec)
    assert "speed must remain <= 5.0 m/s" in ir.requirements[0].text


# ── Constraint extraction ─────────────────────────────────────────────────────

def test_safety_constraint_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Safety Constraints

- CON-001: motor_torque <= 10 Nm when mode = MAINTENANCE
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.constraints) == 1
    con = ir.constraints[0]
    assert con.id == "CON-001"
    assert con.constraint_type == ConstraintType.INVARIANT


def test_forbidden_condition_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Forbidden Conditions

- FC-001: gripper_force > 0 when human_detected = true
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.constraints) == 1
    assert ir.constraints[0].constraint_type == ConstraintType.FORBIDDEN


def test_timing_constraint_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Timing Constraints

- TC-001: OPERATING -> SAFE_STOP within 100 ms
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.constraints) == 1
    assert ir.constraints[0].constraint_type == ConstraintType.TIMING


# ── Transition extraction ─────────────────────────────────────────────────────

def test_transition_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Transitions

- IDLE -> OPERATING: guard=task_ready
- OPERATING -> SAFE_STOP: guard=e_stop_active=true
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.transitions) == 2
    assert ir.transitions[0].from_state == "IDLE"
    assert ir.transitions[0].to_state == "OPERATING"


# ── Assumption extraction ─────────────────────────────────────────────────────

def test_assumption_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Assumptions

- ASM-001: Sensor latency is < 10 ms.
"""))
    ir = extract_ir_from_spec(spec)
    assert len(ir.assumptions) == 1
    assert ir.assumptions[0].id == "ASM-001"


def test_assumption_timing_classification(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Assumptions

- ASM-001: The sensor has a response time of < 10 ms.
"""))
    ir = extract_ir_from_spec(spec)
    from eal.ir.schema import AssumptionType
    assert ir.assumptions[0].assumption_type == AssumptionType.TIMING


# ── Full example ──────────────────────────────────────────────────────────────

def test_robotics_arm_spec_loads(robotics_arm_spec):
    spec = load_spec(robotics_arm_spec)
    ir = extract_ir_from_spec(spec)
    assert len(ir.signals) >= 4
    assert len(ir.states) >= 4
    assert len(ir.requirements) >= 5
    assert len(ir.constraints) >= 2


def test_mobile_robot_spec_loads(mobile_robot_spec):
    spec = load_spec(mobile_robot_spec)
    ir = extract_ir_from_spec(spec)
    assert len(ir.signals) >= 4
    assert len(ir.requirements) >= 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_spec(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "spec.md"
    p.write_text(content)
    return p
