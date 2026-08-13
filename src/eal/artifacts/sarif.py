"""
SARIF transformer for Engineering Assurance Layer findings.

This module only transforms canonical Finding objects into SARIF v2.1.0.
It does not run rules or solver logic.
"""

from __future__ import annotations

import json
from pathlib import Path

from eal import hazards
from eal.coverage import CoverageGap
from eal.findings.schema import Finding, severity_rank

SARIF_FILE_NAME = "results.sarif"

# Coverage gaps are emitted as SARIF results (not only as invocation
# notifications) so they are visible in code-scanning UIs, which surface
# results and routinely ignore notifications.
COVERAGE_RULE_PREFIX = "EAL_COVERAGE_"


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


def _coverage_rule_id(gap: CoverageGap) -> str:
    return f"{COVERAGE_RULE_PREFIX}{gap.category.value}"


def _build_coverage_rules(gaps: list[CoverageGap]) -> list[dict]:
    by_rule: dict[str, CoverageGap] = {}
    for gap in gaps:
        by_rule.setdefault(_coverage_rule_id(gap), gap)
    return [
        {
            "id": rule_id,
            "name": rule_id,
            "shortDescription": {"text": exemplar.title or rule_id},
            "fullDescription": {
                "text": (
                    "Analysis coverage gap: EAL was asked to analyze input it could not "
                    "fully model. Absence of findings in the affected region is not "
                    "evidence of its correctness."
                )
            },
            "defaultConfiguration": {"level": "warning"},
        }
        for rule_id, exemplar in sorted(by_rule.items())
    ]


def _build_coverage_result(gap: CoverageGap) -> dict:
    result: dict = {
        "ruleId": _coverage_rule_id(gap),
        "level": "warning",
        "message": {"text": f"{gap.title} {gap.summary}".strip()},
        "properties": {
            "ealCoverageGapId": gap.id,
            "analysisStatus": "INPUTS_NOT_FULLY_READ",
            "unanalyzed_constructs": gap.unanalyzed_constructs,
        },
    }
    if gap.affected_input:
        result["locations"] = [
            {"physicalLocation": {"artifactLocation": {"uri": gap.affected_input}}}
        ]
    return result


def build_sarif_payload(
    findings: list[Finding],
    run_id: str,
    coverage_gaps: list[CoverageGap] | None = None,
) -> dict:
    """Build SARIF v2.1.0 payload from canonical findings and coverage gaps."""
    from eal import __version__

    coverage_gaps = coverage_gaps or []
    rules = _build_rules(findings) + _build_coverage_rules(coverage_gaps)
    results = [_build_result(f) for f in findings]
    results += [_build_coverage_result(g) for g in coverage_gaps]

    invocation: dict = {
        # The tool itself ran fine; it is the analysis coverage that is partial.
        "executionSuccessful": True,
        "properties": {
            "analysisStatus": ("INPUTS_NOT_FULLY_READ" if coverage_gaps else "INPUTS_FULLY_READ"),
            "coverageGapCount": len(coverage_gaps),
            # Carried on every run, including clean ones. Emitted as invocation
            # properties rather than results: these are not findings, and adding
            # eight synthetic results per run would drown a code-scanning view.
            "uncheckedHazards": hazards.register_summary(),
        },
    }
    if coverage_gaps:
        invocation["toolExecutionNotifications"] = [
            {
                "level": "warning",
                "message": {"text": f"{g.id} — {g.title}. {g.summary}"},
                "descriptor": {"id": _coverage_rule_id(g)},
            }
            for g in coverage_gaps
        ]

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
                "invocations": [invocation],
                "results": results,
            }
        ],
    }


def write_sarif_artifact(
    out_dir: Path,
    findings: list[Finding],
    run_id: str,
    coverage_gaps: list[CoverageGap] | None = None,
) -> str:
    """Write SARIF artifact and return artifact file name."""
    payload = build_sarif_payload(findings, run_id=run_id, coverage_gaps=coverage_gaps)
    (out_dir / SARIF_FILE_NAME).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return SARIF_FILE_NAME
