"""
Artifact writer for Engineering Assurance Layer.

Writes all required review artifacts to the output directory.
All artifacts are always written — empty content gets an explicit status marker.

Outputs:
  review_summary.md        — human-readable summary
  constraint_violations.md — all CRITICAL/HIGH findings in detail
  missing_assumptions.md   — MISSING_ASSUMPTION findings
  counterexamples.json     — machine-readable counterexamples
  review_evidence.json     — evidence model (reused from Synthetic Danger pattern)
  ir_snapshot.json         — full IR dump
  findings.json            — all findings (stable schema)
  results.sarif            — SARIF v2.1.0 output derived from findings
  report.html              — simple HTML report
  run_metadata.json        — run provenance
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from eal.findings.schema import (
    Finding,
    FindingCategory,
    FindingSeverity,
    meets_or_exceeds_threshold,
)
from eal.ir.schema import IRSnapshot
from eal.artifacts.sarif import write_sarif_artifact


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_info() -> dict:
    info: dict = {"available": False}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info = {"available": True, "commit": commit, "branch": branch}
    except Exception:
        pass
    return info


def _severity_icon(sev: FindingSeverity) -> str:
    return {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(sev.value, "⚪")


def _findings_by_severity(findings: list[Finding]) -> dict[str, list[Finding]]:
    buckets: dict[str, list[Finding]] = {s.value: [] for s in FindingSeverity}
    for f in findings:
        buckets[f.severity.value].append(f)
    return buckets


# ── Individual artifact writers ───────────────────────────────────────────────

def _write_review_summary(
    out: Path,
    ir: IRSnapshot,
    findings: list[Finding],
    run_id: str,
    spec_file: str,
    fail_on_severity: str,
    min_severity: str,
    strictness: str,
    policy_profile: str,
    policy_sources: dict[str, str],
    suppressed_finding_count: int,
    highest_severity_found: str,
    gate_failed: bool,
    sarif_file: str,
) -> None:
    by_sev = _findings_by_severity(findings)
    critical = len(by_sev["CRITICAL"])
    high = len(by_sev["HIGH"])
    medium = len(by_sev["MEDIUM"])
    low = len(by_sev["LOW"])

    review_status = "PASS" if critical == 0 and high == 0 else "REVIEW REQUIRED"
    gate_status = "FAIL" if gate_failed else "PASS"
    displayed_findings = [
        f for f in findings if meets_or_exceeds_threshold(f.severity.value, min_severity)
    ]

    lines = [
        "# Engineering Assurance Review Summary",
        "",
        f"**Run ID:** `{run_id}`",
        f"**Spec:** `{spec_file}`",
        f"**Generated:** {_now_iso()}",
        f"**Review status:** {'✅ ' if review_status == 'PASS' else '❌ '}{review_status}",
        f"**Highest severity found:** `{highest_severity_found}`",
        f"**Gate threshold:** `{fail_on_severity}`",
        f"**Gate result:** {'✅ PASS' if gate_status == 'PASS' else '❌ FAIL'}",
        f"**Policy profile:** `{policy_profile}`",
        f"**Presentation minimum severity:** `{min_severity}`",
        f"**Rule strictness:** `{strictness}`",
        f"**Policy source map:** `{json.dumps(policy_sources, sort_keys=True)}`",
        f"**Strictness-suppressed findings:** `{suppressed_finding_count}`",
        f"**SARIF artifact:** `{sarif_file}`",
        "",
        "## Findings Overview",
        "",
        f"| Severity | Count |",
        f"|----------|-------|",
        f"| 🔴 CRITICAL | {critical} |",
        f"| 🟠 HIGH     | {high} |",
        f"| 🟡 MEDIUM   | {medium} |",
        f"| 🔵 LOW      | {low} |",
        f"| **Total**   | **{len(findings)}** |",
        "",
        "## IR Extraction Summary",
        "",
        f"- Signals: {len(ir.signals)}",
        f"- States: {len(ir.states)}",
        f"- Modes: {len(ir.modes)}",
        f"- Transitions: {len(ir.transitions)}",
        f"- Requirements: {len(ir.requirements)}",
        f"- Constraints: {len(ir.constraints)}",
        f"- Assumptions: {len(ir.assumptions)}",
        f"- Code files analyzed: {len(ir.code_files)}",
        f"- Code constants extracted: {len(ir.code_constants)}",
        f"- Code comparisons extracted: {len(ir.code_comparisons)}",
    ]

    if ir.extraction_warnings:
        lines += ["", "## Extraction Warnings", ""]
        for w in ir.extraction_warnings:
            lines.append(f"- ⚠️  {w}")

    if displayed_findings:
        lines += ["", "## Top Findings", ""]
        lines.append(
            f"_Showing findings at or above `{min_severity}` "
            f"({len(displayed_findings)} of {len(findings)} total)._"
        )
        lines.append("")
        for f in displayed_findings[:10]:
            lines.append(f"- {_severity_icon(f.severity)} **{f.id}** [{f.category.value}] {f.title}")
    else:
        lines += [
            "",
            f"_No findings at or above `{min_severity}` "
            f"({len(findings)} total findings exist)._",
        ]

    (out / "review_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_constraint_violations(out: Path, findings: list[Finding]) -> None:
    violations = [f for f in findings if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)]
    lines = ["# Constraint Violations", ""]

    if not violations:
        lines.append("_No CRITICAL or HIGH findings._")
    else:
        for f in violations:
            lines += [
                f"## {f.id} — {f.title}",
                "",
                f"**Severity:** {_severity_icon(f.severity)} {f.severity.value}  ",
                f"**Category:** {f.category.value}  ",
                "",
                f"**Summary:** {f.summary}",
                "",
            ]
            if f.details:
                lines += [f"**Details:** {f.details}", ""]
            if f.related_ir_nodes:
                lines += [f"**Related IR nodes:** {', '.join(f.related_ir_nodes)}", ""]
            if f.source_refs:
                lines += [f"**Source refs:** {', '.join(f.source_refs)}", ""]
            if f.suggested_fix:
                lines += [f"**Suggested fix:** {f.suggested_fix}", ""]
            if f.counterexample:
                lines += [
                    "**Counterexample:**",
                    "```json",
                    json.dumps(f.counterexample, indent=2),
                    "```",
                    "",
                ]
            lines.append("---")
            lines.append("")

    (out / "constraint_violations.md").write_text("\n".join(lines), encoding="utf-8")


def _write_missing_assumptions(out: Path, findings: list[Finding]) -> None:
    asm_findings = [f for f in findings if f.category == FindingCategory.MISSING_ASSUMPTION]
    lines = ["# Missing Assumptions", ""]

    if not asm_findings:
        lines.append("_No missing assumption findings._")
    else:
        for f in asm_findings:
            lines += [
                f"## {f.id} — {f.title}",
                "",
                f"**Summary:** {f.summary}",
                "",
                f"**Suggested fix:** {f.suggested_fix}",
                "",
                "---",
                "",
            ]

    (out / "missing_assumptions.md").write_text("\n".join(lines), encoding="utf-8")


def _write_counterexamples(out: Path, findings: list[Finding]) -> None:
    examples = [
        {
            "finding_id": f.id,
            "severity": f.severity.value,
            "category": f.category.value,
            "title": f.title,
            "counterexample": f.counterexample,
        }
        for f in findings
        if f.counterexample is not None
    ]
    payload = {
        "counterexample_count": len(examples),
        "status": "none" if not examples else "counterexamples_found",
        "counterexamples": examples,
    }
    (out / "counterexamples.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _write_review_evidence(
    out: Path,
    ir: IRSnapshot,
    run_id: str,
    spec_file: str,
    sarif_file: str,
) -> None:
    payload = {
        "run_id": run_id,
        "generated_at": _now_iso(),
        "inputs": {
            "spec_file": spec_file,
            "model_file": ir.model_file,
            "code_files": ir.code_files,
        },
        "ir_summary": {
            "signals": len(ir.signals),
            "states": len(ir.states),
            "modes": len(ir.modes),
            "transitions": len(ir.transitions),
            "requirements": len(ir.requirements),
            "constraints": len(ir.constraints),
            "assumptions": len(ir.assumptions),
            "code_constants": len(ir.code_constants),
            "code_comparisons": len(ir.code_comparisons),
            "code_evidence": len(ir.code_evidence),
            "extraction_warnings": len(ir.extraction_warnings),
        },
        "code_analysis": {
            "analyzed_files": ir.code_files,
            "constants_extracted": len(ir.code_constants),
            "comparisons_extracted": len(ir.code_comparisons),
            "evidence_items": len(ir.code_evidence),
        },
        "artifacts": {
            "sarif": {
                "generated": True,
                "file": sarif_file,
            }
        },
        "git": _git_info(),
    }
    (out / "review_evidence.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _write_ir_snapshot(out: Path, ir: IRSnapshot) -> None:
    (out / "ir_snapshot.json").write_text(
        json.dumps(ir.extra_model_fields(), indent=2), encoding="utf-8"
    )


def _write_findings(out: Path, findings: list[Finding]) -> None:
    payload = {
        "finding_count": len(findings),
        "status": "no_findings" if not findings else "findings_present",
        "findings": [f.model_dump(mode="json") for f in findings],
    }
    (out / "findings.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _write_html_report(out: Path, ir: IRSnapshot, findings: list[Finding], run_id: str) -> None:
    by_sev = _findings_by_severity(findings)
    critical = len(by_sev["CRITICAL"])
    high = len(by_sev["HIGH"])
    medium = len(by_sev["MEDIUM"])
    low = len(by_sev["LOW"])

    status_color = "#d32f2f" if (critical or high) else "#2e7d32"
    status_text = "REVIEW REQUIRED" if (critical or high) else "PASS"

    def sev_badge(sev: str) -> str:
        colors = {"CRITICAL": "#d32f2f", "HIGH": "#f57c00", "MEDIUM": "#fbc02d", "LOW": "#1976d2"}
        return (
            f'<span style="background:{colors.get(sev,"#888")};color:white;'
            f'padding:2px 8px;border-radius:4px;font-size:0.85em">{sev}</span>'
        )

    rows = ""
    for f in findings:
        ce = f"<br><code>{json.dumps(f.counterexample)}</code>" if f.counterexample else ""
        rows += (
            f"<tr>"
            f"<td>{f.id}</td>"
            f"<td>{sev_badge(f.severity.value)}</td>"
            f"<td>{f.category.value}</td>"
            f"<td><strong>{f.title}</strong><br>{f.summary}{ce}</td>"
            f"<td>{f.suggested_fix}</td>"
            f"</tr>\n"
        )
    findings_table_html = "<p><em>No findings.</em></p>"
    if findings:
        findings_table_html = (
            "<table>\n"
            "<tr><th>ID</th><th>Severity</th><th>Category</th><th>Finding</th><th>Suggested Fix</th></tr>\n"
            f"{rows}"
            "</table>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>EAL Review Report — {run_id}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ color: #1a1a2e; }} h2 {{ color: #16213e; border-bottom: 1px solid #eee; }}
  .status {{ font-size: 1.4em; font-weight: bold; color: {status_color}; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #16213e; color: white; padding: 8px 12px; text-align: left; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; font-size: 0.9em; }}
  tr:nth-child(even) {{ background: #f9f9f9; }}
  .stat {{ display: inline-block; margin: 0.5rem 1rem; padding: 0.5rem 1rem;
           background: #f0f4f8; border-radius: 6px; text-align: center; }}
  .stat strong {{ display: block; font-size: 1.5em; }}
</style>
</head>
<body>
<h1>Engineering Assurance Review</h1>
<p>Run ID: <code>{run_id}</code> &nbsp;|&nbsp; Generated: {_now_iso()}</p>
<p class="status">{status_text}</p>

<h2>Summary</h2>
<div class="stat"><strong style="color:#d32f2f">{critical}</strong>CRITICAL</div>
<div class="stat"><strong style="color:#f57c00">{high}</strong>HIGH</div>
<div class="stat"><strong style="color:#fbc02d">{medium}</strong>MEDIUM</div>
<div class="stat"><strong style="color:#1976d2">{low}</strong>LOW</div>

<h2>IR Extraction</h2>
<p>Signals: {len(ir.signals)} &nbsp;|&nbsp; States: {len(ir.states)} &nbsp;|&nbsp;
Modes: {len(ir.modes)} &nbsp;|&nbsp; Requirements: {len(ir.requirements)} &nbsp;|&nbsp;
Constraints: {len(ir.constraints)} &nbsp;|&nbsp; Assumptions: {len(ir.assumptions)}</p>

<h2>Findings ({len(findings)})</h2>
{findings_table_html}

</body>
</html>"""
    (out / "report.html").write_text(html, encoding="utf-8")


