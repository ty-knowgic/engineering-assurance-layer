"""End-to-end CLI smoke tests."""

from __future__ import annotations

from pathlib import Path

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
    assert (out / "results.sarif").exists()
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


def test_review_ci_smoke_passes_high_gate(tmp_path):
    import json

    out_dir = tmp_path / "out_ci_smoke"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "ci_smoke" / "spec.md"),
        "--model", str(EXAMPLES / "ci_smoke" / "model.yaml"),
        "--fail-on-severity", "HIGH",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output

    metadata = json.loads((out_dir / "run_metadata.json").read_text())
    assert metadata["gate"]["fail_on_severity"] == "HIGH"
    assert metadata["gate"]["failed"] is False
    assert metadata["results"]["highest_severity_found"] in {"NONE", "LOW", "MEDIUM"}
    assert (out_dir / "results.sarif").exists()


def test_review_spec_only(tmp_path, minimal_spec):
    result = runner.invoke(app, [
        "review",
        "--spec", str(minimal_spec),
        "--out", str(tmp_path / "out"),
    ])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "findings.json").exists()
    assert (tmp_path / "out" / "results.sarif").exists()


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

    sarif = json.loads((tmp_path / "out" / "results.sarif").read_text())
    assert sarif["version"] == "2.1.0"
    assert "runs" in sarif
    assert "results" in sarif["runs"][0]


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
    assert data["artifacts"]["sarif"]["generated"] is True
    assert data["artifacts"]["sarif"]["file"] == "results.sarif"


def test_review_code_input_changes_findings(tmp_path):
    import json

    out_without = tmp_path / "out_without_code"
    result_without = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(out_without),
    ])
    assert result_without.exit_code == 0
    findings_without = json.loads((out_without / "findings.json").read_text())["findings"]
    categories_without = {f["category"] for f in findings_without}

    out_with = tmp_path / "out_with_code"
    result_with = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--code", str(EXAMPLES / "robotics_arm" / "controller.py"),
        "--out", str(out_with),
    ])
    assert result_with.exit_code == 0
    findings_with = json.loads((out_with / "findings.json").read_text())["findings"]
    categories_with = {f["category"] for f in findings_with}

    assert "CODE_BOUND_MISMATCH" in categories_with
    assert "CODE_TIMING_MISMATCH" in categories_with
    assert "CODE_BOUND_MISMATCH" not in categories_without
    assert "CODE_TIMING_MISMATCH" not in categories_without


def test_review_mode_scoped_solver_behavior(tmp_path):
    import json

    out_dir = tmp_path / "out_mode_scope"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output

    findings = json.loads((out_dir / "findings.json").read_text())["findings"]
    categories = {f["category"] for f in findings}
    assert "UNSAT_IN_MODE" in categories or "MODE_SCOPED_CONFLICT" in categories
    assert "GLOBAL_CONSTRAINT_CONFLICT" not in categories


