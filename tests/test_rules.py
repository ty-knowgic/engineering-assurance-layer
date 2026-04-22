"""Tests for the deterministic rules engine."""

from __future__ import annotations

from eal.findings.schema import FindingCategory, FindingSeverity
from eal.ir.schema import (
    Assumption, AssumptionType, Bounds, Constraint, ConstraintType,
    CodeConstant,
    CodeSymbolClass,
    IRSnapshot,
    Mode,
    Requirement,
    Signal,
    SignalKind,
    SourceRef,
    State,
    Transition,
)
from eal.rules.engine import (
    RuleStrictness,
    available_rule_metadata,
    run_rules,
    rule_code_bound_mismatch,
    rule_code_timing_mismatch,
    rule_code_unmodeled_parameter,
    rule_contradictory_bounds,
    rule_forbidden_condition_unguarded,
    rule_missing_failsafe_assumption,
    rule_missing_signal_bounds,
    rule_timing_req_no_parameter,
    rule_undefined_signal_in_req,
    rule_undefined_state_in_transition,
)


def _ir(**kwargs) -> IRSnapshot:
    return IRSnapshot(spec_file="test.md", **kwargs)


# ── Missing bounds ────────────────────────────────────────────────────────────

def test_missing_upper_bound_actuator():
    ir = _ir(signals=[Signal(name="torque", kind=SignalKind.ACTUATOR)])
    findings = rule_missing_signal_bounds(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.MISSING_BOUND
    assert "torque" in findings[0].title


def test_bounded_signal_no_finding():
    ir = _ir(signals=[Signal(name="speed", kind=SignalKind.SENSOR,
                             bounds=Bounds(min=0, max=10))])
    findings = rule_missing_signal_bounds(ir)
    assert findings == []


def test_internal_signal_not_flagged():
    # Internal signals don't need bounds
    ir = _ir(signals=[Signal(name="mode_flag", kind=SignalKind.INTERNAL)])
    findings = rule_missing_signal_bounds(ir)
    assert findings == []


# ── Undefined signal in requirement ──────────────────────────────────────────

def test_undefined_signal_detected():
    ir = _ir(
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR)],
        requirements=[Requirement(id="REQ-001", text="undefined_sensor must stay below 5")],
    )
    findings = rule_undefined_signal_in_req(ir)
    assert any("undefined_sensor" in f.title for f in findings)


def test_known_signal_no_finding():
    ir = _ir(
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR)],
        requirements=[Requirement(id="REQ-001", text="joint_speed must remain <= 1.2 rad/s")],
    )
    findings = rule_undefined_signal_in_req(ir)
    assert findings == []


# ── Undefined state in transition ─────────────────────────────────────────────

def test_undefined_state_transition():
    ir = _ir(
        states=[State(name="IDLE"), State(name="RUNNING")],
        transitions=[Transition(from_state="RUNNING", to_state="RECOVERY")],
    )
    findings = rule_undefined_state_in_transition(ir)
    assert len(findings) == 1
    assert "RECOVERY" in findings[0].title


def test_defined_states_no_finding():
    ir = _ir(
        states=[State(name="IDLE"), State(name="RUNNING")],
        transitions=[Transition(from_state="IDLE", to_state="RUNNING")],
    )
    findings = rule_undefined_state_in_transition(ir)
    assert findings == []


# ── Forbidden condition unguarded ─────────────────────────────────────────────

