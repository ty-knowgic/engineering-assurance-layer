"""
Lightweight policy profile resolution for EAL operational contexts.

Profiles provide defaults for gate threshold, presentation threshold, and rule
strictness. Explicit CLI flags always override the selected profile defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PolicyProfile(str, Enum):
    LOCAL = "local"
    CI = "ci"
    MAIN = "main"
    PROD = "prod"
    STRICT = "strict"


@dataclass(frozen=True)
class PolicyDefaults:
    fail_on_severity: str
    min_severity: str
    strictness: str
    description: str


@dataclass(frozen=True)
class ResolvedPolicy:
    profile: PolicyProfile
    fail_on_severity: str
    min_severity: str
    strictness: str
    fail_on_source: str
    min_severity_source: str
    strictness_source: str

    def source_map(self) -> dict[str, str]:
        return {
            "fail_on_severity": self.fail_on_source,
            "min_severity": self.min_severity_source,
            "strictness": self.strictness_source,
        }


_PROFILE_DEFAULTS: dict[PolicyProfile, PolicyDefaults] = {
    PolicyProfile.LOCAL: PolicyDefaults(
        fail_on_severity="NONE",
        min_severity="LOW",
        strictness="balanced",
        description="Local exploratory run: no gate failure by default.",
    ),
    PolicyProfile.CI: PolicyDefaults(
        fail_on_severity="HIGH",
        min_severity="LOW",
        strictness="balanced",
        description="CI smoke checks: fail on HIGH/CRITICAL findings.",
    ),
    PolicyProfile.MAIN: PolicyDefaults(
        fail_on_severity="HIGH",
        min_severity="LOW",
        strictness="relaxed",
        description="Main branch gating with reduced heuristic noise.",
    ),
    PolicyProfile.PROD: PolicyDefaults(
        fail_on_severity="HIGH",
        min_severity="LOW",
        strictness="relaxed",
        description="Production-style gating alias; same defaults as main.",
    ),
    PolicyProfile.STRICT: PolicyDefaults(
        fail_on_severity="MEDIUM",
        min_severity="LOW",
        strictness="strict",
        description="Stricter validation: include heuristics and gate at MEDIUM+.",
    ),
}


def available_policy_profiles() -> dict[str, PolicyDefaults]:
    """Return profile defaults keyed by profile name."""
    return {k.value: v for k, v in _PROFILE_DEFAULTS.items()}


def resolve_policy(
    *,
    profile: PolicyProfile | str | None = None,
    fail_on_severity: Optional[str] = None,
    min_severity: Optional[str] = None,
    strictness: Optional[str] = None,
) -> ResolvedPolicy:
    """
    Resolve effective policy values from profile defaults + explicit overrides.

    Precedence:
      explicit flag > selected profile default
    """
    selected = (
        profile
        if isinstance(profile, PolicyProfile)
        else PolicyProfile(str(profile).lower()) if profile is not None
        else PolicyProfile.LOCAL
    )
    defaults = _PROFILE_DEFAULTS[selected]

    eff_fail = (fail_on_severity or defaults.fail_on_severity).upper()
    eff_min = (min_severity or defaults.min_severity).upper()
    eff_strict = (strictness or defaults.strictness).lower()

    return ResolvedPolicy(
        profile=selected,
        fail_on_severity=eff_fail,
        min_severity=eff_min,
        strictness=eff_strict,
        fail_on_source="explicit_flag" if fail_on_severity is not None else "profile_default",
        min_severity_source="explicit_flag" if min_severity is not None else "profile_default",
        strictness_source="explicit_flag" if strictness is not None else "profile_default",
    )
