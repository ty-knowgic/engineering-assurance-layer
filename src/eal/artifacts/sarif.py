"""
SARIF transformer for Engineering Assurance Layer findings.

This module only transforms canonical Finding objects into SARIF v2.1.0.
It does not run rules or solver logic.
"""

from __future__ import annotations

import json
from pathlib import Path

from eal.findings.schema import Finding, severity_rank

SARIF_FILE_NAME = "results.sarif"


_SEVERITY_TO_LEVEL = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
}


def _sarif_level(severity: str) -> str:
    return _SEVERITY_TO_LEVEL.get(severity.upper(), "note")


def _looks_like_file_path(value: str) -> bool:
    name = Path(value).name
    return "." in name and not name.startswith(".")


def _parse_source_ref(source_ref: str) -> tuple[str, int | None, int | None]:
    """
    Parse `path:line` or `path:line:column` source refs.

    Returns `(path, line, column)`. If line/column are missing, values are None.
    """
    tokens = source_ref.split(":")
    if len(tokens) >= 3 and tokens[-1].isdigit() and tokens[-2].isdigit():
        path = ":".join(tokens[:-2])
        return path or source_ref, int(tokens[-2]), int(tokens[-1])
    if len(tokens) >= 2 and tokens[-1].isdigit():
        path = ":".join(tokens[:-1])
        return path or source_ref, int(tokens[-1]), None
    if len(tokens) >= 2:
        # Handle `file:section`-style refs by preserving the file path only.
        candidate_path = ":".join(tokens[:-1])
        if _looks_like_file_path(candidate_path):
            return candidate_path, None, None
    return source_ref, None, None


def _to_sarif_location(source_ref: str) -> dict:
    path, line, column = _parse_source_ref(source_ref)
    location: dict = {
        "physicalLocation": {
            "artifactLocation": {"uri": path},
        }
    }
    if line is not None:
        region: dict = {"startLine": line}
        if column is not None:
            region["startColumn"] = column
        location["physicalLocation"]["region"] = region
    return location


def _message_text(finding: Finding) -> str:
    parts = [finding.title.strip(), finding.summary.strip()]
    if finding.details.strip():
        parts.append(finding.details.strip())
    return " ".join([p for p in parts if p])


def _rule_default_level(rule_findings: list[Finding]) -> str:
    if not rule_findings:
        return "note"
    highest = max((f.severity.value for f in rule_findings), key=severity_rank)
    return _sarif_level(highest)


def _build_rules(findings: list[Finding]) -> list[dict]:
    by_rule: dict[str, list[Finding]] = {}
    for finding in findings:
        by_rule.setdefault(finding.category.value, []).append(finding)

    rules: list[dict] = []
    for rule_id in sorted(by_rule):
        samples = by_rule[rule_id]
        exemplar = samples[0]
        rules.append(
            {
                "id": rule_id,
                "name": rule_id,
                "shortDescription": {"text": exemplar.title or rule_id},
                "fullDescription": {"text": exemplar.summary or exemplar.title or rule_id},
                "defaultConfiguration": {"level": _rule_default_level(samples)},
            }
        )
    return rules


def _build_result(finding: Finding) -> dict:
    result: dict = {
        "ruleId": finding.category.value,
        "level": _sarif_level(finding.severity.value),
        "message": {"text": _message_text(finding)},
        "properties": {
            "ealFindingId": finding.id,
            "severity": finding.severity.value,
            "related_ir_nodes": finding.related_ir_nodes,
            "evidence_refs": finding.evidence_refs,
            "source_refs": finding.source_refs,
        },
    }

    if finding.source_refs:
        result["locations"] = [_to_sarif_location(finding.source_refs[0])]
        if len(finding.source_refs) > 1:
            result["relatedLocations"] = [
                {
                    "id": idx,
                    **_to_sarif_location(source_ref),
                    "message": {"text": "Additional source reference"},
                }
                for idx, source_ref in enumerate(finding.source_refs[1:], start=1)
            ]

    return result


def build_sarif_payload(findings: list[Finding], run_id: str) -> dict:
    """Build SARIF v2.1.0 payload from canonical findings."""
    from eal import __version__

    rules = _build_rules(findings)
    results = [_build_result(finding) for finding in findings]
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "automationDetails": {"id": run_id},
                "tool": {
                    "driver": {
                        "name": "engineering-assurance-layer",
                        "version": __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def write_sarif_artifact(out_dir: Path, findings: list[Finding], run_id: str) -> str:
    """Write SARIF artifact and return artifact file name."""
    payload = build_sarif_payload(findings, run_id=run_id)
    (out_dir / SARIF_FILE_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SARIF_FILE_NAME
