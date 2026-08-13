"""
The unchecked-hazard register: declared silence.

A review that reports no findings is silent about everything outside the checks
that ran. Left implicit, that silence reads as reassurance, and reassurance is
what turns a narrow tool into an accident contributor: an engineer resolves what
the tool pointed at, sees a green result, and concludes the configuration is
sound. The tool has then directed attention away from the hazard rather than
merely failing to find it.

This was not a theoretical worry. On EAL's own corpus, taking the flagship Nav2
config, cutting the sensor marking range to 0.4 m — so the robot cannot see far
enough to stop — and then applying exactly the fix EAL recommended for the
acceleration mismatch produced `0 findings`, `PASS`, `exit 0`.

The register is the countermeasure available to a static tool. It cannot find
hazards nobody declared, but it can refuse to let its silence be mistaken for
coverage, by naming what it did not examine at the moment the result is read.
Contents are derived from measured evaluation results rather than written by
hand; see scripts/generate_hazard_register.py.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

REGISTER_PATH = Path(__file__).parent / "data" / "unchecked_hazards.yaml"


@functools.lru_cache(maxsize=1)
def unchecked_hazards() -> dict:
    """Load the shipped register. Returns an empty register if absent."""
    if not REGISTER_PATH.exists():
        return {"statement": "", "measured": {}, "classes": []}
    return yaml.safe_load(REGISTER_PATH.read_text(encoding="utf-8")) or {}


def hazard_classes() -> list[dict]:
    return unchecked_hazards().get("classes", [])


def register_summary() -> dict:
    """Compact form for machine-readable artifacts."""
    register = unchecked_hazards()
    return {
        "statement": register.get("statement", ""),
        "measured": register.get("measured", {}),
        "class_count": len(register.get("classes", [])),
        "classes": [
            {
                "id": c["id"],
                "title": c["title"],
                "worst_hazard": c.get("worst_hazard"),
                "detail": c["detail"],
                "evidence": [e["mutation"] for e in c.get("evidence", [])],
            }
            for c in register.get("classes", [])
        ],
    }
