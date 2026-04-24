"""Tests for narrow BehaviorTree XML ingestion."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from eal.cli import app
from eal.ingestion.behaviortree_xml import bt_xml_slice_to_model_data, parse_bt_xml

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
runner = CliRunner()


def test_parse_supported_bt_nodes(tmp_path):
    xml = tmp_path / "tree.xml"
    xml.write_text(
        """
<root main_tree_to_execute="MainTree">
  <BehaviorTree ID="MainTree">
    <Fallback name="TryWithRecovery">
      <Sequence name="Nominal">
        <Precondition condition="battery_ok == true">
          <Action ID="NavigateToPose"/>
        </Precondition>
      </Sequence>
      <Action ID="RecoverySpin"/>
    </Fallback>
  </BehaviorTree>
</root>
""",
        encoding="utf-8",
    )

    bt = parse_bt_xml(xml)

    assert {leaf.name for leaf in bt.leaves} == {"NavigateToPose", "RecoverySpin"}
    assert bt.preconditions[0].expression == "battery_ok == true"
    assert bt.preconditions[0].target == "NavigateToPose"
    assert bt.fallbacks[0].name == "TryWithRecovery"
    assert bt.fallbacks[0].primary == "NavigateToPose"
    assert bt.fallbacks[0].alternates == ("RecoverySpin",)


def test_extract_timeout_values_from_bt_xml(tmp_path):
    xml = tmp_path / "tree.xml"
    xml.write_text(
        """
<root>
  <BehaviorTree ID="MainTree">
    <Timeout msec="250">
      <Action ID="DockRobot"/>
    </Timeout>
  </BehaviorTree>
</root>
""",
        encoding="utf-8",
    )

    bt = parse_bt_xml(xml)
    data = bt_xml_slice_to_model_data(bt)

    assert bt.timeouts[0].msec == 250
    assert bt.timeouts[0].target == "DockRobot"
    assert data["parameters"]["bt_timeout_dock_robot_ms"] == 250


def test_extract_condition_leaves_as_guard_assumptions():
    bt = parse_bt_xml(EXAMPLES / "behaviortree_timeout_precondition" / "tree.xml")
    data = bt_xml_slice_to_model_data(bt)

    signal_names = {entry["name"] for entry in data["signals"]}
    assumption_text = "\n".join(data["assumptions"])

    assert {"battery_ok", "localization_ready", "goal_requested"} <= signal_names
    assert "battery_ok" in assumption_text
    assert "localization_ready" in assumption_text
    assert "BT Fallback" in assumption_text


def test_bt_xml_native_ingestion_end_to_end(tmp_path):
    out_dir = tmp_path / "bt_native"
    result = runner.invoke(app, [
        "review",
        "--spec", str(EXAMPLES / "behaviortree_timeout_precondition" / "spec.md"),
        "--bt-xml", str(EXAMPLES / "behaviortree_timeout_precondition" / "tree.xml"),
        "--fail-on-severity", "HIGH",
        "--out", str(out_dir),
    ])

    assert result.exit_code == 0, result.output
    findings = json.loads((out_dir / "findings.json").read_text())["findings"]
    categories = {f["category"] for f in findings}
    ir = json.loads((out_dir / "ir_snapshot.json").read_text())
    params = {
        c["id"]: c
        for c in ir["constraints"]
        if c["id"].startswith("PARAM-BT_TIMEOUT_NAVIGATE_TO_POSE_MS")
    }

    assert "TIMING_GAP" not in categories
    assert "FORBIDDEN_UNCHECKED" not in categories
    assert params
    assert next(iter(params.values()))["numeric_value"] == 100.0
