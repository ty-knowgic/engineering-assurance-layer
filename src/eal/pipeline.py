"""
Review pipeline orchestrator.

Stages:
  1. Ingest  — load spec, model, code files
  2. Extract — build IR from spec
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

from eal.artifacts import write_artifacts
from eal.extraction import extract_ir_from_spec, merge_model_into_ir
from eal.findings.schema import assign_ids
from eal.ingestion import load_code_files, load_model, load_spec
from eal.rules import run_rules
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
) -> int:
    """
    Run a full assurance review.

    Returns:
      0 — review complete (findings may exist; check report.html)
      1 — pipeline error (unrecoverable)
    """
    logger.info("EAL review starting")
    logger.info("  spec:  %s", spec_path)
    logger.info("  model: %s", model_path or "(none)")
    logger.info("  code:  %s", code_paths or "(none)")
    logger.info("  out:   %s", out_dir)

    # ── Stage 1: Ingest ───────────────────────────────────────────────────────
    spec = load_spec(spec_path)
    model = load_model(model_path) if model_path else None
    code_files = load_code_files(code_paths) if code_paths else []
    logger.info("Ingestion complete: spec=%d lines", len(spec.lines))

    # ── Stage 2: Extract IR from spec ─────────────────────────────────────────
    ir = extract_ir_from_spec(spec)
    ir.code_files = [str(cf.path) for cf in code_files]
    logger.info(
        "Extraction complete: %d signals, %d states, %d requirements, %d constraints",
        len(ir.signals), len(ir.states), len(ir.requirements), len(ir.constraints),
    )
    for w in ir.extraction_warnings:
        logger.warning("  Extraction: %s", w)

    # ── Stage 3: Merge model ──────────────────────────────────────────────────
    if model:
        merge_model_into_ir(ir, model)
        logger.info(
            "Model merged: now %d signals, %d states, %d constraints",
            len(ir.signals), len(ir.states), len(ir.constraints),
        )

    # ── Stage 4: Deterministic rules ──────────────────────────────────────────
    rule_findings = run_rules(ir)
    logger.info("Rules: %d finding(s)", len(rule_findings))

    # ── Stage 5: Z3 solver checks ─────────────────────────────────────────────
    z3_findings = run_z3_checks(ir)
    logger.info("Solver: %d finding(s)", len(z3_findings))

    # ── Stage 6: Rank & ID assignment ─────────────────────────────────────────
    all_findings = assign_ids(rule_findings + z3_findings)

    # ── Stage 7: Emit artifacts ───────────────────────────────────────────────
    run_id = _make_run_id(spec_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_artifacts(out_dir, ir, all_findings, run_id)
    logger.info("Artifacts written to: %s", out_dir)

    return 0
