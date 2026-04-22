"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def robotics_arm_spec():
    return EXAMPLES / "robotics_arm" / "spec.md"


@pytest.fixture
def robotics_arm_model():
    return EXAMPLES / "robotics_arm" / "model.yaml"


@pytest.fixture
def mobile_robot_spec():
    return EXAMPLES / "mobile_robot" / "spec.md"


@pytest.fixture
def mobile_robot_model():
    return EXAMPLES / "mobile_robot" / "model.yaml"


@pytest.fixture
def minimal_spec(tmp_path) -> Path:
    """A minimal valid spec with one signal and one requirement."""
    p = tmp_path / "spec.md"
    p.write_text(
        "# Minimal Spec\n\n"
        "## Signals\n\n"
        "- speed: sensor, m/s, bounds=[0, 10]\n\n"
        "## States\n\n"
        "- IDLE: waiting\n"
        "- RUNNING: in motion\n\n"
        "## Requirements\n\n"
        "- REQ-001: speed must remain <= 5 m/s in RUNNING state.\n"
    )
    return p
