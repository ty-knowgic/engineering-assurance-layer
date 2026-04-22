"""Deterministic name normalization, classification, and matching for code/spec/model alignment."""

from __future__ import annotations

import re

from eal.ir.schema import CodeSymbolClass

_WORD_RE = re.compile(r"[a-z0-9]+")

_PREFIX_QUALIFIERS = {"max", "maximum", "min", "minimum"}
_SUFFIX_QUALIFIERS = {"limit", "bound", "threshold", "value", "val", "target"}

_UNIT_NORMALIZATION = {
    "millisecond": "ms",
    "milliseconds": "ms",
    "msec": "ms",
    "msecs": "ms",
    "second": "s",
    "seconds": "s",
    "secs": "s",
}

_TIMING_TOKENS = {"ms", "time", "timing", "latency", "response", "timeout", "delay", "deadline"}
_STRONG_TIMING_TOKENS = {"ms", "timeout", "delay", "latency", "deadline"}

_BOUND_QUANTITY_TOKENS = {
    "speed",
    "torque",
    "force",
    "pressure",
    "current",
    "voltage",
    "position",
    "angle",
    "accel",
    "acceleration",
    "rate",
    "temp",
    "temperature",
}


# Keep alias handling explicit and conservative to reduce accidental matches.
_ALIAS_REWRITES = (
    ("e_stop", "estop"),
    ("e-stop", "estop"),
    ("emergency_stop", "estop"),
    ("emergency-stop", "estop"),
)


def symbol_tokens(symbol: str) -> list[str]:
    """Tokenize symbol names into normalized, comparable tokens."""
    raw = (symbol or "").strip()
    if not raw:
        return []

    # Attribute paths (e.g. obj.max_joint_speed) compare by leaf symbol.
    leaf = raw.split(".")[-1].lower()
    for src, dst in _ALIAS_REWRITES:
        leaf = leaf.replace(src, dst)

    words = _WORD_RE.findall(leaf)
    return [_UNIT_NORMALIZATION.get(w, w) for w in words]


def normalize_symbol_name(symbol: str) -> str:
    """
    Normalize identifiers for deterministic matching.

    Strategy:
    - lowercase + tokenization
    - strip common max/min prefixes
    - strip common limit/bound suffixes
    - normalize time units (milliseconds -> ms)
    """
    tokens = symbol_tokens(symbol)
    if not tokens:
        return ""

    while tokens and tokens[0] in _PREFIX_QUALIFIERS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _SUFFIX_QUALIFIERS:
        tokens = tokens[:-1]

    return "_".join(tokens)


def classify_numeric_symbol(symbol: str) -> tuple[CodeSymbolClass, float, str]:
    """Classify a numeric code symbol into assurance-relevant buckets."""
    tokens = symbol_tokens(symbol)
    if not tokens:
        return (CodeSymbolClass.GENERIC_NUMERIC_CONSTANT, 0.0, "empty symbol")

    prefix = tokens[0]
    suffix = tokens[-1]

    has_timing = any(tok in _TIMING_TOKENS for tok in tokens)
    strong_timing = any(tok in _STRONG_TIMING_TOKENS for tok in tokens)
    has_bound_qualifier = prefix in _PREFIX_QUALIFIERS or suffix in _SUFFIX_QUALIFIERS
    has_bound_quantity = any(tok in _BOUND_QUANTITY_TOKENS for tok in tokens)

    if has_timing and (strong_timing or ("response" in tokens and "ms" in tokens)):
        return (
            CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
            0.95,
            "contains strong timing tokens/suffixes (e.g. ms/timeout/delay/latency)",
        )

    if has_bound_qualifier and has_bound_quantity:
        return (
            CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
            0.95,
            "contains bound qualifier plus physical quantity token",
        )

    if has_bound_qualifier:
        return (
            CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
            0.88,
            "contains bound qualifier (max/min/limit/bound/threshold)",
        )

    if has_bound_quantity:
        return (
            CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
            0.72,
            "contains physical quantity token (e.g. speed/torque)",
        )

    if has_timing:
        return (
            CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
            0.78,
            "contains timing token but lacks strong timing suffix",
        )

    return (
        CodeSymbolClass.GENERIC_NUMERIC_CONSTANT,
        0.30,
        "no strong timing or bound indicators",
    )


def classification_is_strong(symbol_class: CodeSymbolClass, confidence: float) -> bool:
    if symbol_class in {
        CodeSymbolClass.TIMING_PARAMETER_CANDIDATE,
        CodeSymbolClass.SIGNAL_BOUND_CANDIDATE,
    }:
        return confidence >= 0.85
    return False


def names_match(name_a: str, name_b: str) -> bool:
    """Deterministic match predicate with conservative fallback for minor variants."""
    a = normalize_symbol_name(name_a)
    b = normalize_symbol_name(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith(f"_{b}") or b.endswith(f"_{a}")


def is_timing_name(symbol: str) -> bool:
    tokens = symbol_tokens(symbol)
    return any(tok in _TIMING_TOKENS for tok in tokens)


def has_min_hint(symbol: str) -> bool:
    tokens = symbol_tokens(symbol)
    return bool(tokens) and tokens[0] in {"min", "minimum"}


def has_upper_hint(symbol: str) -> bool:
    tokens = symbol_tokens(symbol)
    if not tokens:
        return False
    if tokens[0] in {"max", "maximum"}:
        return True
    return tokens[-1] in {"limit", "bound", "threshold", "max", "maximum"}


def token_overlap(name_a: str, name_b: str) -> set[str]:
    return set(symbol_tokens(name_a)) & set(symbol_tokens(name_b))
