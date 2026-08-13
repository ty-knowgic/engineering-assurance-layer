"""
Coverage / UNKNOWN plane tests.

The regression these lock down: before the UNKNOWN plane existed, EAL answered
real upstream Nav2 behavior trees with `findings.json` = 0 findings, SARIF = 0
results, `run_metadata.status` = PASS and exit code 0 — while silently dropping
every Nav2 control-flow node it did not model. The only trace was one line of
prose in `review_summary.md`, which no CI gate reads.

Fixtures in `tests/fixtures/nav2_upstream_bt/` are unmodified files from
ros-navigation/navigation2 @ 075b29611a7d21ff4f1c74077a17c672e708001c
(nav2_bt_navigator/behavior_trees/), retrieved 2026-08-13.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eal.cli import app
from eal.coverage import (
    AnalysisStatus,
    CoverageGap,
    CoverageGapCategory,
    analysis_status,
    assign_gap_ids,
)

runner = CliRunner()

NAV2_BT = Path(__file__).parent / "fixtures" / "nav2_upstream_bt"
EXAMPLES = Path(__file__).parent.parent / "examples"

NAV2_TREES = sorted(p.name for p in NAV2_BT.glob("*.xml"))


@pytest.fixture
def bare_spec(tmp_path) -> Path:
    """A spec with no analyzable content of its own — the BT XML is the input."""
    p = tmp_path / "spec.md"
    p.write_text(
        "# Nav Stack\n\n"
        "## Entities\n\n"
        "- nav_stack: ROS 2 Nav2 navigation stack\n\n"
        "## Requirements\n\n"
        "- REQ-001: The robot must recover from planner failure.\n"
    )
    return p


def _review(*args) -> tuple[int, dict, dict, dict]:
    """Run the CLI and return (exit_code, findings, run_metadata, sarif)."""
    out = args[-1]
    result = runner.invoke(app, ["review", *[str(a) for a in args[:-1]], "--out", str(out)])
    findings = json.loads((Path(out) / "findings.json").read_text())
    metadata = json.loads((Path(out) / "run_metadata.json").read_text())
    sarif = json.loads((Path(out) / "results.sarif").read_text())
    return result.exit_code, findings, metadata, sarif


# ── The core regression ───────────────────────────────────────────────────────

@pytest.mark.parametrize("tree_name", NAV2_TREES)
def test_real_nav2_tree_never_reports_pass(tree_name, bare_spec, tmp_path):
    """No real upstream Nav2 tree may produce a PASS in any machine-readable plane."""
    exit_code, findings, metadata, sarif = _review(
        "--spec", bare_spec,
        "--bt-xml", NAV2_BT / tree_name,
        "--policy-profile", "ci",
        tmp_path / "out",
    )

    assert exit_code == 3, f"{tree_name}: expected UNKNOWN exit 3, got {exit_code}"
    assert findings["status"] == "analysis_incomplete"
    assert findings["analysis_status"] == "INCOMPLETE"
    assert findings["coverage_gap_count"] >= 1
    assert metadata["results"]["status"] == "UNKNOWN"
    assert metadata["gate"]["result"] == "UNKNOWN"
    assert metadata["gate"]["exit_reason"] == "ANALYSIS_COVERAGE_INCOMPLETE"
    assert metadata["coverage"]["analysis_status"] == "INCOMPLETE"

    # The gap must reach SARIF, not just the human-readable summary.
    coverage_results = [
        r for r in sarif["runs"][0]["results"] if r["ruleId"].startswith("EAL_COVERAGE_")
    ]
    assert coverage_results, f"{tree_name}: no coverage gap in SARIF"
    assert sarif["runs"][0]["invocations"][0]["properties"]["analysisStatus"] == "INCOMPLETE"


def test_nav2_unsupported_nodes_are_named_not_just_counted(bare_spec, tmp_path):
    """The gap must say which constructs went unanalyzed, so it is actionable."""
    _, findings, _, _ = _review(
        "--spec", bare_spec,
        "--bt-xml", NAV2_BT / "navigate_to_pose_w_replanning_and_recovery.xml",
        tmp_path / "out",
    )
    unsupported = [
        g for g in findings["coverage_gaps"]
        if g["category"] == "UNSUPPORTED_INPUT_CONSTRUCT"
    ]
    assert len(unsupported) == 1
    named = set(unsupported[0]["unanalyzed_constructs"])
    # Nav2's real control flow, all of which EAL's narrow importer drops.
    assert {"RecoveryNode", "PipelineSequence", "ReactiveSequence"} <= named


def test_local_profile_reports_unknown_but_does_not_block(bare_spec, tmp_path):
    """Reporting is always honest; blocking is a policy decision."""
    exit_code, findings, metadata, _ = _review(
        "--spec", bare_spec,
        "--bt-xml", NAV2_BT / "follow_point.xml",
        "--policy-profile", "local",
        tmp_path / "out",
    )
    assert exit_code == 0
    assert findings["analysis_status"] == "INCOMPLETE"
    assert metadata["results"]["status"] == "UNKNOWN"
    assert metadata["gate"]["result"] == "UNKNOWN"


def test_fail_on_unknown_flag_overrides_profile(bare_spec, tmp_path):
    exit_code, _, metadata, _ = _review(
        "--spec", bare_spec,
        "--bt-xml", NAV2_BT / "follow_point.xml",
        "--policy-profile", "local",
        "--fail-on-unknown",
        tmp_path / "out",
    )
    assert exit_code == 3
    assert metadata["policy"]["sources"]["fail_on_unknown"] == "explicit_flag"


def test_unknown_takes_precedence_over_severity_gate(tmp_path):
    """An incomplete analysis must not be reported as a graded severity result."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Signals\n- speed: sensor, m/s, bounds=[0, 10]\n\n"
        "## Requirements\n- REQ-001: speed must stay under 5 m/s.\n"
    )
    exit_code, _, metadata, _ = _review(
        "--spec", spec,
        "--bt-xml", NAV2_BT / "navigate_to_pose_w_replanning_and_recovery.xml",
        "--fail-on-severity", "LOW",
        "--fail-on-unknown",
        tmp_path / "out",
    )
    assert exit_code == 3
    assert metadata["gate"]["result"] == "UNKNOWN"


