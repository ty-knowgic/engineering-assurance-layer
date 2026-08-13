"""
Nav2 parameter YAML ingestion.

This is the first EAL importer that reads a *real, unmodified upstream artifact*
rather than a hand-authored abstraction. It extracts the motion limits that a
Nav2 stack declares in two independent places — the controller plugin, and the
downstream `velocity_smoother` that actually clamps what reaches the base — plus
the costmap and frequency values those limits have to be consistent with.

Scope discipline: this module **extracts and records provenance only**. It makes
no judgement about whether the extracted values agree. Comparing them is a
separate concern, so that an extraction bug and a check bug cannot hide in each
other.

Verified topic chain (nav2_bringup/launch/navigation_launch.py, remappings on the
controller_server and velocity_smoother nodes):

    controller_server -> cmd_vel_nav -> velocity_smoother
        -> cmd_vel_smoothed -> collision_monitor -> cmd_vel -> base

The smoother is therefore downstream of the controller. Which side that makes
authoritative is a question for the checking layer, not for this one.

Supported controller plugins are enumerated explicitly. An unrecognised plugin
is reported as unsupported rather than guessed at: inventing a parameter-name
mapping for a plugin nobody has validated would produce confident nonsense.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from eal.ir.schema import Constraint, ConstraintType, Entity, IRSnapshot, SourceRef

ROS_PARAMS = "ros__parameters"


class LimitRole(str, Enum):
    """Role a numeric limit plays, independent of the plugin's name for it."""

    V_MAX_LINEAR = "v_max_linear"
    V_MIN_LINEAR = "v_min_linear"
    V_MAX_ANGULAR = "v_max_angular"
    A_ACCEL_LINEAR = "a_accel_linear"
    A_DECEL_LINEAR = "a_decel_linear"
    A_ACCEL_ANGULAR = "a_accel_angular"


_ROLE_UNITS: dict[LimitRole, str] = {
    LimitRole.V_MAX_LINEAR: "m/s",
    LimitRole.V_MIN_LINEAR: "m/s",
    LimitRole.V_MAX_ANGULAR: "rad/s",
    LimitRole.A_ACCEL_LINEAR: "m/s^2",
    LimitRole.A_DECEL_LINEAR: "m/s^2",
    LimitRole.A_ACCEL_ANGULAR: "rad/s^2",
}

# Controller plugin -> {role: parameter name}.
#
# Each mapping below is validated against a real upstream params file in
# tests/fixtures/nav2_upstream_params/. Do not add a plugin here without a real
# file to validate it against — see module docstring.
CONTROLLER_LIMIT_PARAMS: dict[str, dict[LimitRole, str]] = {
    "nav2_mppi_controller::MPPIController": {
        LimitRole.V_MAX_LINEAR: "vx_max",
        LimitRole.V_MIN_LINEAR: "vx_min",
        LimitRole.V_MAX_ANGULAR: "wz_max",
        LimitRole.A_ACCEL_LINEAR: "ax_max",
        LimitRole.A_DECEL_LINEAR: "ax_min",
        LimitRole.A_ACCEL_ANGULAR: "az_max",
    },
    "dwb_core::DWBLocalPlanner": {
        LimitRole.V_MAX_LINEAR: "max_vel_x",
        LimitRole.V_MIN_LINEAR: "min_vel_x",
        LimitRole.V_MAX_ANGULAR: "max_vel_theta",
        LimitRole.A_ACCEL_LINEAR: "acc_lim_x",
        LimitRole.A_DECEL_LINEAR: "decel_lim_x",
        LimitRole.A_ACCEL_ANGULAR: "acc_lim_theta",
    },
}

# velocity_smoother stores limits as [x, y, theta] vectors.
SMOOTHER_LIMIT_PARAMS: dict[LimitRole, tuple[str, int]] = {
    LimitRole.V_MAX_LINEAR: ("max_velocity", 0),
    LimitRole.V_MIN_LINEAR: ("min_velocity", 0),
    LimitRole.V_MAX_ANGULAR: ("max_velocity", 2),
    LimitRole.A_ACCEL_LINEAR: ("max_accel", 0),
    LimitRole.A_DECEL_LINEAR: ("max_decel", 0),
    LimitRole.A_ACCEL_ANGULAR: ("max_accel", 2),
}

# Units that make a value a timing parameter rather than a bound.
_TIMING_UNITS = {"s", "Hz"}

# Scalars that are not motion limits but that limit checks depend on.
_CONTROLLER_SCALARS = {"controller_frequency": "Hz", "costmap_update_timeout": "s"}
_PLUGIN_SCALARS = {"time_steps": "count", "model_dt": "s"}
_COSTMAP_SCALARS = {
    "update_frequency": "Hz",
    "width": "m",
    "height": "m",
    "resolution": "m",
    "robot_radius": "m",
}
_INFLATION_SCALARS = {"inflation_radius": "m", "cost_scaling_factor": "dimensionless"}
_OBSERVATION_SCALARS = {
    "obstacle_max_range": "m",
    "obstacle_min_range": "m",
    "raytrace_max_range": "m",
}


