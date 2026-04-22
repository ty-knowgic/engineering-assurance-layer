"""Tests for deterministic code/spec/model name normalization."""

from __future__ import annotations

from eal.code_analysis import classify_numeric_symbol, names_match, normalize_symbol_name
from eal.ir.schema import CodeSymbolClass


def test_normalize_symbol_name_variants():
    assert normalize_symbol_name("joint_speed") == "joint_speed"
    assert normalize_symbol_name("max_joint_speed") == "joint_speed"
    assert normalize_symbol_name("JOINT_SPEED_LIMIT") == "joint_speed"
    assert normalize_symbol_name("estop_response_milliseconds") == "estop_response_ms"


def test_names_match_bound_aliases():
    assert names_match("MAX_JOINT_SPEED", "joint_speed")
    assert names_match("JOINT_SPEED_LIMIT", "joint_speed")
    assert names_match("ESTOP_RESPONSE_MS", "estop_response_ms")
    assert not names_match("HTTP_PORT", "joint_speed")


def test_classify_numeric_symbol_conservative():
    cls_speed, conf_speed, _ = classify_numeric_symbol("MAX_JOINT_SPEED")
    assert cls_speed == CodeSymbolClass.SIGNAL_BOUND_CANDIDATE
    assert conf_speed >= 0.85

    cls_timing, conf_timing, _ = classify_numeric_symbol("ESTOP_RESPONSE_MS")
    assert cls_timing == CodeSymbolClass.TIMING_PARAMETER_CANDIDATE
    assert conf_timing >= 0.85

    cls_generic, conf_generic, _ = classify_numeric_symbol("HTTP_PORT")
    assert cls_generic == CodeSymbolClass.GENERIC_NUMERIC_CONSTANT
    assert conf_generic < 0.5