def _write_run_metadata(
    out: Path,
    run_id: str,
    spec_file: str,
    model_file: Optional[str],
    code_files: list[str],
    finding_count: int,
    highest_severity_found: str,
    low_count: int,
    medium_count: int,
    critical_count: int,
    high_count: int,
    fail_on_severity: str,
    min_severity: str,
    strictness: str,
    policy_profile: str,
    policy_sources: dict[str, str],
    suppressed_finding_count: int,
    suppressed_by_rule: dict[str, int],
    gate_failed: bool,
    exit_reason: str,
    sarif_file: str,
) -> None:
    from eal import __version__
    payload = {
        "run_id": run_id,
        "eal_version": __version__,
        "generated_at": _now_iso(),
        "inputs": {
            "spec_file": spec_file,
            "model_file": model_file,
            "code_files": code_files,
        },
        "results": {
            "finding_count": finding_count,
            "highest_severity_found": highest_severity_found,
            "low_count": low_count,
            "medium_count": medium_count,
            "critical_count": critical_count,
            "high_count": high_count,
            "status": "REVIEW_REQUIRED" if (critical_count or high_count) else "PASS",
        },
        "gate": {
            "fail_on_severity": fail_on_severity,
            "min_severity": min_severity,
            "failed": gate_failed,
            "result": "FAIL" if gate_failed else "PASS",
            "exit_reason": exit_reason,
        },
        "policy": {
            "profile": policy_profile,
            "effective": {
                "fail_on_severity": fail_on_severity,
                "min_severity": min_severity,
                "strictness": strictness,
            },
            "sources": policy_sources,
            "notes": "Precedence: explicit CLI flags override selected policy profile defaults.",
        },
        "strictness": {
            "level": strictness,
            "suppressed_finding_count": suppressed_finding_count,
            "suppressed_by_rule": suppressed_by_rule,
            "notes": "Strictness filtering applies to heuristic rules only; solver and always-on deterministic rules are unaffected.",
        },
        "artifacts": {
            "sarif": {
                "generated": True,
                "file": sarif_file,
            }
        },
        "git": _git_info(),
    }
    (out / "run_metadata.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def write_artifacts(
    out_dir: Path,
    ir: IRSnapshot,
    findings: list[Finding],
    run_id: str,
    fail_on_severity: str = "NONE",
    min_severity: str = "LOW",
    strictness: str = "balanced",
    policy_profile: str = "local",
    policy_sources: Optional[dict[str, str]] = None,
    suppressed_finding_count: int = 0,
    suppressed_by_rule: Optional[dict[str, int]] = None,
    highest_severity_found: str = "NONE",
    gate_failed: bool = False,
    exit_reason: str = "REVIEW_COMPLETED",
) -> None:
    """Write all review artifacts to out_dir. Directory must already exist."""
    out_dir.mkdir(parents=True, exist_ok=True)

    by_sev = _findings_by_severity(findings)
    spec_file = ir.spec_file
    sarif_file = write_sarif_artifact(out_dir, findings, run_id)

    _write_review_summary(
        out_dir,
        ir,
        findings,
        run_id,
        spec_file,
        fail_on_severity=fail_on_severity,
        min_severity=min_severity,
        strictness=strictness,
        policy_profile=policy_profile,
        policy_sources=policy_sources or {},
        suppressed_finding_count=suppressed_finding_count,
        highest_severity_found=highest_severity_found,
        gate_failed=gate_failed,
        sarif_file=sarif_file,
    )
    _write_constraint_violations(out_dir, findings)
    _write_missing_assumptions(out_dir, findings)
    _write_counterexamples(out_dir, findings)
    _write_review_evidence(out_dir, ir, run_id, spec_file, sarif_file=sarif_file)
    _write_ir_snapshot(out_dir, ir)
    _write_findings(out_dir, findings)
    _write_html_report(out_dir, ir, findings, run_id)
    _write_run_metadata(
        out_dir,
        run_id=run_id,
        spec_file=spec_file,
        model_file=ir.model_file,
        code_files=ir.code_files,
        finding_count=len(findings),
        highest_severity_found=highest_severity_found,
        low_count=len(by_sev["LOW"]),
        medium_count=len(by_sev["MEDIUM"]),
        critical_count=len(by_sev["CRITICAL"]),
        high_count=len(by_sev["HIGH"]),
        fail_on_severity=fail_on_severity,
        min_severity=min_severity,
        strictness=strictness,
        policy_profile=policy_profile,
        policy_sources=policy_sources or {},
        suppressed_finding_count=suppressed_finding_count,
        suppressed_by_rule=suppressed_by_rule or {},
        gate_failed=gate_failed,
        exit_reason=exit_reason,
        sarif_file=sarif_file,
    )