class Nav2Stage(str, Enum):
    """Where in the cmd_vel chain (or supporting config) a value was declared."""

    CONTROLLER = "controller"
    SMOOTHER = "smoother"
    LOCAL_COSTMAP = "local_costmap"


class Nav2Value(BaseModel):
    """One numeric value read from the file, with the path it was read from."""

    name: str = Field(description="Role-qualified stable name, e.g. controller_v_max_linear")
    value: float
    unit: str
    yaml_path: str = Field(description="Dotted path within the source YAML")
    stage: Nav2Stage
    param_name: str = Field(description="Native parameter name in the source file")
    role: Optional[LimitRole] = None
    plugin: Optional[str] = None

    @property
    def raw_text(self) -> str:
        return f"{self.param_name}: {self.value}"


class Nav2ParamSlice(BaseModel):
    """Deterministic extraction result for one Nav2 parameter file."""

    path: str
    controller_plugin: Optional[str] = None
    controller_plugin_key: Optional[str] = None
    values: list[Nav2Value] = Field(default_factory=list)
    unsupported_constructs: list[str] = Field(default_factory=list)
    absent_sections: list[str] = Field(default_factory=list)

    def by_stage(self, stage: Nav2Stage) -> dict[LimitRole, Nav2Value]:
        return {v.role: v for v in self.values if v.stage is stage and v.role is not None}

    def scalar(self, name: str) -> Optional[Nav2Value]:
        return next((v for v in self.values if v.name == name), None)


# ── Parsing helpers ───────────────────────────────────────────────────────────

def _params_of(doc: dict, node: str) -> dict:
    section = doc.get(node)
    if not isinstance(section, dict):
        return {}
    params = section.get(ROS_PARAMS)
    return params if isinstance(params, dict) else {}


def _nested_costmap_params(doc: dict, node: str) -> dict:
    """local_costmap is nested twice: local_costmap.local_costmap.ros__parameters."""
    outer = doc.get(node)
    if not isinstance(outer, dict):
        return {}
    inner = outer.get(node)
    if not isinstance(inner, dict):
        return {}
    params = inner.get(ROS_PARAMS)
    return params if isinstance(params, dict) else {}


