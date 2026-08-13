#!/usr/bin/env python3
"""
Generate the shipped unchecked-hazard register from measured evaluation results.

    make hazard-register

The register is emitted with every review run, so it must state what EAL
actually fails to catch rather than what someone once believed it failed to
catch. It is therefore derived, not written by hand: a hazard class is included
only while at least one moderate-or-severe mutation in that class is still going
undetected in `eval/output/results.json`.

That keeps it honest in both directions. Fix a blind spot and the class drops
out on the next regeneration. Introduce one and it appears. A test asserts the
committed register matches what the current results imply, so the two cannot
drift apart silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "eval" / "mutations.yaml"
RESULTS = ROOT / "eval" / "output" / "results.json"
TARGET = ROOT / "src" / "eal" / "data" / "unchecked_hazards.yaml"

HEADER = (
    "# GENERATED FILE — do not edit by hand.\n"
    "# Regenerate with: make hazard-register\n"
    "#\n"
    "# Derived from eval/mutations.yaml and the measured results in\n"
    "# eval/output/results.json. A hazard class is listed here only while at\n"
    "# least one moderate-or-severe mutation in that class still goes\n"
    "# undetected. This register is emitted with every review run.\n"
)


def build_register() -> dict:
    catalogue = yaml.safe_load(CATALOGUE.read_text())
    results = json.loads(RESULTS.read_text())["results"]
    descriptions = catalogue["hazard_classes"]

    silent = [r for r in results if r["hazardous"] and not r["eal_said_something"]]
    by_category: dict[str, list[dict]] = {}
    for r in silent:
        by_category.setdefault(r["category"], []).append(r)

    missing = sorted(set(by_category) - set(descriptions))
    if missing:
        raise SystemExit(
            "eval/mutations.yaml has no hazard_classes entry for: "
            + ", ".join(missing)
            + "\nEvery undetected hazard class must be described before it can be shipped."
        )

    classes = []
    for category in sorted(by_category):
        entry = descriptions[category]
        evidence = sorted(by_category[category], key=lambda r: r["id"])
        classes.append({
            "id": category,
            "title": entry["title"].strip(),
            "detail": " ".join(entry["detail"].split()),
            "worst_hazard": max(
                (r["hazard"] for r in evidence),
                key=["none", "low", "moderate", "severe"].index,
            ),
            "evidence": [
                {"mutation": r["id"], "hazard": r["hazard"], "case": r["description"]}
                for r in evidence
            ],
        })

    hazardous = [r for r in results if r["hazardous"]]
    detected = [r for r in hazardous if r["eal_said_something"]]
    return {
        "statement": (
            "Hazard classes EAL does not check. A review that reports no findings "
            "says nothing about any of these. Measured by the adversarial "
            "evaluation in eval/, not asserted."
        ),
        "measured": {
            "hazardous_mutations": len(hazardous),
            "detected": len(detected),
            "undetected": len(hazardous) - len(detected),
            "source": "eval/output/results.json",
        },
        "classes": classes,
    }


def main() -> int:
    register = build_register()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(HEADER + yaml.safe_dump(register, sort_keys=False, width=88))
    print(
        f"Wrote {TARGET.relative_to(ROOT)}: {len(register['classes'])} unchecked "
        f"hazard class(es) from {register['measured']['undetected']} undetected mutation(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
