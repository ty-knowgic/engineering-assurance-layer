"""
Nav2 cross-artifact coherence checks.

Two checks, both deterministic and both operating on values extracted from a
real upstream Nav2 parameter file:

(A) Limit coherence. A Nav2 stack declares its motion limits twice — once in the
    controller plugin, once in the `velocity_smoother` that sits downstream of
    it. The verified chain (nav2_bringup/launch/navigation_launch.py) is:

        controller_server -> cmd_vel_nav -> velocity_smoother
            -> cmd_vel_smoothed -> collision_monitor -> cmd_vel -> base

    so the smoother's limits are what the base actually receives, and the
    controller's are a request. A text diff of `vx_max: 0.5 -> 2.0` cannot tell
    you whether the two still agree; this check can.

(B) Prediction horizon vs costmap size. This one is not our model — it is
    written down by the Nav2 maintainers in nav2_mppi_controller/README.md:
    if the prediction horizon at maximum speed exceeds the local costmap
    radius, the robot is artificially limited by the costmap.

## Direction matters, and the two directions are not the same finding

Reporting any numeric difference would be a noise generator. Three distinctions
are enforced here:

  controller > smoother, on acceleration
      The controller rolls out and validates trajectories assuming it can
      accelerate or brake harder than the chain will actually deliver. A
      trajectory judged collision-free under the optimistic figure may not be.
      Unsafe-leaning. HIGH.

  controller > smoother, on velocity
      The controller plans at a speed the smoother clamps away. The robot moves
      slower than planned, so prediction diverges from execution — a
      model-fidelity problem, not an unsafe-leaning one. MEDIUM.

  controller < smoother, either quantity
      The controller is simply configured more conservatively than the platform
      permits. That is ordinary and usually deliberate. Informational only, LOW,
      and emitted **at `strict` strictness only**.

      That last part is calibrated against the real corpus rather than assumed.
      Emitting this class by default produced exactly two findings across three
      upstream configs — `wz_max 1.9` against a 2.0 clamp (5% unused), and DWB's
      `min_vel_x: 0.0` against a -0.26 clamp, which only means "this robot does
      not drive in reverse". A reviewer dismisses both. A check whose default
      output is dismissed every time it fires trains people to ignore the tool,
      so the informational direction is off unless explicitly asked for. The
      direction *distinction* is still enforced at every strictness: the
      conservative case must never be reported as a mismatch.

## What this check does not decide

Whether a mismatch is a *defect* depends on intent, which is not in the file.
Upstream defaults can legitimately pair a generically-tuned controller with a
platform-tuned smoother. So every finding reports both values, both YAML paths,
and the direction — and leaves the judgement to a human.
"""

from __future__ import annotations

import math
from typing import Optional

from eal.findings.schema import Finding, FindingCategory, FindingSeverity
from eal.ingestion.nav2_params import LimitRole, Nav2ParamSlice, Nav2Stage, Nav2Value

# Roles where the controller assuming *more* than the chain delivers is
# unsafe-leaning, because trajectory validation depends on the figure.
_ACCEL_ROLES = {
    LimitRole.A_ACCEL_LINEAR,
    LimitRole.A_DECEL_LINEAR,
    LimitRole.A_ACCEL_ANGULAR,
}

_ROLE_LABEL: dict[LimitRole, str] = {
    LimitRole.V_MAX_LINEAR: "maximum forward velocity",
    LimitRole.V_MIN_LINEAR: "maximum reverse velocity",
    LimitRole.V_MAX_ANGULAR: "maximum angular velocity",
    LimitRole.A_ACCEL_LINEAR: "linear acceleration limit",
    LimitRole.A_DECEL_LINEAR: "linear deceleration limit",
    LimitRole.A_ACCEL_ANGULAR: "angular acceleration limit",
}

_ACCEL_RATIONALE = (
    "The controller rolls out and validates candidate trajectories against its own "
    "figure. Because the smoother caps what actually reaches the base, a trajectory "
    "accepted as feasible or collision-free under the controller's figure may not be "
    "achievable in execution. This leans in the unsafe direction."
)

_VELOCITY_RATIONALE = (
    "The smoother clamps commanded velocity below what the controller plans for, so "
    "the robot executes more slowly than predicted. Path tracking degrades as "
    "prediction diverges from execution. This does not lean unsafe on its own."
)

_INTENT_CAVEAT = (
    "Whether this is a defect depends on intent, which is not recorded in the "
    "configuration: a generically-tuned controller paired with a platform-tuned "
    "smoother can produce this legitimately. EAL reports both values and the "
    "direction; the judgement is yours."
)