def _as_number(value: Any) -> Optional[float]:
    """Accept ints/floats only. Bools are ints in Python and must be rejected."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _collect_scalars(
    params: dict,
    wanted: dict[str, str],
    *,
    stage: Nav2Stage,
    prefix: str,
    yaml_prefix: str,
) -> list[Nav2Value]:
    out: list[Nav2Value] = []
    for param_name, unit in wanted.items():
        number = _as_number(params.get(param_name))
        if number is None:
            continue
        out.append(Nav2Value(
            name=f"{prefix}_{param_name}",
            value=number,
            unit=unit,
            yaml_path=f"{yaml_prefix}.{param_name}",
            stage=stage,
            param_name=param_name,
        ))
    return out


def parse_nav2_params(path: Path) -> Nav2ParamSlice:
    """Parse a Nav2 parameter YAML into a deterministic extraction slice."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc = raw if isinstance(raw, dict) else {}
    values: list[Nav2Value] = []
    unsupported: list[str] = []
    absent: list[str] = []

    # ── controller_server ─────────────────────────────────────────────────────
    controller = _params_of(doc, "controller_server")
    plugin: Optional[str] = None
    plugin_key: Optional[str] = None
    if not controller:
        absent.append("controller_server")
    else:
        base = f"controller_server.{ROS_PARAMS}"
        values += _collect_scalars(
            controller, _CONTROLLER_SCALARS,
            stage=Nav2Stage.CONTROLLER, prefix="controller", yaml_prefix=base,
        )
        # The plugin's config key is itself configurable; read it rather than
        # assuming the conventional "FollowPath".
        plugin_keys = controller.get("controller_plugins")
        candidates = [k for k in plugin_keys if isinstance(k, str)] if isinstance(plugin_keys, list) else []
        for key in candidates:
            block = controller.get(key)
            if isinstance(block, dict) and isinstance(block.get("plugin"), str):
                plugin_key, plugin = key, block["plugin"]
                break

        if plugin is None:
            absent.append("controller_server.controller_plugins[].plugin")
        elif plugin not in CONTROLLER_LIMIT_PARAMS:
            unsupported.append(f"controller plugin {plugin}")
        else:
            block = controller[plugin_key]
            pbase = f"{base}.{plugin_key}"
            for role, param_name in CONTROLLER_LIMIT_PARAMS[plugin].items():
                number = _as_number(block.get(param_name))
                if number is None:
                    continue
                values.append(Nav2Value(
                    name=f"controller_{role.value}",
                    value=number,
                    unit=_ROLE_UNITS[role],
                    yaml_path=f"{pbase}.{param_name}",
                    stage=Nav2Stage.CONTROLLER,
                    param_name=param_name,
                    role=role,
                    plugin=plugin,
                ))
            values += _collect_scalars(
                block, _PLUGIN_SCALARS,
                stage=Nav2Stage.CONTROLLER, prefix="controller", yaml_prefix=pbase,
            )

    # ── velocity_smoother ─────────────────────────────────────────────────────
    smoother = _params_of(doc, "velocity_smoother")
    if not smoother:
        absent.append("velocity_smoother")
    else:
        base = f"velocity_smoother.{ROS_PARAMS}"
        for role, (param_name, index) in SMOOTHER_LIMIT_PARAMS.items():
            vector = smoother.get(param_name)
            if not isinstance(vector, list) or len(vector) <= index:
                continue
            number = _as_number(vector[index])
            if number is None:
                continue
            values.append(Nav2Value(
                name=f"smoother_{role.value}",
                value=number,
                unit=_ROLE_UNITS[role],
                yaml_path=f"{base}.{param_name}[{index}]",
                stage=Nav2Stage.SMOOTHER,
                param_name=f"{param_name}[{index}]",
                role=role,
            ))

    # ── local_costmap ─────────────────────────────────────────────────────────
    costmap = _nested_costmap_params(doc, "local_costmap")
    if not costmap:
        absent.append("local_costmap")
    else:
        base = f"local_costmap.local_costmap.{ROS_PARAMS}"
        values += _collect_scalars(
            costmap, _COSTMAP_SCALARS,
            stage=Nav2Stage.LOCAL_COSTMAP, prefix="local_costmap", yaml_prefix=base,
        )
        layer_names = costmap.get("plugins")
        layers = [n for n in layer_names if isinstance(n, str)] if isinstance(layer_names, list) else []
        for layer_name in layers:
            layer = costmap.get(layer_name)
            if not isinstance(layer, dict):
                continue
            lbase = f"{base}.{layer_name}"
            values += _collect_scalars(
                layer, _INFLATION_SCALARS,
                stage=Nav2Stage.LOCAL_COSTMAP, prefix="local_costmap", yaml_prefix=lbase,
            )
            # Observation sources carry the sensor marking range, which upper-bounds
            # the distance at which an obstacle can enter the costmap at all.
            sources_raw = layer.get("observation_sources")
            if isinstance(sources_raw, str):
                sources = sources_raw.split()
            elif isinstance(sources_raw, list):
                sources = [s for s in sources_raw if isinstance(s, str)]
            else:
                sources = []
            for source in sources:
                block = layer.get(source)
                if not isinstance(block, dict):
                    continue
                values += _collect_scalars(
                    block, _OBSERVATION_SCALARS,
                    stage=Nav2Stage.LOCAL_COSTMAP,
                    prefix=f"local_costmap_{source}",
                    yaml_prefix=f"{lbase}.{source}",
                )

    return Nav2ParamSlice(
        path=str(path),
        controller_plugin=plugin,
        controller_plugin_key=plugin_key,
        values=values,
        unsupported_constructs=unsupported,
        absent_sections=absent,
    )


# ── IR contribution ───────────────────────────────────────────────────────────

def merge_nav2_slice_into_ir(ir: IRSnapshot, slice_: Nav2ParamSlice) -> int:
    """
    Add extracted Nav2 values to the IR as provenance-carrying constraints.

    Each value keeps the exact YAML path it came from, so a downstream finding
    can name the line a human has to go edit. Returns the number added.
    """
    if not any(e.name == "nav2_stack" for e in ir.entities):
        ir.entities.append(Entity(
            name="nav2_stack",
            description=(
                f"Nav2 configuration imported from {Path(slice_.path).name}"
                + (f" (controller: {slice_.controller_plugin})" if slice_.controller_plugin else "")
            ),
            source_ref=SourceRef(file=slice_.path),
        ))

    existing = {c.id for c in ir.constraints}
    added = 0
    for value in slice_.values:
        cid = f"NAV2-{value.name.upper()}"
        if cid in existing:
            continue
        ir.constraints.append(Constraint(
            id=cid,
            expression_text=f"{value.name} = {value.value} {value.unit}",
            # Rates and durations are timing parameters, not bounds. Typing them
            # correctly is what lets timing rules see that the config does
            # declare them.
            constraint_type=(
                ConstraintType.TIMING if value.unit in _TIMING_UNITS
                else ConstraintType.BOUND
            ),
            applies_globally=True,
            numeric_value=value.value,
            operator="==",
            source_ref=SourceRef(
                file=slice_.path,
                section=value.yaml_path,
                raw_text=value.raw_text,
            ),
        ))
        existing.add(cid)
        added += 1
    return added
