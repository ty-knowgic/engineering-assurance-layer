"""
Unsat core tests.

Two regressions are locked down here.

The first is a naming one. `counterexamples.json` used to file UNSAT results
under `counterexamples` while reporting only the list of constraint IDs that had
been asserted. An unsatisfiable system has no model, so there is nothing to
report as a counterexample, and "everything we asserted" is not an explanation.

The second is a correctness one, found while fixing the first. The core was
initially built with `assert_and_track`, which asserts each fact *hard*.
Omitting a tracker from a later `check()` therefore did not retract anything,
every subset stayed unsat, and deletion-based minimization shrank the core to
the empty set — which the tool then reported as "minimal: true". A core of size
zero claims the empty set is contradictory. `test_core_is_never_empty` exists
because that shipped for the length of one test run.

Minimality is verified here by brute force over proper subsets, independently of
the minimizer that produced it. A minimizer that validates its own output
validates nothing.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eal.cli import app
from eal.ir.schema import (
    Bounds,
    Constraint,
    ConstraintScopeType,
    ConstraintType,
    IRSnapshot,
    Mode,
    Signal,
    SignalKind,
)
from eal.solver.z3_checker import (
    _build_solver,
    _minimal_unsat_core,
    _numeric_constraints,
    run_z3_checks,
)

z3 = pytest.importorskip("z3", reason="z3-solver not installed")

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples"


def _contradictory_ir() -> IRSnapshot:
    """speed is bounded [1.5, 3.0] but three constraints push it down."""
    return IRSnapshot(
        spec_file="synthetic",
        signals=[
            Signal(name="speed", kind=SignalKind.SENSOR,
                   bounds=Bounds(min=1.5, max=3.0, unit="m/s")),
        ],
        constraints=[
            Constraint(
                id="CON-001", expression_text="speed <= 1.0",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.GLOBAL, applies_globally=True,
                related_signals=["speed"], numeric_value=1.0, operator="<=",
            ),
            # Redundant with CON-001 and strictly weaker: must not reach the core.
            Constraint(
                id="CON-002", expression_text="speed <= 2.0",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.GLOBAL, applies_globally=True,
                related_signals=["speed"], numeric_value=2.0, operator="<=",
            ),
            Constraint(
                id="CON-003", expression_text="speed >= 0.0",
                constraint_type=ConstraintType.INVARIANT,
                scope_type=ConstraintScopeType.GLOBAL, applies_globally=True,
                related_signals=["speed"], numeric_value=0.0, operator=">=",
            ),
        ],
    )


def _core_for(ir: IRSnapshot):
    constraints = _numeric_constraints(ir)
    bundle = _build_solver(ir, constraints, with_mode_logic=False)
    assert bundle.check() == z3.unsat, "fixture is meant to be unsatisfiable"
    return bundle, _minimal_unsat_core(bundle)


def _subset_is_unsat(bundle, labels) -> bool:
    return bundle.solver.check(*[bundle.selectors[n] for n in labels]) == z3.unsat


# ── Correctness of the core itself ────────────────────────────────────────────

def test_core_is_never_empty():
    """The empty set cannot be unsat. A zero-size core is always a bug."""
    _, core = _core_for(_contradictory_ir())
    assert len(core) >= 1


def test_core_is_actually_unsat():
    """The reported facts must be contradictory on their own."""
    bundle, core = _core_for(_contradictory_ir())
    assert _subset_is_unsat(bundle, core)


def test_core_is_irreducible_by_brute_force():
    """No proper subset may be unsat — checked exhaustively, not via the minimizer."""
    bundle, core = _core_for(_contradictory_ir())
    for size in range(len(core)):
        for subset in itertools.combinations(core, size):
            assert not _subset_is_unsat(bundle, list(subset)), (
                f"subset {subset} is already unsat, so the core is not minimal"
            )


def test_redundant_weaker_constraint_is_excluded():
    """`speed <= 2.0` is implied by `speed <= 1.0`; only the binding one belongs."""
    bundle, core = _core_for(_contradictory_ir())
    ids = {bundle.label_constraints.get(n) for n in core}
    assert "CON-001" in ids
    assert "CON-002" not in ids


def test_core_names_the_signal_bound_not_only_constraints():
    """Half of this contradiction is the declared bound; a core hiding it is useless."""
    bundle, core = _core_for(_contradictory_ir())
    facts = [bundle.labels[n] for n in core]
    assert any("declared bound" in f for f in facts), facts


def test_core_is_deterministic():
    first = _core_for(_contradictory_ir())[1]
    second = _core_for(_contradictory_ir())[1]
    assert first == second


def test_satisfiable_system_produces_no_findings():
    ir = _contradictory_ir()
    ir.constraints = [c for c in ir.constraints if c.id != "CON-001"]
    assert run_z3_checks(ir) == []


# ── Mode-scoped cores ─────────────────────────────────────────────────────────

def test_mode_assumption_is_not_reported_as_part_of_the_core():
    """"Mode X is active" frames the question; it is not a fact under suspicion."""
    ir = _contradictory_ir()
    ir.modes = [Mode(name="FAST"), Mode(name="SLOW")]
    ir.constraints[0].scope_type = ConstraintScopeType.MODE
    ir.constraints[0].applies_globally = False
    ir.constraints[0].applies_in_modes = ["SLOW"]

    findings = [f for f in run_z3_checks(ir) if f.counterexample]
    assert findings
    for f in findings:
        for item in f.counterexample["core"]:
            assert not item["label"].startswith("mode_")


# ── Real example ──────────────────────────────────────────────────────────────

def test_robotics_arm_core_is_smaller_than_the_asserted_set():
    """
    The previous output listed CON-002 and REQC-REQ-001-01 as "conflicting".
    REQC-REQ-001-01 is redundant, and the real other half — the declared lower
    bound on joint_speed — was not mentioned at all.
    """
    from eal.extraction import extract_ir_from_spec, merge_model_into_ir
    from eal.ingestion import load_model, load_spec

    ir = extract_ir_from_spec(load_spec(EXAMPLES / "robotics_arm" / "spec.md"))
    merge_model_into_ir(ir, load_model(EXAMPLES / "robotics_arm" / "model.yaml"))

    findings = [f for f in run_z3_checks(ir) if f.counterexample]
    assert findings
    for f in findings:
        evidence = f.counterexample
        if evidence["kind"] != "unsat_core":
            continue
        assert evidence["core_size"] >= 1
        assert evidence["minimal"] is True
        assert "REQC-REQ-001-01" not in evidence["core_constraint_ids"]
        facts = [c["fact"] for c in evidence["core"]]
        assert any("declared bound joint_speed" in f for f in facts), facts


# ── Artifact honesty ──────────────────────────────────────────────────────────

def test_artifact_does_not_file_cores_as_counterexamples(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "out" / "counterexamples.json").read_text())

    assert data["counterexample_count"] == 0, "no witness model exists for an UNSAT system"
    assert data["unsat_core_count"] >= 1
    assert data["status"] == "unsat_cores_only"
    assert data["counterexamples"] == []
    assert "not interchangeable" in data["notes"]

    for entry in data["unsat_cores"]:
        evidence = entry["evidence"]
        assert evidence["kind"] == "unsat_core"
        assert evidence["z3_result"] == "unsat"
        assert evidence["core_size"] == len(evidence["core"])
        assert evidence["core_size"] >= 1


def test_structural_conflicts_are_labelled_distinctly():
    """
    A required+forbidden transition is found by direct comparison, not by the
    solver, so it must not be labelled as a core or a witness.

    Built at IR level because this rule cannot currently be reached through the
    CLI at all — see test_required_and_forbidden_rule_is_unreachable_via_input.
    """
    from eal.ir.schema import Transition

    ir = IRSnapshot(
        spec_file="synthetic",
        transitions=[
            Transition(from_state="A", to_state="B", forbidden=False),
            Transition(from_state="A", to_state="B", forbidden=True),
        ],
    )
    findings = [f for f in run_z3_checks(ir) if f.counterexample]
    assert findings
    assert {f.counterexample["kind"] for f in findings} == {"structural_conflict"}


def test_required_and_forbidden_rule_is_unreachable_via_input(tmp_path):
    """
    Documents a real gap rather than asserting desired behaviour.

    README advertises an `UNREACHABLE_STATE` check for a transition that is both
    required and forbidden. No supported input can produce that IR: the spec
    extractor never sets `forbidden` on a transition, and the model merger
    dedups transitions by (from, to), so a model entry cannot flip a pair the
    spec already declared. The rule only fires on hand-constructed IR.

    If the rule is ever made reachable, this test will fail — which is the
    signal to delete it.
    """
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## States\n- A: first\n- B: second\n\n"
        "## Transitions\n- A -> B: guard=go\n"
    )
    model = tmp_path / "model.yaml"
    model.write_text(
        "transitions:\n"
        "  - from: A\n    to: B\n    guard: \"go\"\n    forbidden: true\n"
    )
    runner.invoke(app, [
        "review", "--spec", str(spec), "--model", str(model),
        "--out", str(tmp_path / "out"),
    ])
    ir = json.loads((tmp_path / "out" / "ir_snapshot.json").read_text())
    pairs = [(t["from_state"], t["to_state"], t["forbidden"]) for t in ir["transitions"]]
    assert pairs == [("A", "B", False)], (
        "the forbidden duplicate was merged in after all; the rule may now be "
        "reachable and this test should be replaced by a positive one"
    )
    findings = json.loads((tmp_path / "out" / "findings.json").read_text())
    assert not [
        f for f in findings["findings"] if f["category"] == "UNREACHABLE_STATE"
    ]
