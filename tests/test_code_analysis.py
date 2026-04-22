"""Tests for Python AST-based code analysis extraction."""

from __future__ import annotations

from pathlib import Path

from eal.code_analysis import analyze_python_code_files
from eal.ingestion import load_code_files
from eal.ir.schema import CodeSymbolClass


def _write_code(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_extract_constants_and_comparisons(tmp_path):
    code_path = _write_code(
        tmp_path,
        "controller.py",
        """
MAX_JOINT_SPEED = 1.5
ESTOP_RESPONSE_MS = 150

class Limits:
    MAX_TORQUE = 10

def check(joint_speed: float, elapsed_ms: float) -> bool:
    if joint_speed > MAX_JOINT_SPEED:
        return False
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    return True
""",
    )
    code_files = load_code_files([code_path])
    analysis = analyze_python_code_files(code_files)

    assert len(analysis.constants) >= 3
    symbols = {c.symbol: c.value for c in analysis.constants}
    assert symbols["MAX_JOINT_SPEED"] == 1.5
    assert symbols["ESTOP_RESPONSE_MS"] == 150.0
    assert symbols["MAX_TORQUE"] == 10.0
    classes = {c.symbol: c.classification for c in analysis.constants}
    assert classes["MAX_JOINT_SPEED"] == CodeSymbolClass.SIGNAL_BOUND_CANDIDATE
    assert classes["ESTOP_RESPONSE_MS"] == CodeSymbolClass.TIMING_PARAMETER_CANDIDATE

    comparisons = {(c.symbol, c.operator, c.value) for c in analysis.comparisons}
    assert ("joint_speed", ">", 1.5) in comparisons
    assert ("elapsed_ms", "<=", 150.0) in comparisons
    cmp_classes = {c.symbol: c.classification for c in analysis.comparisons}
    assert cmp_classes["elapsed_ms"] == CodeSymbolClass.TIMING_PARAMETER_CANDIDATE


def test_parse_error_is_reported(tmp_path):
    broken = _write_code(tmp_path, "broken.py", "def bad(:\n    return 1\n")
    analysis = analyze_python_code_files(load_code_files([broken]))

    assert analysis.constants == []
    assert analysis.comparisons == []
    assert len(analysis.warnings) == 1
    assert "parse error" in analysis.warnings[0].lower()
    assert any(e.kind == "warning" for e in analysis.evidence)
