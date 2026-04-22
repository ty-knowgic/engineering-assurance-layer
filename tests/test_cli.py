"""End-to-end CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from eal.cli import app

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples"


def test_review_robotics_arm(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--code", str(EXAMPLES / "robotics_arm" / "controller.py"),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0, result.output
    out = tmp_path / "out"
    # All required artifacts must exist
    assert (out / "review_summary.md").exists()
    assert (out / "constraint_violations.md").exists()
    assert (out / "missing_assumptions.md").exists()
    assert (out / "counterexamples.json").exists()
    assert (out / "review_evidence.json").exists()
    assert (out / "ir_snapshot.json").exists()
    assert (out / "findings.json").exists()
    assert (out / "report.html").exists()
    assert (out / "run_metadata.json").exists()


def test_review_mobile_robot(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "mobile_robot" / "spec.md"),
        "--model", str(EXAMPLES / "mobile_robot" / "model.yaml"),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0, result.output
    out = tmp_path / "out"
    assert (out / "findings.json").exists()


def test_review_spec_only(tmp_path, minimal_spec):
    result = runner.invoke(app, [
        "review",
        "--spec", str(minimal_spec),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "findings.json").exists()


def test_review_findings_are_valid_json(tmp_path):
    import json
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "out" / "findings.json").read_text())
    assert "findings" in data
    assert "finding_count" in data


def test_review_robotics_arm_has_findings(tmp_path):
    """Robotics arm example must generate at least one finding — it has intentional issues."""
    import json
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "out" / "findings.json").read_text())
    assert data["finding_count"] > 0


def test_review_counterexamples_json_structure(tmp_path):
    import json
    runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(tmp_path / "out"),
    ])
    data = json.loads((tmp_path / "out" / "counterexamples.json").read_text())
    assert "counterexample_count" in data
    assert "counterexamples" in data


def test_review_missing_spec_errors():
    result = runner.invoke(app, [
        "review",
        "--spec", "/nonexistent/path/spec.md",
    ])
    assert result.exit_code != 0


def test_run_metadata_has_version(tmp_path):
    import json
    runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--out", str(tmp_path / "out"),
    ])
    data = json.loads((tmp_path / "out" / "run_metadata.json").read_text())
    assert "eal_version" in data
    assert "run_id" in data
    assert data["run_id"].startswith("eal-")
