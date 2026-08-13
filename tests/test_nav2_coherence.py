"""
Nav2 cross-artifact coherence checks, run against real upstream configuration.

The corpus is not injected. All three files are unmodified upstream Nav2
configs at the same commit, and they happen to span the interesting cases:

  nav2_system_params.yaml  (DWB)   all six limit roles agree      -> clean
  nav2_params.yaml         (MPPI)  accel roles disagree 1.20x     -> unsafe-leaning
  nav2_no_map_params.yaml  (MPPI)  accel and velocity disagree    -> both classes

The false-positive regression locked down here is a real one. A throwaway spike
of this check reported `wz_max 1.9` vs `max_velocity[2] 2.0` as a mismatch. It
is not: the controller being *more* conservative than the downstream clamp is
ordinary and usually deliberate. An undirected numeric comparison is a noise
generator, so direction is part of the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eal.cli import app
from eal.findings.schema import FindingCategory, FindingSeverity
from eal.ingestion.nav2_params import parse_nav2_params
from eal.rules.nav2_coherence import check_nav2_coherence

runner = CliRunner()

PARAMS = Path(__file__).parent / "fixtures" / "nav2_upstream_params"

ACCEL = FindingCategory.NAV2_ACCEL_OVERDECLARED.value
VELOCITY = FindingCategory.NAV2_VELOCITY_OVERDECLARED.value
HEADROOM = FindingCategory.NAV2_LIMIT_HEADROOM.value
HORIZON = FindingCategory.NAV2_HORIZON_EXCEEDS_COSTMAP.value


def _check(filename: str):
    return check_nav2_coherence(parse_nav2_params(PARAMS / filename))


def _categories(filename: str) -> list[str]:
    return [f.category.value for f in _check(filename)]


# ── The stop condition ────────────────────────────────────────────────────────

def test_dwb_upstream_config_reports_no_mismatch():
    """
    All six roles agree in the DWB config, so no mismatch may be reported.

    One informational headroom item does exist — `min_vel_x: 0.0` against a
    -0.26 clamp, i.e. "this robot does not reverse" — and it is emitted at
    `strict` only. It must never be classified as a mismatch.
    """
    cats = _categories("nav2_system_params.yaml")
    assert ACCEL not in cats
    assert VELOCITY not in cats
    assert HORIZON not in cats


def test_dwb_config_is_silent_at_default_strictness(minimal_spec, tmp_path):
    """What a user actually sees on the clean config: nothing."""
    _, findings, _ = _review(
        "--spec", minimal_spec,
        "--nav2-params", PARAMS / "nav2_system_params.yaml",
        tmp_path / "out",
    )
    assert [f for f in findings["findings"] if f["category"].startswith("NAV2_")] == []


def test_mppi_bringup_config_flags_accel_only():
    """nav2_params.yaml: accel roles disagree 1.20x/1.09x; velocities agree."""
    cats = _categories("nav2_params.yaml")
    assert cats.count(ACCEL) == 3          # ax_max, ax_min, az_max
    assert cats.count(VELOCITY) == 0       # vx_max and wz_max do not over-declare
    assert cats.count(HORIZON) == 0        # 1.400 m <= 1.500 m


def test_mppi_no_map_config_flags_both_classes():
    cats = _categories("nav2_no_map_params.yaml")
    assert cats.count(ACCEL) == 3
    assert cats.count(VELOCITY) >= 2       # vx_max 1.92x, wz_max 1.90x


# ── The false positive that must not come back ────────────────────────────────

def test_conservative_controller_is_not_reported_as_a_mismatch():
    """wz_max 1.9 vs smoother 2.0 — controller is more conservative. Not a defect."""
    findings = _check("nav2_params.yaml")
    angular = [
        f for f in findings
        if "NAV2-CONTROLLER_V_MAX_ANGULAR" in f.related_ir_nodes
    ]
    assert len(angular) == 1
    assert angular[0].category.value == HEADROOM
    assert angular[0].severity is FindingSeverity.LOW


def test_headroom_is_never_high_or_critical():
    for name in ("nav2_params.yaml", "nav2_no_map_params.yaml"):
        for f in _check(name):
            if f.category.value == HEADROOM:
                assert f.severity is FindingSeverity.LOW


# ── Direction and classification ──────────────────────────────────────────────

def test_accel_overdeclaration_is_high_velocity_is_medium():
    findings = _check("nav2_no_map_params.yaml")
    by_cat = {}
    for f in findings:
        by_cat.setdefault(f.category.value, []).append(f)
    assert all(f.severity is FindingSeverity.HIGH for f in by_cat[ACCEL])
    assert all(f.severity is FindingSeverity.MEDIUM for f in by_cat[VELOCITY])


def test_decel_finding_names_both_values_paths_and_ratio():
    """A finding is only actionable if it names the lines a human must edit."""
    f = next(
        f for f in _check("nav2_params.yaml")
        if "NAV2-CONTROLLER_A_DECEL_LINEAR" in f.related_ir_nodes
    )
    assert f.category.value == ACCEL
    assert "ax_min" in f.summary and "-3.0" in f.summary
    assert "max_decel" in f.summary and "-2.5" in f.summary
    assert "1.20x" in f.title
    assert any("FollowPath.ax_min" in r for r in f.source_refs)
    assert any("max_decel[0]" in r for r in f.source_refs)
    assert "unsafe direction" in f.details


def test_findings_state_that_intent_is_not_in_the_file():
    """The tool reports the numbers; it must not pronounce on intent."""
    for f in _check("nav2_params.yaml"):
        if f.category.value in (ACCEL, VELOCITY):
            assert "depends on intent" in f.details


def test_negative_values_are_compared_by_magnitude():
    """decel is written negative; -3.0 vs -2.5 is over-declaration, not under."""
    f = next(
        f for f in _check("nav2_no_map_params.yaml")
        if "NAV2-CONTROLLER_A_DECEL_LINEAR" in f.related_ir_nodes
    )
    assert f.category.value == ACCEL


# ── Horizon rule ──────────────────────────────────────────────────────────────

def test_horizon_rule_passes_on_all_real_configs():
    """56 * 0.05 * 0.5 = 1.400 m vs 1.500 m radius. Real margin is only 6.7%."""
    for name in ("nav2_params.yaml", "nav2_no_map_params.yaml"):
        assert HORIZON not in _categories(name)


def test_horizon_rule_fires_just_past_the_boundary(tmp_path):
    """Raising vx_max from 0.5 to 0.54 alone breaks the upstream-documented rule."""
    src = (PARAMS / "nav2_params.yaml").read_text()
    modified = src.replace("      vx_max: 0.5\n", "      vx_max: 0.54\n", 1)
    assert modified != src
    p = tmp_path / "nav2_params.yaml"
    p.write_text(modified)

    findings = check_nav2_coherence(parse_nav2_params(p))
    horizon = [f for f in findings if f.category.value == HORIZON]
    assert len(horizon) == 1
    assert "1.512" in horizon[0].summary   # 56 * 0.05 * 0.54
    assert "1.500" in horizon[0].summary
    assert horizon[0].severity is FindingSeverity.MEDIUM


def test_horizon_rule_is_silent_for_non_mppi_controllers():
    """DWB declares no time_steps/model_dt; the rule is inapplicable, not failing."""
    assert HORIZON not in _categories("nav2_system_params.yaml")


# ── Applicability ─────────────────────────────────────────────────────────────

def test_no_smoother_means_inapplicable_not_a_finding(tmp_path):
    """A stack without velocity_smoother has nothing to compare against."""
    src = (PARAMS / "nav2_params.yaml").read_text()
    p = tmp_path / "params.yaml"
    p.write_text(src.replace("velocity_smoother:", "velocity_smoother_disabled:", 1))
    findings = check_nav2_coherence(parse_nav2_params(p))
    assert [f for f in findings if f.category.value in (ACCEL, VELOCITY, HEADROOM)] == []


def test_no_slice_returns_no_findings():
    assert check_nav2_coherence(None) == []


# ── End to end ────────────────────────────────────────────────────────────────

def _review(*args) -> tuple[int, dict, dict]:
    out = args[-1]
    result = runner.invoke(app, ["review", *[str(a) for a in args[:-1]], "--out", str(out)])
    return (
        result.exit_code,
        json.loads((Path(out) / "findings.json").read_text()),
        json.loads((Path(out) / "run_metadata.json").read_text()),
    )


def test_clean_config_passes_ci_gate(minimal_spec, tmp_path):
    exit_code, findings, metadata = _review(
        "--spec", minimal_spec,
        "--nav2-params", PARAMS / "nav2_system_params.yaml",
        "--policy-profile", "ci", tmp_path / "out",
    )
    assert exit_code == 0
    assert metadata["gate"]["result"] == "BELOW_THRESHOLD"
    assert findings["analysis_status"] == "INPUTS_FULLY_READ"
    assert not [
        f for f in findings["findings"] if f["category"].startswith("NAV2_")
    ]


def test_clean_config_still_passes_ci_gate_at_strict(minimal_spec, tmp_path):
    """Even the informational item must not turn the clean config into a failure."""
    exit_code, _, metadata = _review(
        "--spec", minimal_spec,
        "--nav2-params", PARAMS / "nav2_system_params.yaml",
        "--policy-profile", "ci", "--strictness", "strict", tmp_path / "out",
    )
    assert exit_code == 0
    assert metadata["gate"]["result"] == "BELOW_THRESHOLD"


def test_mismatched_config_fails_ci_gate(minimal_spec, tmp_path):
    exit_code, findings, metadata = _review(
        "--spec", minimal_spec,
        "--nav2-params", PARAMS / "nav2_params.yaml",
        "--policy-profile", "ci", tmp_path / "out",
    )
    assert exit_code == 2
    assert metadata["gate"]["result"] == "THRESHOLD_EXCEEDED"
    # UNKNOWN must not be involved: the input was fully analyzed.
    assert findings["analysis_status"] == "INPUTS_FULLY_READ"
    assert [f for f in findings["findings"] if f["category"] == ACCEL]


def test_headroom_is_strict_only(minimal_spec, tmp_path):
    """
    The informational direction is off by default and on at `strict`. Mismatch
    findings are unaffected by strictness — they are deterministic facts.
    """
    seen = {}
    for level in ("relaxed", "balanced", "strict"):
        _, findings, meta = _review(
            "--spec", minimal_spec,
            "--nav2-params", PARAMS / "nav2_params.yaml",
            "--strictness", level, tmp_path / level,
        )
        seen[level] = ([f["category"] for f in findings["findings"]], meta)

    assert HEADROOM not in seen["relaxed"][0]
    assert HEADROOM not in seen["balanced"][0]
    assert HEADROOM in seen["strict"][0]

    accel_counts = {lvl: cats.count(ACCEL) for lvl, (cats, _) in seen.items()}
    assert len(set(accel_counts.values())) == 1, accel_counts
    assert seen["balanced"][1]["strictness"]["suppressed_by_rule"].get(HEADROOM, 0) >= 1


def test_findings_reach_sarif_with_locations(minimal_spec, tmp_path):
    _review(
        "--spec", minimal_spec,
        "--nav2-params", PARAMS / "nav2_params.yaml",
        tmp_path / "out",
    )
    sarif = json.loads((tmp_path / "out" / "results.sarif").read_text())
    accel = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == ACCEL]
    assert len(accel) == 3
    assert all(r["level"] == "error" for r in accel)


@pytest.mark.parametrize("filename", [
    "nav2_system_params.yaml", "nav2_params.yaml", "nav2_no_map_params.yaml",
])
def test_check_is_deterministic(filename):
    first = [(f.category.value, f.title) for f in _check(filename)]
    second = [(f.category.value, f.title) for f in _check(filename)]
    assert first == second