def test_forbidden_condition_no_guard():
    ir = _ir(
        constraints=[
            Constraint(
                id="FC-001",
                expression_text="gripper_force > 0 when human_detected = true",
                constraint_type=ConstraintType.FORBIDDEN,
                related_signals=["gripper_force", "human_detected"],
            )
        ],
        transitions=[],
        assumptions=[],
    )
    findings = rule_forbidden_condition_unguarded(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.FORBIDDEN_UNCHECKED


def test_forbidden_condition_with_guard():
    ir = _ir(
        constraints=[
            Constraint(
                id="FC-001",
                expression_text="gripper_force > 0 when human_detected = true",
                constraint_type=ConstraintType.FORBIDDEN,
                related_signals=["gripper_force", "human_detected"],
            )
        ],
        transitions=[
            Transition(from_state="A", to_state="B", guard_condition="human_detected = false")
        ],
        assumptions=[],
    )
    findings = rule_forbidden_condition_unguarded(ir)
    assert findings == []


# ── Timing requirement without parameter ──────────────────────────────────────

def test_timing_req_missing_param():
    ir = _ir(
        constraints=[
            Constraint(
                id="TC-001",
                expression_text="OPERATING -> SAFE_STOP within 100 ms",
                constraint_type=ConstraintType.TIMING,
            )
        ],
        assumptions=[],
    )
    findings = rule_timing_req_no_parameter(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.TIMING_GAP


def test_timing_req_with_asm_no_finding():
    ir = _ir(
        constraints=[
            Constraint(
                id="TC-001",
                expression_text="OPERATING -> SAFE_STOP within 100 ms",
                constraint_type=ConstraintType.TIMING,
            )
        ],
        assumptions=[
            Assumption(
                id="ASM-001",
                text="E-stop hardware response time is guaranteed to be < 50 ms by vendor.",
                assumption_type=AssumptionType.TIMING,
            )
        ],
    )
    findings = rule_timing_req_no_parameter(ir)
    assert findings == []


# ── Missing failsafe assumption ───────────────────────────────────────────────

def test_missing_failsafe_no_asm():
    ir = _ir(
        constraints=[
            Constraint(
                id="FC-001",
                expression_text="human_detected must cause stop",
                constraint_type=ConstraintType.FORBIDDEN,
                related_signals=["human_detected"],
            )
        ],
        assumptions=[],
    )
    findings = rule_missing_failsafe_assumption(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.MISSING_ASSUMPTION


# ── Contradictory bounds ──────────────────────────────────────────────────────

def test_contradictory_bound_detected():
    """Signal min=1.5 but constraint requires <= 1.2 → contradiction."""
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
    findings = rule_contradictory_bounds(ir)
    assert len(findings) == 1
    assert findings[0].severity == FindingSeverity.CRITICAL
    assert findings[0].counterexample is not None


def test_no_contradiction():
    ir = _ir(
        signals=[
            Signal(name="speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=5))
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
    findings = rule_contradictory_bounds(ir)
    assert findings == []


# ── Code/spec-model mismatch rules ───────────────────────────────────────────

def test_code_bound_mismatch_detected():
    ir = _ir(
        signals=[
            Signal(
                name="joint_speed",
                kind=SignalKind.SENSOR,
                bounds=Bounds(min=0, max=1.2),
                source_ref=SourceRef(file="spec.md", section="Signals"),
            )
        ],
        code_constants=[
            CodeConstant(
                evidence_id="CC-001",
                file="controller.py",
                line=3,
                symbol="MAX_JOINT_SPEED",
                normalized_name="joint_speed",
                value=1.5,
                snippet="MAX_JOINT_SPEED = 1.5",
                classification=CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
                classification_confidence=0.95,
            )
        ],
    )
    findings = rule_code_bound_mismatch(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.CODE_BOUND_MISMATCH
    assert findings[0].severity == FindingSeverity.HIGH
    assert "controller.py:3" in findings[0].source_refs


def test_code_timing_mismatch_detected():
    ir = _ir(
        requirements=[
            Requirement(
                id="REQ-003",
                text="Emergency stop shall transition system to SAFE_STOP within 100 ms.",
                source_ref=SourceRef(file="spec.md", section="Requirements"),
            )
        ],
        code_constants=[
            CodeConstant(
                evidence_id="CC-002",
                file="controller.py",
                line=4,
                symbol="ESTOP_RESPONSE_MS",
                normalized_name="estop_response_ms",
                value=150.0,
                snippet="ESTOP_RESPONSE_MS = 150",
                classification=CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
                classification_confidence=0.95,
            )
        ],
    )
    findings = rule_code_timing_mismatch(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.CODE_TIMING_MISMATCH
    assert findings[0].severity == FindingSeverity.HIGH


def test_code_unmodeled_parameter_detected():
    ir = _ir(
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=1.2))],
        code_constants=[
            CodeConstant(
                evidence_id="CC-003",
                file="controller.py",
                line=5,
                symbol="JOINT_SPEED_SOFT_LIMIT",
                normalized_name="joint_speed_soft",
                value=1.1,
                classification=CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
                classification_confidence=0.9,
            )
        ],
    )
    findings = rule_code_unmodeled_parameter(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.CODE_UNMODELED_PARAMETER
    assert findings[0].severity == FindingSeverity.MEDIUM


def test_code_unmodeled_parameter_avoids_unrelated_false_positive():
    ir = _ir(
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR)],
        code_constants=[
            CodeConstant(
                evidence_id="CC-004",
                file="controller.py",
                line=7,
                symbol="HTTP_PORT",
                normalized_name="http_port",
                value=8080.0,
                classification=CodeSymbolClass.GENERIC_NUMERIC_CONSTANT,
                classification_confidence=0.3,
            )
        ],
    )
    findings = rule_code_unmodeled_parameter(ir)
    assert findings == []


def test_timing_constant_does_not_claim_boolean_signal_match():
    ir = _ir(
        signals=[
            Signal(
                name="e_stop_active",
                kind=SignalKind.SENSOR,
                source_ref=SourceRef(file="spec.md", section="Signals"),
            )
        ],
        constraints=[
            Constraint(
                id="TC-001",
                expression_text="OPERATING -> SAFE_STOP within 100 ms of e_stop_active activation",
                constraint_type=ConstraintType.TIMING,
                related_signals=["e_stop_active"],
                source_ref=SourceRef(file="spec.md", section="Timing Constraints"),
            )
        ],
        code_constants=[
            CodeConstant(
                evidence_id="CC-005",
                file="controller.py",
                line=9,
                symbol="ESTOP_RESPONSE_MS",
                normalized_name="estop_response_ms",
                value=150.0,
                classification=CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
                classification_confidence=0.95,
            )
        ],
    )
    findings = rule_code_unmodeled_parameter(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.CODE_UNMODELED_PARAMETER
    assert "e_stop_active" not in findings[0].summary


def test_timing_mismatch_rejects_boolean_signal_name_matching():
    ir = _ir(
        signals=[Signal(name="e_stop_active", kind=SignalKind.SENSOR)],
        constraints=[
            Constraint(
                id="TC-001",
                expression_text="OPERATING -> SAFE_STOP within 100 ms of e_stop_active activation",
                constraint_type=ConstraintType.TIMING,
                related_signals=["e_stop_active"],
            )
        ],
        code_constants=[
            CodeConstant(
                evidence_id="CC-006",
                file="controller.py",
                line=10,
                symbol="ESTOP_RESPONSE_MS",
                normalized_name="estop_response_ms",
                value=150.0,
                classification=CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
                classification_confidence=0.95,
                snippet="ESTOP_RESPONSE_MS = 150",
            )
        ],
    )
    findings = rule_code_timing_mismatch(ir)
    assert len(findings) == 1
    assert findings[0].category == FindingCategory.CODE_TIMING_MISMATCH
    assert "global timing limit fallback" in findings[0].details


# ── Rule metadata and strictness ──────────────────────────────────────────────

def test_rule_metadata_contains_strictness_fields():
    catalog = available_rule_metadata()
    assert catalog

    code_unmodeled = next(m for m in catalog if m.rule_id == "CODE_UNMODELED_PARAMETER")
    assert code_unmodeled.confidence.value == "low"
    assert code_unmodeled.strictness_sensitivity.value == "heuristic"
    assert code_unmodeled.default_severity == FindingSeverity.MEDIUM


def test_relaxed_strictness_suppresses_heuristic_code_unmodeled_findings():
    ir = _ir(
        signals=[Signal(name="joint_speed", kind=SignalKind.SENSOR, bounds=Bounds(min=0, max=1.2))],
        code_constants=[
            CodeConstant(
                evidence_id="CC-007",
                file="controller.py",
                line=12,
                symbol="JOINT_SPEED_SOFT_LIMIT",
                normalized_name="joint_speed_soft",
                value=1.1,
                classification=CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
                classification_confidence=0.9,
            )
        ],
    )
    strict_findings = run_rules(ir, strictness=RuleStrictness.STRICT)
    relaxed_findings = run_rules(ir, strictness=RuleStrictness.RELAXED)

    assert any(f.category == FindingCategory.CODE_UNMODELED_PARAMETER for f in strict_findings)
    assert all(f.category != FindingCategory.CODE_UNMODELED_PARAMETER for f in relaxed_findings)


def test_relaxed_strictness_does_not_suppress_high_confidence_mismatch():
    ir = _ir(
        signals=[
            Signal(
                name="joint_speed",
                kind=SignalKind.SENSOR,
                bounds=Bounds(min=0, max=1.2),
            )
        ],
        code_constants=[
            CodeConstant(
                evidence_id="CC-008",
                file="controller.py",
                line=13,
                symbol="MAX_JOINT_SPEED",
                normalized_name="joint_speed",
                value=1.5,
                classification=CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
                classification_confidence=0.95,
            )
        ],
    )
    relaxed_findings = run_rules(ir, strictness=RuleStrictness.RELAXED)
    categories = {f.category for f in relaxed_findings}
    assert FindingCategory.CODE_BOUND_MISMATCH in categories


# ── Full run ──────────────────────────────────────────────────────────────────

def test_run_rules_robotics_arm(robotics_arm_spec, robotics_arm_model):
    from eal.ingestion import load_spec, load_model
    from eal.extraction import extract_ir_from_spec, merge_model_into_ir
    spec = load_spec(robotics_arm_spec)
    model = load_model(robotics_arm_model)
    ir = extract_ir_from_spec(spec)
    merge_model_into_ir(ir, model)
    findings = run_rules(ir)
    # Robotics arm example has intentional issues
    assert len(findings) > 0
    categories = {f.category for f in findings}
    # Should detect at least: undefined reference, transition gap, timing gap
    assert FindingCategory.TRANSITION_GAP in categories or FindingCategory.TIMING_GAP in categories


def test_run_rules_returns_list_on_empty_ir():
    ir = IRSnapshot(spec_file="empty.md")
    findings = run_rules(ir)
    assert isinstance(findings, list)