# ── No false UNKNOWNs on the curated corpus ───────────────────────────────────

@pytest.mark.parametrize("name", ["ci_smoke", "robotics_arm", "boundary_clean", "mobile_robot"])
def test_curated_examples_stay_complete(name, tmp_path):
    """A false UNKNOWN destroys gate trust as surely as a false PASS."""
    args = ["--spec", EXAMPLES / name / "spec.md", "--model", EXAMPLES / name / "model.yaml"]
    code = EXAMPLES / name / "controller.py"
    if code.exists():
        args += ["--code", code]
    _, findings, metadata, _ = _review(*args, tmp_path / "out")
    assert findings["analysis_status"] == "COMPLETE"
    assert findings["coverage_gap_count"] == 0
    assert metadata["results"]["status"] in ("PASS", "REVIEW_REQUIRED")


def test_supported_bt_fixture_stays_complete(tmp_path):
    """EAL's own BT example uses only supported constructs and must not go UNKNOWN."""
    ex = EXAMPLES / "behaviortree_timeout_precondition"
    _, findings, _, _ = _review(
        "--spec", ex / "spec.md", "--bt-xml", ex / "tree.xml", tmp_path / "out"
    )
    assert findings["analysis_status"] == "COMPLETE"


# ── Detection rules that do not need a real tree ──────────────────────────────

def test_empty_ir_is_unknown_not_pass(tmp_path):
    """A spec with nothing checkable must not yield a zero-finding PASS."""
    spec = tmp_path / "spec.md"
    spec.write_text("## Entities\n- thing: a thing\n")
    exit_code, findings, metadata, _ = _review(
        "--spec", spec, "--policy-profile", "ci", tmp_path / "out"
    )
    assert exit_code == 3
    assert metadata["results"]["status"] == "UNKNOWN"
    assert any(
        g["category"] == "NO_ANALYZABLE_CONTENT" for g in findings["coverage_gaps"]
    )


def test_code_file_yielding_nothing_is_unknown(tmp_path):
    """Supplying code EAL cannot read anything from leaves it unverified, not clean."""
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Signals\n- speed: sensor, m/s, bounds=[0, 10]\n\n"
        "## Requirements\n- REQ-001: speed must stay under 5 m/s.\n"
    )
    code = tmp_path / "controller.py"
    code.write_text('"""No numeric content at all."""\n\n\ndef run(x):\n    return x\n')
    _, findings, _, _ = _review("--spec", spec, "--code", code, tmp_path / "out")
    assert findings["analysis_status"] == "INCOMPLETE"
    assert any(
        g["category"] == "INPUT_YIELDED_NO_CONTENT" for g in findings["coverage_gaps"]
    )


def test_empty_model_yaml_is_unknown(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        "## Signals\n- speed: sensor, m/s, bounds=[0, 10]\n\n"
        "## Requirements\n- REQ-001: speed must stay under 5 m/s.\n"
    )
    model = tmp_path / "model.yaml"
    model.write_text("# nothing recognized here\nunrelated_key: 1\n")
    _, findings, _, _ = _review("--spec", spec, "--model", model, tmp_path / "out")
    assert any(
        g["category"] == "INPUT_YIELDED_NO_CONTENT" and "model.yaml" in g["affected_input"]
        for g in findings["coverage_gaps"]
    )


# ── Unit-level ────────────────────────────────────────────────────────────────

def test_gap_ids_are_deterministic():
    gaps = [
        CoverageGap(
            id="X", category=CoverageGapCategory.NO_ANALYZABLE_CONTENT,
            title="b", summary="", affected_input="z",
        ),
        CoverageGap(
            id="X", category=CoverageGapCategory.UNSUPPORTED_INPUT_CONSTRUCT,
            title="a", summary="", affected_input="y",
        ),
    ]
    assigned = assign_gap_ids(gaps)
    assert [g.id for g in assigned] == ["U-001", "U-002"]
    assert assigned[0].category == CoverageGapCategory.UNSUPPORTED_INPUT_CONSTRUCT


def test_analysis_status_mapping():
    assert analysis_status([]) is AnalysisStatus.COMPLETE
    assert analysis_status([
        CoverageGap(
            id="U-001", category=CoverageGapCategory.NO_ANALYZABLE_CONTENT,
            title="t", summary="s",
        )
    ]) is AnalysisStatus.INCOMPLETE
