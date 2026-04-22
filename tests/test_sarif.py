"""Tests for SARIF transformation from canonical findings."""

from __future__ import annotations

import json

from eal.artifacts.sarif import SARIF_FILE_NAME, build_sarif_payload, write_sarif_artifact
from eal.findings.schema import Finding, FindingCategory, FindingSeverity


def _finding(
    *,
    fid: str,
    severity: FindingSeverity,
    category: FindingCategory,
    source_refs: list[str] | None = None,
) -> Finding:
    return Finding(
        id=fid,
        severity=severity,
        category=category,
        title=f"{category.value} title",
        summary=f"{category.value} summary",
        details=f"{category.value} details",
        source_refs=source_refs or [],
        evidence_refs=["EVID-001"],
        related_ir_nodes=["NODE-001"],
        suggested_fix="Fix it.",
    )


def test_sarif_top_level_structure_and_zero_findings(tmp_path):
    payload = build_sarif_payload([], run_id="eal-test-empty")

    assert payload["version"] == "2.1.0"
    assert "runs" in payload
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["results"] == []
    assert payload["runs"][0]["tool"]["driver"]["rules"] == []

    file_name = write_sarif_artifact(tmp_path, [], run_id="eal-test-empty")
    assert file_name == SARIF_FILE_NAME
    sarif = json.loads((tmp_path / SARIF_FILE_NAME).read_text())
    assert sarif["runs"][0]["results"] == []


def test_sarif_severity_mapping():
    findings = [
        _finding(fid="F-001", severity=FindingSeverity.CRITICAL, category=FindingCategory.UNSAT_IN_MODE),
        _finding(fid="F-002", severity=FindingSeverity.HIGH, category=FindingCategory.CODE_BOUND_MISMATCH),
        _finding(fid="F-003", severity=FindingSeverity.MEDIUM, category=FindingCategory.MISSING_BOUND),
        _finding(fid="F-004", severity=FindingSeverity.LOW, category=FindingCategory.SOLVER_COUNTEREXAMPLE),
    ]
    payload = build_sarif_payload(findings, run_id="eal-test-severity")

    levels_by_id = {
        r["properties"]["ealFindingId"]: r["level"]
        for r in payload["runs"][0]["results"]
    }
    assert levels_by_id["F-001"] == "error"
    assert levels_by_id["F-002"] == "error"
    assert levels_by_id["F-003"] == "warning"
    assert levels_by_id["F-004"] == "note"


def test_sarif_source_ref_locations_and_rule_metadata():
    finding = _finding(
        fid="F-101",
        severity=FindingSeverity.HIGH,
        category=FindingCategory.CODE_TIMING_MISMATCH,
        source_refs=[
            "examples/robotics_arm/controller.py:13",
            "examples/robotics_arm/spec.md:2",
        ],
    )
    payload = build_sarif_payload([finding], run_id="eal-test-locations")
    run = payload["runs"][0]
    result = run["results"][0]

    assert result["ruleId"] == "CODE_TIMING_MISMATCH"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == (
        "examples/robotics_arm/controller.py"
    )
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 13
    assert result["relatedLocations"][0]["physicalLocation"]["artifactLocation"]["uri"] == (
        "examples/robotics_arm/spec.md"
    )
    assert result["relatedLocations"][0]["physicalLocation"]["region"]["startLine"] == 2

    rules = run["tool"]["driver"]["rules"]
    assert len(rules) == 1
    assert rules[0]["id"] == "CODE_TIMING_MISMATCH"
    assert rules[0]["defaultConfiguration"]["level"] == "error"


def test_sarif_parses_file_section_source_ref_as_file_location():
    finding = _finding(
        fid="F-102",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.TIMING_GAP,
        source_refs=["examples/robotics_arm/spec.md:Timing Constraints"],
    )
    payload = build_sarif_payload([finding], run_id="eal-test-file-section")
    location = payload["runs"][0]["results"][0]["locations"][0]
    assert location["physicalLocation"]["artifactLocation"]["uri"] == "examples/robotics_arm/spec.md"
    assert "region" not in location["physicalLocation"]
