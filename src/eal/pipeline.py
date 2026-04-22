"""
Review pipeline orchestrator.

Stages:
  1. Ingest  — load spec, model, code files
  2. Extract — build IR from spec and Python code analysis
  3. Merge   — merge model YAML into IR
  4. Rules   — run deterministic checks
  5. Solver  — run Z3-backed checks
  6. Rank    — assign stable IDs in severity order
  7. Emit    — write all artifacts
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional
from collections import Counter

from eal.artifacts import write_artifacts
from eal.code_analysis import analyze_python_code_files
from eal.extraction import extract_ir_from_spec, merge_model_into_ir
from eal.findings.schema import assign_ids, highest_severity, meets_or_exceeds_threshold
from eal.ingestion import load_code_files, load_model, load_spec
from eal.rules import RuleStrictness, run_rules_detailed
from eal.solver import run_z3_checks

logger = logging.getLogger(__name__)


def _make_run_id(spec_path: Path) -> str:
    digest = hashlib.sha1(spec_path.read_bytes()).hexdigest()[:10]
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"eal-{ts}-{digest}"


def run_review(
    spec_path: Path,
    model_path: Optional[Path],
    code_paths: list[Path],
    out_dir: Path,
    fail_on_severity: str = "NONE",
    min_severity: str = "LOW",
    strictness: str = "balanced",
) -> int:
    """
    Run a full assurance review.

    Returns:
      0 — review complete and gate passed
      2 — review complete but gate threshold exceeded
      1 — pipeline error (unrecoverable)

    Strictness:
      relaxed — suppress heuristic low-confidence rule findings
      balanced/strict — keep all currently enabled deterministic rules
    """
    try:
        logger.info("EAL review starting")
        logger.info("  spec:  %s", spec_path)
        logger.info("  model: %s", model_path or "(none)")
        logger.info("  code:  %s", code_paths or "(none)")
        logger.info("  out:   %s", out_dir)
        logger.info("  gate fail-on severity: %s", fail_on_severity)
        logger.info("  min-severity (presentation): %s", min_severity)
        logger.info("  strictness: %s", strictness)

        # ── Stage 1: Ingest ───────────────────────────────────────────────────
        spec = load_spec(spec_path)
        model = load_model(model_path) if model_path else None
        code_files = load_code_files(code_paths) if code_paths else []
        logger.info("Ingestion complete: spec=%d lines", len(spec.lines))

        # ── Stage 2: Extract IR from spec ─────────────────────────────────────
        ir = extract_ir_from_spec(spec)
        ir.code_files = [str(cf.path) for cf in code_files]
        if code_files:
            code_analysis = analyze_python_code_files(code_files)
            ir.code_constants = code_analysis.constants
            ir.code_comparisons = code_analysis.comparisons
            ir.code_evidence.extend(code_analysis.evidence)
            ir.extraction_warnings.extend(code_analysis.warnings)
            logger.info(
                "Code analysis complete: %d constants, %d comparisons, %d warning(s)",
                len(ir.code_constants), len(ir.code_comparisons), len(code_analysis.warnings),
            )
        else:
            logger.info("Code analysis skipped: no code files provided")
        logger.info(
            "Extraction complete: %d signals, %d states, %d requirements, %d constraints",
            len(ir.signals), len(ir.states), len(ir.requirements), len(ir.constraints),
        )
        for w in ir.extraction_warnings:
            logger.warning("  Extraction: %s", w)

        # ── Stage 3: Merge model ──────────────────────────────────────────────
        if model:
            merge_model_into_ir(ir, model)
            logger.info(
                "Model merged: now %d signals, %d states, %d constraints",
                len(ir.signals), len(ir.states), len(ir.constraints),
            )

        # ── Stage 4: Deterministic rules ──────────────────────────────────────
        strictness_level = RuleStrictness(strictness.lower())
        rule_result = run_rules_detailed(ir, strictness=strictness_level)
        rule_findings = rule_result.findings
        suppressed_rule_findings = rule_result.suppressed_findings
        suppressed_by_rule = Counter(f.category.value for f in suppressed_rule_findings)
        logger.info(
            "Rules: %d finding(s), %d suppressed by strictness=%s",
            len(rule_findings),
            len(suppressed_rule_findings),
            strictness_level.value,
        )

        # ── Stage 5: Z3 solver checks ─────────────────────────────────────────
        z3_findings = run_z3_checks(ir)
        logger.info("Solver: %d finding(s)", len(z3_findings))

        # ── Stage 6: Rank & ID assignment ─────────────────────────────────────
        all_findings = assign_ids(rule_findings + z3_findings)
        highest = highest_severity(all_findings)
        gate_failed = meets_or_exceeds_threshold(highest, fail_on_severity)
        exit_reason = "SEVERITY_THRESHOLD_EXCEEDED" if gate_failed else "REVIEW_COMPLETED"

        # ── Stage 7: Emit artifacts ───────────────────────────────────────────
        run_id = _make_run_id(spec_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_artifacts(
            out_dir,
            ir,
            all_findings,
            run_id,
            fail_on_severity=fail_on_severity,
            min_severity=min_severity,
            strictness=strictness_level.value,
            suppressed_finding_count=len(suppressed_rule_findings),
            suppressed_by_rule=dict(suppressed_by_rule),
            highest_severity_found=highest,
            gate_failed=gate_failed,
            exit_reason=exit_reason,
        )
        logger.info("Artifacts written to: %s", out_dir)

        return 2 if gate_failed else 0
    except Exception:
        logger.exception("EAL review failed due to pipeline/infrastructure error")
        return 1
