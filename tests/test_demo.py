"""
Demo integrity tests.

These are fast checks on the committed demo. The full byte-for-byte
reproduction is `make demo-check`, which CI runs as a separate step; running it
here would duplicate four CLI subprocesses on every test run.

What is guarded here:
  - the fixtures still hash to what demo/provenance.json claims, so the demo
    cannot silently drift onto edited input
  - the committed summary agrees with the committed artifacts
  - the demo still covers all three outcomes (PASS / FAIL / UNKNOWN), so a
    reviewer sees the tool report each of them on real input
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
OUTPUT = DEMO / "output"

MANIFEST = json.loads((DEMO / "provenance.json").read_text())
RESULTS = json.loads((DEMO / "results.json").read_text())


@pytest.mark.parametrize("entry", MANIFEST["files"], ids=lambda e: Path(e["local_path"]).name)
def test_fixture_matches_recorded_provenance(entry):
    """Every third-party fixture must still be the exact upstream bytes."""
    path = ROOT / entry["local_path"]
    assert path.exists(), entry["local_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    assert path.stat().st_size == entry["bytes"]


def test_provenance_pins_a_single_upstream_commit():
    up = MANIFEST["upstream"]
    assert len(up["commit"]) == 40
    assert up["repository"].startswith("https://github.com/")
    assert up["retrieved"] and up["commit_date"]


def test_every_scenario_has_committed_artifacts():
    for scenario in RESULTS["scenarios"]:
        d = OUTPUT / scenario["scenario"]
        assert d.is_dir(), scenario["scenario"]
        for name in ("findings.json", "run_metadata.json", "results.sarif",
                     "review_summary.md", "report.html"):
            assert (d / name).exists(), f"{scenario['scenario']}/{name}"


def test_summary_agrees_with_committed_artifacts():
    """demo/results.json must describe the artifacts actually committed."""
    for scenario in RESULTS["scenarios"]:
        d = OUTPUT / scenario["scenario"]
        findings = json.loads((d / "findings.json").read_text())
        metadata = json.loads((d / "run_metadata.json").read_text())
        assert findings["finding_count"] == scenario["finding_count"]
        assert findings["analysis_status"] == scenario["analysis_status"]
        assert findings["coverage_gap_count"] == scenario["coverage_gap_count"]
        assert metadata["gate"]["result"] == scenario["gate_result"]


def test_demo_covers_all_three_gate_outcomes():
    """A demo that only shows failures does not demonstrate a usable gate."""
    outcomes = {s["gate_result"] for s in RESULTS["scenarios"]}
    assert {"BELOW_THRESHOLD", "THRESHOLD_EXCEEDED", "UNKNOWN"} <= outcomes
    exits = {s["exit_code"] for s in RESULTS["scenarios"]}
    assert {0, 2, 3} <= exits


def test_clean_upstream_config_demo_has_no_findings():
    """The PASS case must be genuinely clean, not merely below a threshold."""
    clean = next(s for s in RESULTS["scenarios"] if s["scenario"] == "nav2_dwb_coherent")
    assert clean["finding_count"] == 0
    assert clean["exit_code"] == 0


def test_committed_artifacts_are_normalized():
    """No absolute paths or wall-clock times, or the outputs cannot be diffed."""
    for scenario in RESULTS["scenarios"]:
        for artifact in (OUTPUT / scenario["scenario"]).iterdir():
            text = artifact.read_text(encoding="utf-8")
            assert str(ROOT) not in text, f"{artifact.name} leaks an absolute path"
            if artifact.suffix == ".json":
                assert "eal-20" not in text, f"{artifact.name} leaks a real run id"


def test_run_metadata_records_input_digests():
    """Provenance must survive into the per-run artifacts, not just the manifest."""
    evidence = json.loads(
        (OUTPUT / "nav2_mppi_bringup" / "review_evidence.json").read_text()
    )
    digests = evidence["input_digests"]
    assert digests["algorithm"] == "sha256"
    assert len(digests["spec_file"]["sha256"]) == 64