def test_review_default_gate_behavior_does_not_fail_process(tmp_path):
    import json

    out_dir = tmp_path / "out_default_gate"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output

    data = json.loads((out_dir / "run_metadata.json").read_text())
    assert data["gate"]["fail_on_severity"] == "NONE"
    assert data["gate"]["failed"] is False
    assert data["strictness"]["level"] == "balanced"
    assert data["results"]["highest_severity_found"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"}


def test_review_fail_on_severity_critical(tmp_path):
    import json

    out_dir = tmp_path / "out_fail_critical"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--fail-on-severity", "CRITICAL",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 2, result.output

    metadata = json.loads((out_dir / "run_metadata.json").read_text())
    assert metadata["gate"]["failed"] is True
    assert metadata["gate"]["exit_reason"] == "SEVERITY_THRESHOLD_EXCEEDED"
    assert metadata["gate"]["fail_on_severity"] == "CRITICAL"
    assert (out_dir / "findings.json").exists()
    assert (out_dir / "review_summary.md").exists()


def test_review_fail_on_severity_high(tmp_path):
    out_dir = tmp_path / "out_fail_high"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--fail-on-severity", "HIGH",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 2, result.output
    assert (out_dir / "run_metadata.json").exists()
    assert (out_dir / "counterexamples.json").exists()
    assert (out_dir / "results.sarif").exists()


def test_review_min_severity_filters_presentation_only(tmp_path):
    import json

    out_dir = tmp_path / "out_min_sev"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--min-severity", "CRITICAL",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output
    assert "Review Findings (>= CRITICAL)" in result.output

    summary = (out_dir / "review_summary.md").read_text()
    assert "Presentation minimum severity" in summary
    assert "`CRITICAL`" in summary

    findings = json.loads((out_dir / "findings.json").read_text())
    severities = {f["severity"] for f in findings["findings"]}
    assert "HIGH" in severities
    assert "MEDIUM" in severities


def test_review_relaxed_strictness_suppresses_heuristic_gate_findings(tmp_path):
    import json

    spec_path = tmp_path / "spec.md"
    model_path = tmp_path / "model.yaml"
    code_path = tmp_path / "controller.py"

    spec_path.write_text(
        "\n".join(
            [
                "## Signals",
                "- joint_speed: sensor, rad/s, bounds=[0, 1.2]",
                "",
                "## Requirements",
                "- REQ-001: joint_speed must remain <= 1.2 rad/s.",
            ]
        ),
        encoding="utf-8",
    )
    model_path.write_text(
        "\n".join(
            [
                "signals:",
                "  - name: joint_speed",
                "    kind: sensor",
                "    unit: rad/s",
                "    bounds:",
                "      min: 0",
                "      max: 1.2",
            ]
        ),
        encoding="utf-8",
    )
    code_path.write_text("JOINT_SPEED_SOFT_LIMIT = 1.1\n", encoding="utf-8")

    out_balanced = tmp_path / "out_balanced"
    balanced = runner.invoke(app, [
        "review",
        "--spec", str(spec_path),
        "--model", str(model_path),
        "--code", str(code_path),
        "--fail-on-severity", "MEDIUM",
        "--strictness", "balanced",
        "--out", str(out_balanced),
    ])
    assert balanced.exit_code == 2, balanced.output
    balanced_findings = json.loads((out_balanced / "findings.json").read_text())["findings"]
    assert any(f["category"] == "CODE_UNMODELED_PARAMETER" for f in balanced_findings)

    out_relaxed = tmp_path / "out_relaxed"
    relaxed = runner.invoke(app, [
        "review",
        "--spec", str(spec_path),
        "--model", str(model_path),
        "--code", str(code_path),
        "--fail-on-severity", "MEDIUM",
        "--strictness", "relaxed",
        "--out", str(out_relaxed),
    ])
    assert relaxed.exit_code == 0, relaxed.output
    relaxed_findings = json.loads((out_relaxed / "findings.json").read_text())["findings"]
    assert all(f["category"] != "CODE_UNMODELED_PARAMETER" for f in relaxed_findings)

    relaxed_meta = json.loads((out_relaxed / "run_metadata.json").read_text())
    assert relaxed_meta["strictness"]["level"] == "relaxed"
    assert relaxed_meta["strictness"]["suppressed_finding_count"] >= 1


def test_review_strictness_strict_retains_heuristic_findings(tmp_path):
    import json

    out_dir = tmp_path / "out_strict_rules"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--code", str(EXAMPLES / "robotics_arm" / "controller.py"),
        "--strictness", "strict",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output

    findings = json.loads((out_dir / "findings.json").read_text())["findings"]
    categories = {f["category"] for f in findings}
    assert "CODE_UNMODELED_PARAMETER" in categories


def test_review_relaxed_does_not_hide_high_confidence_mismatch(tmp_path):
    import json

    out_dir = tmp_path / "out_relaxed_code_mismatch"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "code_mismatch_demo" / "spec.md"),
        "--model", str(EXAMPLES / "code_mismatch_demo" / "model.yaml"),
        "--code", str(EXAMPLES / "code_mismatch_demo" / "controller.py"),
        "--strictness", "relaxed",
        "--fail-on-severity", "HIGH",
        "--out", str(out_dir),
    ])
    assert result.exit_code == 2, result.output

    findings = json.loads((out_dir / "findings.json").read_text())["findings"]
    categories = {f["category"] for f in findings}
    assert "CODE_BOUND_MISMATCH" in categories
    assert "CODE_TIMING_MISMATCH" in categories


def test_review_invalid_fail_on_severity_rejected(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--fail-on-severity", "SEVERE",
        "--out", str(tmp_path / "out_invalid"),
    ])
    assert result.exit_code != 0
    assert "Invalid value for '--fail-on-severity'" in result.output


def test_review_invalid_min_severity_rejected(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--min-severity", "NONE",
        "--out", str(tmp_path / "out_invalid_min"),
    ])
    assert result.exit_code != 0
    assert "Invalid value for '--min-severity'" in result.output


def test_review_invalid_strictness_rejected(tmp_path):
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--strictness", "custom",
        "--out", str(tmp_path / "out_invalid_strictness"),
    ])
    assert result.exit_code != 0
    assert "Invalid value for '--strictness'" in result.output


def test_review_sarif_contains_code_mismatch_rule(tmp_path):
    import json

    out_dir = tmp_path / "out_sarif_code"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "robotics_arm" / "spec.md"),
        "--model", str(EXAMPLES / "robotics_arm" / "model.yaml"),
        "--code", str(EXAMPLES / "robotics_arm" / "controller.py"),
        "--out", str(out_dir),
    ])
    assert result.exit_code == 0, result.output

    sarif = json.loads((out_dir / "results.sarif").read_text())
    results = sarif["runs"][0]["results"]
    rule_ids = {r["ruleId"] for r in results}
    assert "CODE_BOUND_MISMATCH" in rule_ids
    assert "CODE_TIMING_MISMATCH" in rule_ids
