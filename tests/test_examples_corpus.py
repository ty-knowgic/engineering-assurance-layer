"""Role-based example corpus regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eal.cli import app

runner = CliRunner()
ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"


def _run_review(
    tmp_path: Path,
    *,
    spec: Path,
    model: Path,
    code: list[Path] | None = None,
    fail_on: str | None = None,
):
    out_dir = tmp_path / spec.parent.name
    args = [
        "review",
        "--spec",
        str(spec),
        "--model",
        str(model),
        "--out",
        str(out_dir),
    ]
    for code_path in code or []:
        args.extend(["--code", str(code_path)])
    if fail_on:
        args.extend(["--fail-on-severity", fail_on])

    result = runner.invoke(app, args)
    findings = json.loads((out_dir / "findings.json").read_text())
    metadata = json.loads((out_dir / "run_metadata.json").read_text())
    categories = {f["category"] for f in findings["findings"]}
    return result, categories, metadata


def test_examples_manifest_references_existing_files():
    manifest_path = EXAMPLES / "manifest.json"
    data = json.loads(manifest_path.read_text())

    assert "examples" in data
    assert isinstance(data["examples"], list)
    assert data["examples"], "examples manifest must not be empty"

    for entry in data["examples"]:
        assert (ROOT / entry["spec"]).exists()
        assert (ROOT / entry["model"]).exists()
        for code_file in entry.get("code", []):
            assert (ROOT / code_file).exists()


def test_robotics_arm_is_intentionally_failing_multi_issue(tmp_path):
    result, categories, _ = _run_review(
        tmp_path,
        spec=EXAMPLES / "robotics_arm" / "spec.md",
        model=EXAMPLES / "robotics_arm" / "model.yaml",
        code=[EXAMPLES / "robotics_arm" / "controller.py"],
    )
    assert result.exit_code == 0, result.output
    assert "TRANSITION_GAP" in categories
    assert "UNDEFINED_REFERENCE" in categories
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories


def test_mode_scope_demo_reports_mode_local_conflict_not_global(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "mode_scope_demo" / "spec.md",
        model=EXAMPLES / "mode_scope_demo" / "model.yaml",
        fail_on="CRITICAL",
    )
    assert result.exit_code == 2, result.output
    assert "UNSAT_IN_MODE" in categories or "MODE_SCOPED_CONFLICT" in categories
    assert "GLOBAL_CONSTRAINT_CONFLICT" not in categories
    assert metadata["gate"]["failed"] is True


def test_code_mismatch_demo_emits_code_derived_findings(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "code_mismatch_demo" / "spec.md",
        model=EXAMPLES / "code_mismatch_demo" / "model.yaml",
        code=[EXAMPLES / "code_mismatch_demo" / "controller.py"],
        fail_on="HIGH",
    )
    assert result.exit_code == 2, result.output
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories
    assert metadata["gate"]["failed"] is True


def test_boundary_clean_avoids_known_noisy_code_findings(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "boundary_clean" / "spec.md",
        model=EXAMPLES / "boundary_clean" / "model.yaml",
        code=[EXAMPLES / "boundary_clean" / "controller.py"],
        fail_on="HIGH",
    )
    assert result.exit_code == 0, result.output
    assert "CODE_BOUND_MISMATCH" not in categories
    assert "CODE_TIMING_MISMATCH" not in categories
    assert "CODE_UNMODELED_PARAMETER" not in categories
    assert metadata["gate"]["failed"] is False


def test_ci_smoke_still_passes_high_gate(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "ci_smoke" / "spec.md",
        model=EXAMPLES / "ci_smoke" / "model.yaml",
        fail_on="HIGH",
    )
    assert result.exit_code == 0, result.output
    assert categories == set()
    assert metadata["gate"]["failed"] is False


def test_complex_control_system_validation_testbed(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "complex_control_system" / "spec.md",
        model=EXAMPLES / "complex_control_system" / "model.yaml",
        code=[EXAMPLES / "complex_control_system" / "controller.py"],
        fail_on="HIGH",
    )
    assert result.exit_code == 2, result.output
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories
    assert "UNSAT_IN_MODE" in categories or "MODE_SCOPED_CONFLICT" in categories
    assert metadata["gate"]["failed"] is True


def test_system_interlock_demo_validation_testbed(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "system_interlock_demo" / "spec.md",
        model=EXAMPLES / "system_interlock_demo" / "model.yaml",
        code=[EXAMPLES / "system_interlock_demo" / "controller.py"],
        fail_on="HIGH",
    )
    assert result.exit_code == 2, result.output
    assert "FORBIDDEN_UNCHECKED" in categories
    assert "TRANSITION_GAP" in categories
    assert "UNDEFINED_REFERENCE" in categories
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories
    assert metadata["gate"]["failed"] is True


def test_subsystem_interface_review_validation_testbed(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "subsystem_interface_review" / "spec.md",
        model=EXAMPLES / "subsystem_interface_review" / "model.yaml",
        code=[EXAMPLES / "subsystem_interface_review" / "controller.py"],
        fail_on="HIGH",
    )
    assert result.exit_code == 2, result.output
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories
    assert "UNDEFINED_REFERENCE" in categories
    assert "FORBIDDEN_UNCHECKED" in categories
    assert metadata["gate"]["failed"] is True


def test_smacc2_atomic_mode_states_validation_slice_clean_baseline(tmp_path):
    result, categories, metadata = _run_review(
        tmp_path,
        spec=EXAMPLES / "smacc2_atomic_mode_states" / "spec.md",
        model=EXAMPLES / "smacc2_atomic_mode_states" / "model.yaml",
        fail_on="HIGH",
    )
    assert result.exit_code == 0, result.output
    assert "TRANSITION_GAP" not in categories
    assert "UNDEFINED_REFERENCE" not in categories
    assert "TIMING_GAP" not in categories
    assert "FORBIDDEN_UNCHECKED" not in categories
    assert "GLOBAL_CONSTRAINT_CONFLICT" not in categories
    assert "MODE_SCOPED_CONFLICT" not in categories
    assert "UNSAT_IN_MODE" not in categories
    assert metadata["gate"]["failed"] is False
    assert metadata["results"]["highest_severity_found"] in {"NONE", "LOW", "MEDIUM"}