def _ref(value: Nav2Value, path: str) -> str:
    return f"{path}:{value.yaml_path}"


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _limit_coherence(slice_: Nav2ParamSlice) -> list[Finding]:
    controller = slice_.by_stage(Nav2Stage.CONTROLLER)
    smoother = slice_.by_stage(Nav2Stage.SMOOTHER)
    # No smoother in this stack means the comparison does not apply. That is not
    # the same as being unable to check, so it must not raise a coverage gap.
    if not controller or not smoother:
        return []

    findings: list[Finding] = []
    for role in LimitRole:
        c, s = controller.get(role), smoother.get(role)
        if c is None or s is None:
            continue
        # Deceleration and reverse limits are written negative; compare envelopes.
        c_mag, s_mag = abs(c.value), abs(s.value)
        if _close(c_mag, s_mag):
            continue

        label = _ROLE_LABEL[role]
        refs = [_ref(c, slice_.path), _ref(s, slice_.path)]
        common = (
            f"Controller `{c.param_name}` = {c.value} {c.unit} "
            f"({c.yaml_path}); downstream velocity_smoother `{s.param_name}` = "
            f"{s.value} {s.unit} ({s.yaml_path})."
        )

        if c_mag > s_mag:
            ratio = c_mag / s_mag if s_mag else float("inf")
            is_accel = role in _ACCEL_ROLES
            findings.append(Finding(
                id="F-000",
                severity=FindingSeverity.HIGH if is_accel else FindingSeverity.MEDIUM,
                category=(
                    FindingCategory.NAV2_ACCEL_OVERDECLARED if is_accel
                    else FindingCategory.NAV2_VELOCITY_OVERDECLARED
                ),
                title=(
                    f"Controller declares {label} {ratio:.2f}x the downstream "
                    f"smoother limit"
                ),
                summary=(
                    f"{common} The controller's figure exceeds the smoother's by "
                    f"{ratio:.2f}x, and the smoother is what the base actually receives."
                ),
                details=(
                    (_ACCEL_RATIONALE if is_accel else _VELOCITY_RATIONALE)
                    + " "
                    + _INTENT_CAVEAT
                ),
                related_ir_nodes=[
                    f"NAV2-CONTROLLER_{role.value.upper()}",
                    f"NAV2-SMOOTHER_{role.value.upper()}",
                ],
                source_refs=refs,
                evidence_refs=[f"nav2_plugin:{slice_.controller_plugin or 'unknown'}"],
                suggested_fix=(
                    f"Reconcile the two declarations: either raise "
                    f"`velocity_smoother.{s.param_name}` to {c.value}, or lower "
                    f"`{c.param_name}` to {s.value}, whichever matches the platform's "
                    f"real capability."
                ),
            ))
        else:
            ratio = s_mag / c_mag if c_mag else float("inf")
            findings.append(Finding(
                id="F-000",
                severity=FindingSeverity.LOW,
                category=FindingCategory.NAV2_LIMIT_HEADROOM,
                title=f"Controller uses only part of the available {label}",
                summary=(
                    f"{common} The controller is the more conservative of the two, "
                    f"leaving {(1 - c_mag / s_mag) * 100:.0f}% of the smoother's "
                    f"envelope unused."
                ),
                details=(
                    "This direction is not unsafe-leaning and is frequently "
                    "deliberate. Reported for visibility only."
                ),
                related_ir_nodes=[
                    f"NAV2-CONTROLLER_{role.value.upper()}",
                    f"NAV2-SMOOTHER_{role.value.upper()}",
                ],
                source_refs=refs,
                suggested_fix=(
                    "No action required unless the unused envelope is unintentional."
                ),
            ))
    return findings


def _horizon_vs_costmap(slice_: Nav2ParamSlice) -> list[Finding]:
    """
    Upstream-documented rule (nav2_mppi_controller/README.md):

        time_steps * model_dt * vx_max <= min(width, height) / 2

    Only MPPI declares time_steps/model_dt, so this is silently inapplicable to
    other controllers.
    """
    steps = slice_.scalar("controller_time_steps")
    dt = slice_.scalar("controller_model_dt")
    width = slice_.scalar("local_costmap_width")
    height = slice_.scalar("local_costmap_height")
    v_max = slice_.by_stage(Nav2Stage.CONTROLLER).get(LimitRole.V_MAX_LINEAR)
    if None in (steps, dt, width, height, v_max):
        return []

    horizon_s = steps.value * dt.value
    reach_m = horizon_s * abs(v_max.value)
    radius_m = min(width.value, height.value) / 2
    if reach_m <= radius_m or _close(reach_m, radius_m):
        return []

    return [Finding(
        id="F-000",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.NAV2_HORIZON_EXCEEDS_COSTMAP,
        title=(
            f"MPPI prediction horizon reaches {reach_m:.3f} m beyond the "
            f"{radius_m:.3f} m local costmap radius"
        ),
        summary=(
            f"time_steps ({steps.value:g}) * model_dt ({dt.value:g} s) = "
            f"{horizon_s:.3f} s of prediction; at vx_max = {abs(v_max.value):g} m/s "
            f"that reaches {reach_m:.3f} m, while the local costmap provides only "
            f"{radius_m:.3f} m around the robot "
            f"(width {width.value:g} m x height {height.value:g} m)."
        ),
        details=(
            "This is the rule stated in the upstream nav2_mppi_controller README: "
            "when the prediction horizon at maximum speed exceeds the costmap "
            "radius, the robot is artificially limited in its maximum speed and "
            "behaviour by the costmap rather than by its own configuration. The "
            "planner is reasoning about space it has no map data for."
        ),
        related_ir_nodes=[
            "NAV2-CONTROLLER_TIME_STEPS",
            "NAV2-CONTROLLER_MODEL_DT",
            "NAV2-CONTROLLER_V_MAX_LINEAR",
            "NAV2-LOCAL_COSTMAP_WIDTH",
            "NAV2-LOCAL_COSTMAP_HEIGHT",
        ],
        source_refs=[
            _ref(v_max, slice_.path),
            _ref(steps, slice_.path),
            _ref(width, slice_.path),
        ],
        suggested_fix=(
            f"Enlarge the local costmap to at least {reach_m * 2:.2f} m square, or "
            f"reduce the horizon / vx_max so that time_steps * model_dt * vx_max "
            f"<= {radius_m:.3f} m."
        ),
    )]


def check_nav2_coherence(slice_: Optional[Nav2ParamSlice]) -> list[Finding]:
    """Run all Nav2 cross-artifact checks. Returns [] when no slice was supplied."""
    if slice_ is None:
        return []
    return _limit_coherence(slice_) + _horizon_vs_costmap(slice_)


def strict_only_categories() -> set[FindingCategory]:
    """Categories emitted only at `strict` strictness. See module docstring."""
    return {FindingCategory.NAV2_LIMIT_HEADROOM}
