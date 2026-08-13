"""
Nav2 parameter ingestion tests.

Fixtures in `tests/fixtures/nav2_upstream_params/` are unmodified files from
ros-navigation/navigation2 @ 075b29611a7d21ff4f1c74077a17c672e708001c
(retrieved 2026-08-13):

  nav2_params.yaml        <- nav2_bringup/params/                   (MPPI)
  nav2_system_params.yaml <- nav2_system_tests/src/system/          (DWB)
  nav2_no_map_params.yaml <- nav2_system_tests/src/gps_navigation/  (MPPI)

The expected values below were transcribed by reading the YAML directly, not by
running the parser. That is the point: an extractor validated against its own
output validates nothing. If the parser and these tables ever disagree, one of
them is wrong and the file itself is the tiebreaker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from eal.cli import app
from eal.ingestion.nav2_params import (
    CONTROLLER_LIMIT_PARAMS,
    LimitRole,
    Nav2Stage,
    parse_nav2_params,
)

runner = CliRunner()

PARAMS = Path(__file__).parent / "fixtures" / "nav2_upstream_params"

MPPI = "nav2_mppi_controller::MPPIController"
DWB = "dwb_core::DWBLocalPlanner"

# ── Hand-read expectations ────────────────────────────────────────────────────
# (role -> value) as literally written in the file.

HAND_READ = {
    "nav2_params.yaml": {
        "plugin": MPPI,
        "plugin_key": "FollowPath",
        "controller": {
            LimitRole.V_MAX_LINEAR: 0.5,      # vx_max
            LimitRole.V_MIN_LINEAR: -0.35,    # vx_min
            LimitRole.V_MAX_ANGULAR: 1.9,     # wz_max
            LimitRole.A_ACCEL_LINEAR: 3.0,    # ax_max
            LimitRole.A_DECEL_LINEAR: -3.0,   # ax_min
            LimitRole.A_ACCEL_ANGULAR: 3.5,   # az_max
        },
        "smoother": {
            LimitRole.V_MAX_LINEAR: 0.5,      # max_velocity[0]
            LimitRole.V_MIN_LINEAR: -0.5,     # min_velocity[0]
            LimitRole.V_MAX_ANGULAR: 2.0,     # max_velocity[2]
            LimitRole.A_ACCEL_LINEAR: 2.5,    # max_accel[0]
            LimitRole.A_DECEL_LINEAR: -2.5,   # max_decel[0]
            LimitRole.A_ACCEL_ANGULAR: 3.2,   # max_accel[2]
        },
        "scalars": {
            "controller_controller_frequency": 20.0,
            "controller_costmap_update_timeout": 0.30,
            "controller_time_steps": 56.0,
            "controller_model_dt": 0.05,
            "local_costmap_update_frequency": 5.0,
            "local_costmap_width": 3.0,
            "local_costmap_height": 3.0,
            "local_costmap_resolution": 0.05,
            "local_costmap_robot_radius": 0.22,
            "local_costmap_inflation_radius": 0.70,
            "local_costmap_cost_scaling_factor": 3.0,
            "local_costmap_scan_obstacle_max_range": 2.5,
            "local_costmap_scan_obstacle_min_range": 0.0,
            "local_costmap_scan_raytrace_max_range": 3.0,
        },
    },
    "nav2_system_params.yaml": {
        "plugin": DWB,
        "plugin_key": "FollowPath",
        "controller": {
            LimitRole.V_MAX_LINEAR: 0.26,     # max_vel_x
            LimitRole.V_MIN_LINEAR: 0.0,      # min_vel_x
            LimitRole.V_MAX_ANGULAR: 1.0,     # max_vel_theta
            LimitRole.A_ACCEL_LINEAR: 2.5,    # acc_lim_x
            LimitRole.A_DECEL_LINEAR: -2.5,   # decel_lim_x
            LimitRole.A_ACCEL_ANGULAR: 3.2,   # acc_lim_theta
        },
        "smoother": {
            LimitRole.V_MAX_LINEAR: 0.26,
            LimitRole.V_MIN_LINEAR: -0.26,
            LimitRole.V_MAX_ANGULAR: 1.0,
            LimitRole.A_ACCEL_LINEAR: 2.5,
            LimitRole.A_DECEL_LINEAR: -2.5,
            LimitRole.A_ACCEL_ANGULAR: 3.2,
        },
        "scalars": {
            "controller_controller_frequency": 20.0,
            "local_costmap_update_frequency": 5.0,
            "local_costmap_width": 3.0,
            "local_costmap_height": 3.0,
            "local_costmap_robot_radius": 0.22,
            "local_costmap_inflation_radius": 0.55,
            "local_costmap_scan_obstacle_max_range": 2.5,
            "local_costmap_scan_raytrace_max_range": 3.0,
        },
    },
    "nav2_no_map_params.yaml": {
        "plugin": MPPI,
        "plugin_key": "FollowPath",
        "controller": {
            LimitRole.V_MAX_LINEAR: 0.5,
            LimitRole.V_MIN_LINEAR: -0.35,
            LimitRole.V_MAX_ANGULAR: 1.9,
            LimitRole.A_ACCEL_LINEAR: 3.0,
            LimitRole.A_DECEL_LINEAR: -3.0,
            LimitRole.A_ACCEL_ANGULAR: 3.5,
        },
        "smoother": {
            LimitRole.V_MAX_LINEAR: 0.26,
            LimitRole.V_MIN_LINEAR: -0.26,
            LimitRole.V_MAX_ANGULAR: 1.0,
            LimitRole.A_ACCEL_LINEAR: 2.5,
            LimitRole.A_DECEL_LINEAR: -2.5,
            LimitRole.A_ACCEL_ANGULAR: 3.2,
        },
        "scalars": {
            "controller_controller_frequency": 20.0,
            "controller_time_steps": 56.0,
            "controller_model_dt": 0.05,
            "local_costmap_update_frequency": 5.0,
            "local_costmap_width": 3.0,
            "local_costmap_height": 3.0,
            "local_costmap_robot_radius": 0.22,
            "local_costmap_inflation_radius": 0.55,
            "local_costmap_scan_obstacle_max_range": 2.5,
            "local_costmap_scan_raytrace_max_range": 3.0,
        },
    },
}

FILES = sorted(HAND_READ)


# ── The stop condition: extraction must match hand-reading exactly ────────────

@pytest.mark.parametrize("filename", FILES)
def test_controller_plugin_is_identified(filename):
    s = parse_nav2_params(PARAMS / filename)
    assert s.controller_plugin == HAND_READ[filename]["plugin"]
    assert s.controller_plugin_key == HAND_READ[filename]["plugin_key"]
    assert s.unsupported_constructs == []


@pytest.mark.parametrize("filename", FILES)
def test_controller_limits_match_hand_reading(filename):
    s = parse_nav2_params(PARAMS / filename)
    got = {r: v.value for r, v in s.by_stage(Nav2Stage.CONTROLLER).items()}
    assert got == HAND_READ[filename]["controller"]


@pytest.mark.parametrize("filename", FILES)
def test_smoother_limits_match_hand_reading(filename):
    s = parse_nav2_params(PARAMS / filename)
    got = {r: v.value for r, v in s.by_stage(Nav2Stage.SMOOTHER).items()}
    assert got == HAND_READ[filename]["smoother"]


@pytest.mark.parametrize("filename", FILES)
def test_scalars_match_hand_reading(filename):
    s = parse_nav2_params(PARAMS / filename)
    for name, expected in HAND_READ[filename]["scalars"].items():
        value = s.scalar(name)
        assert value is not None, f"{filename}: {name} not extracted"
        assert value.value == pytest.approx(expected), f"{filename}: {name}"


@pytest.mark.parametrize("filename", FILES)
def test_dwb_has_no_mppi_only_scalars(filename):
    """Plugin-specific scalars must not leak across plugins."""
    s = parse_nav2_params(PARAMS / filename)
    if s.controller_plugin == DWB:
        assert s.scalar("controller_time_steps") is None
        assert s.scalar("controller_model_dt") is None


# ── Provenance ────────────────────────────────────────────────────────────────

def test_every_value_carries_a_resolvable_yaml_path():
    """A finding is only actionable if it can name the line to go edit."""
    s = parse_nav2_params(PARAMS / "nav2_params.yaml")
    assert s.values
    for v in s.values:
        assert v.yaml_path
        assert "ros__parameters" in v.yaml_path
        assert v.unit


def test_yaml_paths_are_exact():
    s = parse_nav2_params(PARAMS / "nav2_params.yaml")
    paths = {v.name: v.yaml_path for v in s.values}
    assert paths["controller_a_decel_linear"] == (
        "controller_server.ros__parameters.FollowPath.ax_min"
    )
    assert paths["smoother_a_decel_linear"] == (
        "velocity_smoother.ros__parameters.max_decel[0]"
    )
    assert paths["local_costmap_scan_obstacle_max_range"] == (
        "local_costmap.local_costmap.ros__parameters.voxel_layer.scan.obstacle_max_range"
    )


def test_native_param_names_are_preserved():
    """Role names are EAL's; the file's own names must survive for the fix hint."""
    s = parse_nav2_params(PARAMS / "nav2_params.yaml")
    controller = s.by_stage(Nav2Stage.CONTROLLER)
    assert controller[LimitRole.A_DECEL_LINEAR].param_name == "ax_min"
    assert controller[LimitRole.V_MAX_ANGULAR].param_name == "wz_max"

    dwb = parse_nav2_params(PARAMS / "nav2_system_params.yaml")
    assert dwb.by_stage(Nav2Stage.CONTROLLER)[LimitRole.A_DECEL_LINEAR].param_name == "decel_lim_x"


def test_same_roles_extracted_across_two_different_plugins():
    """The role vocabulary must generalize; only the name mapping is per-plugin."""
    mppi = parse_nav2_params(PARAMS / "nav2_params.yaml")
    dwb = parse_nav2_params(PARAMS / "nav2_system_params.yaml")
    assert set(mppi.by_stage(Nav2Stage.CONTROLLER)) == set(dwb.by_stage(Nav2Stage.CONTROLLER))
    assert mppi.controller_plugin != dwb.controller_plugin


# ── Unknown / degenerate input ────────────────────────────────────────────────

def test_unknown_controller_plugin_is_unsupported_not_guessed(tmp_path):
    p = tmp_path / "params.yaml"
    p.write_text(
        "controller_server:\n"
        "  ros__parameters:\n"
        "    controller_frequency: 20.0\n"
        "    controller_plugins: [\"FollowPath\"]\n"
        "    FollowPath:\n"
        "      plugin: \"some_vendor::SecretController\"\n"
        "      max_vel_x: 9.9\n"
    )
    s = parse_nav2_params(p)
    assert s.controller_plugin == "some_vendor::SecretController"
    assert s.unsupported_constructs == ["controller plugin some_vendor::SecretController"]
    # It must not have guessed a mapping from the familiar-looking name.
    assert s.by_stage(Nav2Stage.CONTROLLER) == {}


def test_non_nav2_yaml_reports_absent_sections(tmp_path):
    p = tmp_path / "other.yaml"
    p.write_text("some_other_tool:\n  setting: 1\n")
    s = parse_nav2_params(p)
    assert s.values == []
    assert set(s.absent_sections) == {
        "controller_server", "velocity_smoother", "local_costmap"
    }


def test_booleans_are_not_read_as_numbers(tmp_path):
    """`bool` is a subclass of `int`; `enabled: true` must not become 1.0."""
    p = tmp_path / "params.yaml"
    p.write_text(
        "local_costmap:\n  local_costmap:\n    ros__parameters:\n"
        "      rolling_window: true\n"
        "      width: 3\n"
    )
    s = parse_nav2_params(p)
    assert s.scalar("local_costmap_width").value == 3.0
    assert all(v.param_name != "rolling_window" for v in s.values)


def test_placeholder_string_values_are_skipped(tmp_path):
    """Real bringup files contain launch substitutions like `enabled: KEEPOUT_ZONE_ENABLED`."""
    p = tmp_path / "params.yaml"
    p.write_text(
        "local_costmap:\n  local_costmap:\n    ros__parameters:\n"
        "      robot_radius: KEEPOUT_PLACEHOLDER\n"
        "      width: 3\n"
    )
    s = parse_nav2_params(p)
    assert s.scalar("local_costmap_robot_radius") is None
    assert s.scalar("local_costmap_width").value == 3.0


# ── End-to-end through the CLI ────────────────────────────────────────────────

def _review(*args) -> tuple[int, dict, dict]:
    out = args[-1]
    result = runner.invoke(app, ["review", *[str(a) for a in args[:-1]], "--out", str(out)])
    return (
        result.exit_code,
        json.loads((Path(out) / "findings.json").read_text()),
        json.loads((Path(out) / "ir_snapshot.json").read_text()),
    )


@pytest.mark.parametrize("filename", FILES)
def test_real_params_reach_the_ir_with_provenance(filename, minimal_spec, tmp_path):
    _, findings, ir = _review(
        "--spec", minimal_spec, "--nav2-params", PARAMS / filename, tmp_path / "out"
    )
    nav2 = [c for c in ir["constraints"] if c["id"].startswith("NAV2-")]
    expected = (
        len(HAND_READ[filename]["controller"])
        + len(HAND_READ[filename]["smoother"])
        + len(HAND_READ[filename]["scalars"])
    )
    assert len(nav2) >= expected, f"{filename}: {len(nav2)} constraints, expected >= {expected}"
    for c in nav2:
        assert c["source_ref"]["file"].endswith(filename)
        assert c["source_ref"]["section"]
        assert c["numeric_value"] is not None
    assert findings["analysis_status"] == "COMPLETE"
    assert any(e["name"] == "nav2_stack" for e in ir["entities"])


def test_unknown_plugin_yields_unknown_not_pass(minimal_spec, tmp_path):
    p = tmp_path / "params.yaml"
    p.write_text(
        "controller_server:\n"
        "  ros__parameters:\n"
        "    controller_plugins: [\"FollowPath\"]\n"
        "    FollowPath:\n"
        "      plugin: \"some_vendor::SecretController\"\n"
    )
    exit_code, findings, _ = _review(
        "--spec", minimal_spec, "--nav2-params", p,
        "--policy-profile", "ci", tmp_path / "out",
    )
    assert exit_code == 3
    assert findings["analysis_status"] == "INCOMPLETE"
    gap = next(
        g for g in findings["coverage_gaps"]
        if g["category"] == "UNSUPPORTED_INPUT_CONSTRUCT"
    )
    assert "some_vendor::SecretController" in gap["unanalyzed_constructs"][0]


def test_registry_and_role_enum_stay_in_sync():
    """Every supported plugin must map every role, or comparisons silently skip."""
    for plugin, mapping in CONTROLLER_LIMIT_PARAMS.items():
        assert set(mapping) == set(LimitRole), f"{plugin} is missing roles"
