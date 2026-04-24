"""Tests for markdown spec extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from eal.extraction import merge_model_into_ir
from eal.ingestion.loaders import load_spec
from eal.extraction.spec_extractor import extract_ir_from_spec
from eal.ingestion import load_model
from eal.ir.schema import ConstraintScopeType, ConstraintType, RequirementLinkClass, SignalKind


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


def test_mode_scoped_constraint_extraction(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Modes

- NORMAL: standard operation
- MAINTENANCE: maintenance mode

## Signals

- motor_torque: actuator, Nm, bounds=[0, 120]

## Safety Constraints

- CON-001: motor_torque <= 10 Nm when mode = MAINTENANCE
"""))
    ir = extract_ir_from_spec(spec)
    con = next(c for c in ir.constraints if c.id == "CON-001")
    assert con.scope_type == ConstraintScopeType.MODE
    assert con.applies_globally is False
    assert con.applies_in_modes == ["MAINTENANCE"]
    assert con.related_modes == ["MAINTENANCE"]


def test_requirement_derived_mode_scoped_constraint(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Modes

- CALIBRATION: low speed

## Signals

- joint_speed: sensor, rad/s, bounds=[0, 2.5]

## Requirements

- REQ-001: Joint speed must remain <= 1.2 rad/s in CALIBRATION mode.
"""))
    ir = extract_ir_from_spec(spec)
    req_constraints = [c for c in ir.constraints if c.id.startswith("REQC-REQ-001")]
    assert len(req_constraints) == 1
    con = req_constraints[0]
    assert con.scope_type == ConstraintScopeType.MODE
    assert con.applies_in_modes == ["CALIBRATION"]
    assert con.related_signals == ["joint_speed"]
    assert con.operator == "<="
    assert con.numeric_value == 1.2


def test_requirement_linkage_prefers_timing_constraints(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- mode_request: internal, bool, bounds=[0, 1]

## States

- StModeA: source state
- StModeB: target state

## Requirements

- REQ-001: Transition StModeA -> StModeB shall complete within 100 ms of mode_request activation.

## Safety Constraints

- CON-001: mode_request <= 1

## Timing Constraints

- TC-001: StModeA -> StModeB within 100 ms of mode_request activation
"""))
    ir = extract_ir_from_spec(spec)

    req = ir.requirements[0]
    assert RequirementLinkClass.TIMING in req.requirement_classes
    assert req.parsed_constraints == ["TC-001"]
    assert "matching timing limit 100 ms" in req.linkage_reasons["TC-001"]
    assert "CON-001" not in req.parsed_constraints


def test_requirement_linkage_prefers_matching_mode_constraints_after_model_merge(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Modes

- MODE_A: first mode
- MODE_B: second mode

## Signals

- mode_request: internal, bool, bounds=[0, 1]

## Requirements

- REQ-001: mode_request must remain <= 1 in MODE_A mode.

## Safety Constraints

- CON-001: mode_request <= 1 when mode = MODE_A
- CON-002: mode_request <= 1 when mode = MODE_B
"""))
    ir = extract_ir_from_spec(spec)

    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "parameters:\n"
        "  max_mode_request: 1\n"
        "mode_constraints:\n"
        "  - id: MCON-001\n"
        "    mode: MODE_A\n"
        "    signal: mode_request\n"
        "    operator: <=\n"
        "    value: 1\n"
        "  - id: MCON-002\n"
        "    mode: MODE_B\n"
        "    signal: mode_request\n"
        "    operator: <=\n"
        "    value: 1\n"
    )
    merge_model_into_ir(ir, load_model(model_path))

    req = ir.requirements[0]
    assert RequirementLinkClass.MODE_SCOPED in req.requirement_classes
    assert set(req.parsed_constraints) == {"CON-001", "MCON-001", "REQC-REQ-001-01"}
    assert "CON-002" not in req.parsed_constraints
    assert "MCON-002" not in req.parsed_constraints
    assert "PARAM-MAX_MODE_REQUEST" not in req.parsed_constraints


def test_requirement_linkage_signal_threshold_excludes_unrelated_constraints(tmp_path):
    spec = load_spec(_write_spec(tmp_path, """
## Signals

- pressure_bar: sensor, bar, bounds=[0, 5]
- temperature_c: sensor, C, bounds=[0, 200]

## Requirements

- REQ-001: pressure_bar must remain <= 2.0 bar.

## Safety Constraints

- CON-001: pressure_bar <= 2.0 bar
- CON-002: temperature_c <= 80 C
"""))
    ir = extract_ir_from_spec(spec)

    req = ir.requirements[0]
    assert RequirementLinkClass.SIGNAL_BOUND in req.requirement_classes
    assert set(req.parsed_constraints) == {"CON-001", "REQC-REQ-001-01"}
    assert "CON-002" not in req.parsed_constraints


def test_smacc2_requirement_linkage_is_narrower_after_model_merge(tmp_path):
    root = Path(__file__).parent.parent
    spec = load_spec(root / "examples" / "smacc2_atomic_mode_states" / "spec.md")
    ir = extract_ir_from_spec(spec)
    merge_model_into_ir(ir, load_model(root / "examples" / "smacc2_atomic_mode_states" / "model.yaml"))

    req_by_id = {req.id: req for req in ir.requirements}

    req_mode_a = req_by_id["REQ-001"]
    assert {"CON-001", "MCON-001", "REQC-REQ-001-01"} <= set(req_mode_a.parsed_constraints)
    assert "CON-002" not in req_mode_a.parsed_constraints
    assert "FC-001" not in req_mode_a.parsed_constraints
    assert "MCON-002" not in req_mode_a.parsed_constraints
    assert "TC-001" not in req_mode_a.parsed_constraints
    assert "REQC-REQ-002-01" not in req_mode_a.parsed_constraints

    req_timing = req_by_id["REQ-003"]
    assert RequirementLinkClass.TIMING in req_timing.requirement_classes
    assert {"TC-001", "PARAM-MODE_SWITCH_RESPONSE_MS"} <= set(req_timing.parsed_constraints)
    assert "CON-001" not in req_timing.parsed_constraints
    assert "REQC-REQ-001-01" not in req_timing.parsed_constraints


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


def test_model_mode_constraints_merge(tmp_path):
    from eal.extraction import merge_model_into_ir
    from eal.ingestion import load_model

    spec = load_spec(_write_spec(tmp_path, """
## Modes

- CALIBRATION: low speed mode

## Signals

- joint_speed: sensor, rad/s, bounds=[0, 2.5]
"""))
    ir = extract_ir_from_spec(spec)

    model_path = tmp_path / "model.yaml"
    model_path.write_text(
        "mode_constraints:\n"
        "  - id: MCON-001\n"
        "    mode: CALIBRATION\n"
        "    signal: joint_speed\n"
        "    operator: <=\n"
        "    value: 1.2\n"
    )
    model = load_model(model_path)
    merge_model_into_ir(ir, model)

    con = next(c for c in ir.constraints if c.id == "MCON-001")
    assert con.scope_type == ConstraintScopeType.MODE
    assert con.applies_globally is False
    assert con.applies_in_modes == ["CALIBRATION"]
    assert con.related_signals == ["joint_speed"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_spec(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "spec.md"
    p.write_text(content)
    return p
