# Synthetic Danger Reuse Report

## What Was Found

`/Users/tetsuy/repo/synthetic-danger/` — a production Python tool for Engineering Change Order (ECO) review automation, called **Synthetic Danger** (ECRB workflow).

The project implements:
- Typer-based CLI with `ecrb`, `score`, `uc1`, `check` commands
- LLM-driven (OpenAI GPT) finding generation from ECO documents
- Deterministic gap checker (`gap_checker.py`) — rule-based, no LLM
- Artifact output pattern: `findings.json`, `review_gaps.json`, `evidence.json`, XLSX/HTML reports
- Anchor extraction from ECO documents (regex-based)
- Phase 0 scoring / completeness computation
- Offline pytest suite

**Notable absence**: No Z3 or any formal verification tool in Synthetic Danger.
All constraint checking in Synthetic Danger is keyword/regex-based or LLM-based.

---

## Reuse Classification

### Category 1: Directly Reused (adapted, not copied)

| Synthetic Danger Asset | How Used in EAL |
|------------------------|-----------------|
| Typer CLI skeleton (`cli.py`) | EAL `cli.py` uses same Typer command pattern, same `_setup_logging()` helper, same `--out` / `--log-level` convention |
| Multi-artifact output coordination (`runner.py`) | EAL `artifacts/writer.py` uses same pattern: write 8+ files per run, always emit even if empty, include status markers |
| `evidence.json` pattern | EAL `review_evidence.json` carries the same provenance fields: run_id, git info, input file hashes, IR summary |
| `run_id` / stable hash pattern (`_stable_hash`, `_git_info`) | EAL `pipeline.py` generates `run_id = eal-{timestamp}-{sha1[:10]}` and calls `_git_info()` with identical fallback logic |
| Offline deterministic test design | EAL test suite is 100% offline, pytest fixtures for example files, same conftest.py pattern |
| `compute_review_completeness` / scoring structure | EAL `run_metadata.json` carries `finding_count`, `critical_count`, `status` in the same layout |
| `enforce_local_rules` + `dedup` in `finding_generator.py` | EAL `findings/schema.py:assign_ids()` uses same stable sort + renumber pattern |

### Category 2: Partially Reused (refactored and reframed)

| Synthetic Danger Asset | What Changed | EAL Equivalent |
|------------------------|--------------|----------------|
| `gap_checker.py` — rule structure | Kept: function-per-rule, `(ir) -> list[Finding]` pattern. Removed: all ECO/manufacturing-specific logic | `rules/engine.py` — 7 engineering-domain rules |
| `ImpactFinding` schema | Kept: severity, category, title, summary, evidence_refs, source_locations, suggested action. Removed: ECO-specific fields (affected_scope, review_status, disposition, discipline lists). Added: counterexample dict, related_ir_nodes | `findings/schema.py:Finding` |
| `ReviewGap` schema | Renamed and reframed: gap_type → FindingCategory, severity → FindingSeverity | Merged into `Finding` (single schema, not split gap/finding) |
| `eco_parser.py` — YAML ingestion | Kept: YAML load pattern, ModelDocument container, safe_load. Removed: ECO-specific field mapping | `ingestion/loaders.py:ModelDocument` |
| HTML report (`_write_html` in runner.py) | Kept: f-string HTML generation, severity badge styling. Removed: XLSX, multi-sheet structure, discipline tables | `artifacts/writer.py:_write_html_report()` |
| `validate_input.py` input validation | Kept: pre-flight validation before pipeline. Removed: hardcoded ECO schema checks. Replaced with Typer's `exists=True` path validation | CLI `--spec` / `--model` path options |

### Category 3: Not Reused

| Synthetic Danger Asset | Reason |
|------------------------|--------|
| `finding_generator.py` | Entirely LLM-based (OpenAI GPT). EAL is deterministic in v0.0.2 — no external API calls |
| `eco_parser.py` ECO field mapping | ECO-specific: `eco_header`, `change_class`, `affected_items`, `specifications_changed`. No equivalent in engineering spec context |
| `hazard_ontology.json` | 8 hazard categories (Mechanical/Electrical/Software/Control/etc.) are robotics-safety-specific, not reusable as generic assurance categories |
| `impact_taxonomy.json` | 8 impact disciplines (Manufacturing, Quality, SupplyChain, Regulatory, etc.) are manufacturing ECO disciplines |
| `anchor_extractor.py` | Extracts part numbers, drawing revisions, process plan IDs — all ECO manufacturing identifiers |
| `enrich.py`, `reason_high.py`, `repair_truncation.py` | Pure LLM enrichment pipeline — out of scope for the current deterministic EAL baseline |
| `normalize.py` | Robotics component alias normalization (fuzzy matching on vacuum gripper, RGB camera, etc.) |
| `run.py` | Hazard generation pipeline — domain-specific, LLM-heavy |
| `scorer.py` (ECRB) | Discipline-recall scoring against expected ECO review disciplines |
| UC-1 workflow (`uc1/runner.py`) | Design change diff workflow (before/after hazard sets) |

---

## Concept Mapping

| Synthetic Danger Concept | Engineering Assurance Layer Equivalent |
|--------------------------|----------------------------------------|
| Engineering Change Review Brief (ECRB) | Assurance Review |
| ECO input → findings | Spec input → findings |
| Impact Finding (discipline-oriented) | Finding (constraint/assurance-oriented) |
| Gap Checker | Rules Engine |
| Review Gap | Finding (merged; single schema) |
| Anchor (part#, spec delta, revision) | Source Reference + constraint expression |
| `evidence.json` | `review_evidence.json` |
| `findings.json` | `findings.json` (renamed fields) |
| `completeness.json` | `run_metadata.json` (status field) |
| Phase 0 scoring (specificity, discipline recall) | Finding severity + CRITICAL/HIGH count |
| `_git_info()` / `run_id` | Same function, same fields |
| Safety hazard review | Engineering assurance review |
| LLM finding generation | (not in v0.0.2; deterministic rules only) |
| Hazard taxonomy | Z3-backed constraint checking |

---

## Summary

Synthetic Danger contributed the following to EAL:
- **Architectural pattern**: artifact-first output, run_id provenance, offline testing
- **Code structure**: per-rule functions, CLI skeleton, HTML writer
- **Design philosophy**: deterministic checks as the foundation; LLM as an optional later layer

Synthetic Danger's domain-specific code (ECO fields, hazard taxonomy, manufacturing disciplines,
LLM prompt engineering) was intentionally excluded. EAL was reframed around engineering
specifications, constraint IR, and symbolic verification — a distinct product positioning
from ECO-driven manufacturing change review.

The most structurally valuable reuse was the **rule-check architecture** and
the **artifact-first output model**. These are the patterns that make both tools
testable, debuggable, and CI-gate-compatible.
