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
from eal.coverage import analysis_status, detect_coverage_gaps
from eal.extraction import extract_ir_from_spec, merge_model_into_ir
from eal.findings.schema import assign_ids, highest_severity, meets_or_exceeds_threshold
from eal.ingestion import (
    load_bt_xml_model,
    load_code_files,
    load_model,
    load_spec,
    merge_nav2_slice_into_ir,
    parse_nav2_params,
)
from eal.rules import (
    RuleStrictness,
    check_nav2_coherence,
    run_rules_detailed,
    strict_only_categories,
)
from eal.solver import run_z3_checks

logger = logging.getLogger(__name__)


def _ir_content_counts(ir) -> tuple[int, ...]:
    """Countable IR content, used to measure what an input actually contributed."""
    return (
        len(ir.signals), len(ir.states), len(ir.modes), len(ir.transitions),
        len(ir.constraints), len(ir.assumptions), len(ir.requirements),
    )


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
    bt_xml_path: Optional[Path] = None,
    nav2_params_path: Optional[Path] = None,
    fail_on_severity: str = "NONE",
    min_severity: str = "LOW",
    strictness: str = "balanced",
    policy_profile: str = "local",
    policy_sources: Optional[dict[str, str]] = None,
    fail_on_unknown: bool = True,
) -> int:
    """
    Run a full assurance review.

    Returns:
      0 — review complete and gate passed
      2 — review complete but gate threshold exceeded
      3 — analysis coverage incomplete (UNKNOWN) and policy blocks on UNKNOWN
      1 — pipeline error (unrecoverable)

    Exit code 3 takes precedence over 2: if EAL could not analyze part of the
    input, the severity verdict it produced is not trustworthy enough to be the
    headline result.

    Strictness:
      relaxed — suppress heuristic low-confidence rule findings
      balanced/strict — keep all currently enabled deterministic rules
    """
    try:
        logger.info("EAL review starting")
        logger.info("  spec:  %s", spec_path)
        logger.info("  model: %s", model_path or "(none)")
        logger.info("  bt xml: %s", bt_xml_path or "(none)")
        logger.info("  nav2 params: %s", nav2_params_path or "(none)")
        logger.info("  code:  %s", code_paths or "(none)")
        logger.info("  out:   %s", out_dir)
        logger.info("  gate fail-on severity: %s", fail_on_severity)
        logger.info("  min-severity (presentation): %s", min_severity)
        logger.info("  strictness: %s", strictness)
        logger.info("  policy profile: %s", policy_profile)

        # ── Stage 1: Ingest ───────────────────────────────────────────────────
        spec = load_spec(spec_path)
        model = load_model(model_path) if model_path else None
        bt_xml_model = load_bt_xml_model(bt_xml_path) if bt_xml_path else None
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
        # Contribution is measured as a before/after IR delta rather than trusted
        # from the loader: an input that parses cleanly but adds nothing is
        # exactly the case that used to produce a silent PASS.
        model_contributed = True
        bt_contributed = True
        bt_unsupported: list[str] = []

        if model:
            before = _ir_content_counts(ir)
            merge_model_into_ir(ir, model)
            model_contributed = _ir_content_counts(ir) != before
            logger.info(
                "Model merged: now %d signals, %d states, %d constraints (contributed=%s)",
                len(ir.signals), len(ir.states), len(ir.constraints), model_contributed,
            )
        if bt_xml_model:
            before = _ir_content_counts(ir)
            merge_model_into_ir(ir, bt_xml_model)
            bt_contributed = _ir_content_counts(ir) != before
            bt_unsupported = list(bt_xml_model.data.get("unsupported_bt_nodes", []))
            if bt_unsupported:
                ir.extraction_warnings.append(
                    "BT XML importer ignored unsupported node(s): " + ", ".join(bt_unsupported)
                )
            logger.info(
                "BT XML merged: now %d signals, %d states, %d constraints, %d assumptions "
                "(contributed=%s, unsupported=%d)",
                len(ir.signals), len(ir.states), len(ir.constraints), len(ir.assumptions),
                bt_contributed, len(bt_unsupported),
            )

        # ── Stage 3b: Nav2 parameter YAML ─────────────────────────────────────
        nav2_slice = None
        nav2_contributed = True
        nav2_unsupported: list[str] = []
        if nav2_params_path:
            nav2_slice = parse_nav2_params(nav2_params_path)
            added = merge_nav2_slice_into_ir(ir, nav2_slice)
            nav2_contributed = added > 0
            nav2_unsupported = list(nav2_slice.unsupported_constructs)
            if nav2_unsupported:
                ir.extraction_warnings.append(
                    "Nav2 importer did not model: " + ", ".join(nav2_unsupported)
                )
            if nav2_slice.absent_sections:
                ir.extraction_warnings.append(
                    "Nav2 params file has no "
                    + ", ".join(nav2_slice.absent_sections)
                    + " section(s)"
                )
            logger.info(
                "Nav2 params merged: plugin=%s, %d value(s) extracted, "
                "%d unsupported, absent=%s",
                nav2_slice.controller_plugin or "(none)", added,
                len(nav2_unsupported), nav2_slice.absent_sections or "none",
            )

        # ── Stage 4: Deterministic rules ──────────────────────────────────────
        strictness_level = RuleStrictness(strictness.lower())
        rule_result = run_rules_detailed(ir, strictness=strictness_level)
        rule_findings = rule_result.findings
        suppressed_rule_findings = rule_result.suppressed_findings

        # Nav2 cross-artifact coherence runs on the structured slice rather than
        # the IR, so it sits alongside the IR rule engine rather than inside it.
        nav2_findings = check_nav2_coherence(nav2_slice)
        if strictness_level != RuleStrictness.STRICT:
            strict_only = strict_only_categories()
            suppressed_rule_findings += [
                f for f in nav2_findings if f.category in strict_only
            ]
            nav2_findings = [f for f in nav2_findings if f.category not in strict_only]
        rule_findings += nav2_findings

        suppressed_by_rule = Counter(f.category.value for f in suppressed_rule_findings)
        logger.info(
            "Rules: %d finding(s) (%d from Nav2 coherence), %d suppressed by strictness=%s",
            len(rule_findings),
            len(nav2_findings),
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

        # ── Stage 6b: Coverage — what did we fail to analyze? ─────────────────
        coverage_gaps = detect_coverage_gaps(
            ir,
            bt_xml_path=bt_xml_path,
            bt_unsupported_nodes=bt_unsupported,
            bt_contributed=bt_contributed,
            model_path=model_path,
            model_contributed=model_contributed,
            code_paths=code_paths,
            nav2_params_path=nav2_params_path,
            nav2_unsupported=nav2_unsupported,
            nav2_contributed=nav2_contributed,
        )
        status = analysis_status(coverage_gaps)
        incomplete = bool(coverage_gaps)
        for gap in coverage_gaps:
            logger.warning("  Coverage gap %s [%s]: %s", gap.id, gap.category.value, gap.title)
        logger.info("Coverage: %s (%d gap(s))", status.value, len(coverage_gaps))

        if incomplete:
            exit_reason = "ANALYSIS_COVERAGE_INCOMPLETE"
        elif gate_failed:
            exit_reason = "SEVERITY_THRESHOLD_EXCEEDED"
        else:
            exit_reason = "REVIEW_COMPLETED"

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
            policy_profile=policy_profile,
            policy_sources=policy_sources or {},
            suppressed_finding_count=len(suppressed_rule_findings),
            suppressed_by_rule=dict(suppressed_by_rule),
            highest_severity_found=highest,
            gate_failed=gate_failed,
            exit_reason=exit_reason,
            coverage_gaps=coverage_gaps,
            analysis_status=status.value,
            fail_on_unknown=fail_on_unknown,
        )
        logger.info("Artifacts written to: %s", out_dir)

        if incomplete and fail_on_unknown:
            return 3
        return 2 if gate_failed else 0
    except Exception:
        logger.exception("EAL review failed due to pipeline/infrastructure error")
        return 1
