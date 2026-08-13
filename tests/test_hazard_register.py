"""
Declared silence: the unchecked-hazard register.

The failure this exists to prevent is not a missed hazard — it is a manufactured
one. On EAL's own corpus, taking the flagship Nav2 config, cutting the sensor
marking range to 0.4 m so the robot cannot see far enough to stop, and then
applying exactly the fix EAL recommended for the acceleration mismatch, produced
`0 findings`, `PASS`, `exit 0`. The tool did not merely fail to see the hazard.
It directed attention to an unrelated issue and rewarded resolving it with a
green result.

A static tool cannot find hazards nobody declared. What it can do is refuse to
let its own silence read as coverage. These tests hold that line:

  - the register is emitted on EVERY run, above all on clean ones
  - it is derived from measured results, so it cannot drift from reality
  - no output word claims more than "the checks that ran found nothing"
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from eal import hazards
from eal.cli import app

runner = CliRunner()

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "tests" / "fixtures" / "nav2_upstream_params"
SPEC = ROOT / "demo" / "spec" / "nav2_motion_limits.md"


@pytest.fixture
def false_confidence_config(tmp_path) -> Path:
    """
    The config that motivated this whole mechanism.

    Sensor range cut to 0.4 m — a severe hazard EAL cannot see — with the
    acceleration mismatch EAL *does* report resolved, exactly as its own
    suggested fix instructs.
    """
    src = (PARAMS / "nav2_params.yaml").read_text()
    t = src.replace("          obstacle_max_range: 2.5\n",
                    "          obstacle_max_range: 0.4\n", 1)
    t = t.replace("      ax_max: 3.0\n", "      ax_max: 2.5\n")
    t = t.replace("      ax_min: -3.0\n", "      ax_min: -2.5\n")
    t = t.replace("      az_max: 3.5\n", "      az_max: 3.2\n")
    assert t != src
    p = tmp_path / "params.yaml"
    p.write_text(t)
    return p


def _review(*args, out: Path):
    result = runner.invoke(
        app, ["review", *[str(a) for a in args], "--out", str(out)]
    )
    return (
        result,
        json.loads((out / "findings.json").read_text()),
        json.loads((out / "run_metadata.json").read_text()),
        json.loads((out / "results.sarif").read_text()),
    )


# ── The stop condition ────────────────────────────────────────────────────────

def test_false_confidence_config_does_not_look_unconditionally_clean(
    false_confidence_config, tmp_path
):
    """
    The whole point. This config is dangerous and EAL cannot see why. It may
    still report no findings — but it must not present that as an unqualified
    clean result.
    """
    out = tmp_path / "out"
    result, findings, metadata, sarif = _review(
        "--spec", SPEC, "--nav2-params", false_confidence_config,
        "--policy-profile", "ci", out=out,
    )
    assert findings["finding_count"] == 0

    # No plane may use the bare word PASS.
    assert metadata["results"]["status"] == "NO_FINDINGS_IN_SCOPE"
    assert metadata["gate"]["result"] == "BELOW_THRESHOLD"
    assert findings["status"] == "no_findings_in_scope"

    # Every machine-readable plane must carry what was not checked.
    for register in (
        findings["unchecked_hazards"],
        metadata["coverage"]["unchecked_hazards"],
        sarif["runs"][0]["invocations"][0]["properties"]["uncheckedHazards"],
    ):
        assert register["class_count"] >= 1
        titles = " ".join(c["title"] for c in register["classes"]).lower()
        assert "sensing range" in titles, "the hazard actually present must be named"

    # And the human surfaces.
    summary = (out / "review_summary.md").read_text()
    assert "What was NOT checked" in summary
    assert "not a statement that the configuration is safe" in summary
    report = (out / "report.html").read_text()
    assert "What was NOT checked" in report
    assert "NO FINDINGS IN SCOPE" in report
    assert "not</strong> a statement that the configuration is safe" in report

    # Rich hard-wraps the terminal output, so collapse whitespace before matching.
    stdout = " ".join(result.stdout.split())
    assert "Not checked by this tool" in stdout
    assert "not a statement that this configuration is safe" in stdout
    assert "Reduced sensing range" in stdout
    assert "Gate result: BELOW THRESHOLD" in stdout
    assert "Review status: NO FINDINGS IN SCOPE" in stdout


# ── Always emitted ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", sorted(p.name for p in PARAMS.glob("*.yaml")))
def test_register_is_emitted_on_every_run(params, tmp_path):
    _, findings, metadata, sarif = _review(
        "--spec", SPEC, "--nav2-params", PARAMS / params, out=tmp_path / "out"
    )
    assert findings["unchecked_hazards"]["class_count"] >= 1
    assert metadata["coverage"]["unchecked_hazards"]["class_count"] >= 1
    assert sarif["runs"][0]["invocations"][0]["properties"]["uncheckedHazards"]


def test_register_is_emitted_with_no_nav2_input_at_all(minimal_spec, tmp_path):
    """The blind spots are properties of the tool, not of one input format."""
    _, findings, _, _ = _review("--spec", minimal_spec, out=tmp_path / "out")
    assert findings["unchecked_hazards"]["class_count"] >= 1


def test_no_output_plane_uses_the_bare_word_pass(tmp_path):
    """A clean run on a clean config still must not say `PASS`."""
    out = tmp_path / "out"
    _, findings, metadata, _ = _review(
        "--spec", SPEC, "--nav2-params", PARAMS / "nav2_system_params.yaml",
        "--policy-profile", "ci", out=out,
    )
    assert findings["finding_count"] == 0
    assert metadata["results"]["status"] != "PASS"
    assert metadata["gate"]["result"] != "PASS"
    assert findings["analysis_status"] != "COMPLETE"


# ── Derived, not asserted ─────────────────────────────────────────────────────

def test_register_matches_what_the_evaluation_measured():
    """
    The shipped register must equal what the committed eval results imply. If
    they diverge, the tool is telling users about blind spots it no longer has,
    or hiding ones it does.
    """
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_hazard_register import build_register  # noqa: E402

    expected = build_register()
    shipped = yaml.safe_load(hazards.REGISTER_PATH.read_text())
    assert shipped["classes"] == expected["classes"], (
        "src/eal/data/unchecked_hazards.yaml is stale — run `make hazard-register`"
    )
    assert shipped["measured"] == expected["measured"]


def test_every_shipped_class_names_its_evidence():
    for c in hazards.hazard_classes():
        assert c["evidence"], c["id"]
        assert all(e["mutation"].startswith("M") for e in c["evidence"])
        assert c["worst_hazard"] in ("moderate", "severe")


def test_register_covers_the_hazards_the_evaluation_reports_as_silent():
    results = json.loads((ROOT / "eval" / "output" / "results.json").read_text())["results"]
    silent = {r["category"] for r in results if r["hazardous"] and not r["eal_said_something"]}
    assert {c["id"] for c in hazards.hazard_classes()} == silent


def test_register_is_shipped_as_package_data():
    """It must survive installation, not only exist in the source tree."""
    assert hazards.REGISTER_PATH.exists()
    assert hazards.REGISTER_PATH.parent.name == "data"
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert "package-data" in pyproject and "data/*.yaml" in pyproject
