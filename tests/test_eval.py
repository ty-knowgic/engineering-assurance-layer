"""
Phase 3 evaluation integrity.

Guards the properties that make the adversarial evaluation worth anything: that
its expectations were written down rather than derived from the results, that it
covers every mutation class the process requires, and that it still contains
cases the tool fails. An evaluation suite that only holds passing cases measures
nothing, so `test_evaluation_still_contains_failures` is deliberately an
assertion that the tool is not perfect.

The full run is `make eval`; CI runs `make eval-check` separately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"

CATALOGUE = yaml.safe_load((EVAL / "mutations.yaml").read_text())
SUMMARY = json.loads((EVAL / "output" / "summary.json").read_text())
RESULTS = json.loads((EVAL / "output" / "results.json").read_text())["results"]

# The ten classes the evaluation process requires.
REQUIRED_CATEGORIES = {
    "max_speed_increase",
    "stopping_region_reduction",
    "latency_increase",
    "min_decel_reduction",
    "unit_mismatch",
    "missing_parameter",
    "conflicting_definitions",
    "irrelevant_change",
    "unknown_parameter",
    "false_safety_assumption",
}

VALID_OUTCOMES = {"DETECT", "UNKNOWN", "MISS", "NO_NEW_FINDINGS"}
VALID_HAZARDS = {"none", "low", "moderate", "severe"}


def test_all_required_mutation_classes_are_covered():
    present = {m["category"] for m in CATALOGUE["mutations"]}
    assert REQUIRED_CATEGORIES <= present, REQUIRED_CATEGORIES - present


@pytest.mark.parametrize("m", CATALOGUE["mutations"], ids=lambda m: m["id"])
def test_every_mutation_declares_hazard_expectation_and_rationale(m):
    """An expectation without a stated reason can be rationalised after the fact."""
    assert m["hazard"] in VALID_HAZARDS
    assert m["expect"]["outcome"] in VALID_OUTCOMES
    assert m.get("edit") or m.get("edits"), "mutation must change something"
    # A harmless false-positive probe is adequately explained in one line; a
    # mutation that introduces real risk needs its reasoning written down,
    # because that reasoning is what the reader is being asked to check.
    minimum = 20 if m["hazard"] in ("moderate", "severe") else 5
    assert len(m["rationale"].split()) >= minimum, (
        f"{m['id']}: rationale too thin for hazard={m['hazard']}"
    )
    if m["expect"]["outcome"] == "DETECT":
        assert m["expect"].get("categories"), "DETECT must name the expected categories"


def test_mutation_ids_are_unique():
    ids = [m["id"] for m in CATALOGUE["mutations"]]
    assert len(ids) == len(set(ids))


def test_catalogue_and_committed_results_agree():
    assert {m["id"] for m in CATALOGUE["mutations"]} == {r["id"] for r in RESULTS}


def test_no_false_positives_on_harmless_edits():
    """A tool that fires on a comment change is not usable in CI."""
    assert SUMMARY["false_positives"] == 0, [
        r["id"] for r in RESULTS if r["verdict"] == "FALSE_POSITIVE"
    ]


def test_results_are_reproducible():
    assert SUMMARY["reproducible"] is True


def test_evaluation_still_contains_failures():
    """
    The suite must keep cases the tool does not handle. If this ever fails
    because every hazard is detected, the catalogue has stopped being
    adversarial and needs harder mutations — not celebration.
    """
    assert SUMMARY["silent_on_real_hazard"] > 0
    assert SUMMARY["detection_rate_over_hazards"] < 1.0


def test_detection_rate_is_reported_over_all_hazards():
    """The denominator must include hazards the catalogue predicted we would miss."""
    hazardous = [r for r in RESULTS if r["hazardous"]]
    detected = [r for r in hazardous if r["eal_said_something"]]
    assert SUMMARY["hazardous_mutations"] == len(hazardous)
    assert SUMMARY["hazards_detected"] == len(detected)
    assert SUMMARY["detection_rate_over_hazards"] == pytest.approx(
        len(detected) / len(hazardous), abs=1e-3
    )


def test_expected_detections_all_fired():
    """Distinct from capability gaps: these are cases the tool claims to cover."""
    assert SUMMARY["expected_detections_missed"] == 0, [
        r["id"] for r in RESULTS if r["verdict"] == "MISSED"
    ]


def test_report_states_the_headline_rate():
    text = (EVAL / "RESULTS.md").read_text()
    assert "introduce a real hazard" in text
    assert "Hazards EAL is silent about" in text
