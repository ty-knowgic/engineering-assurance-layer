"""Tests for built-in policy profile resolution."""

from __future__ import annotations

from eal.policy import PolicyProfile, resolve_policy


def test_default_policy_is_local():
    resolved = resolve_policy()
    assert resolved.profile == PolicyProfile.LOCAL
    assert resolved.fail_on_severity == "NONE"
    assert resolved.min_severity == "LOW"
    assert resolved.strictness == "balanced"
    assert resolved.fail_on_source == "profile_default"
    assert resolved.min_severity_source == "profile_default"
    assert resolved.strictness_source == "profile_default"


def test_builtin_profile_defaults():
    ci = resolve_policy(profile="ci")
    assert ci.fail_on_severity == "HIGH"
    assert ci.min_severity == "LOW"
    assert ci.strictness == "balanced"

    main = resolve_policy(profile="main")
    assert main.fail_on_severity == "HIGH"
    assert main.min_severity == "LOW"
    assert main.strictness == "relaxed"

    strict = resolve_policy(profile="strict")
    assert strict.fail_on_severity == "MEDIUM"
    assert strict.min_severity == "LOW"
    assert strict.strictness == "strict"


def test_explicit_overrides_profile_defaults():
    resolved = resolve_policy(
        profile="ci",
        fail_on_severity="CRITICAL",
        min_severity="HIGH",
        strictness="strict",
    )
    assert resolved.profile == PolicyProfile.CI
    assert resolved.fail_on_severity == "CRITICAL"
    assert resolved.min_severity == "HIGH"
    assert resolved.strictness == "strict"
    assert resolved.fail_on_source == "explicit_flag"
    assert resolved.min_severity_source == "explicit_flag"
    assert resolved.strictness_source == "explicit_flag"

