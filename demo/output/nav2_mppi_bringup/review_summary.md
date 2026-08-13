# Engineering Assurance Review Summary

**Run ID:** `eal-DEMO-NORMALIZED`
**Spec:** `demo/spec/nav2_motion_limits.md`
**Generated:** 1970-01-01T00:00:00+00:00
**Review status:** ❌ REVIEW REQUIRED
**Analysis status:** `COMPLETE`
**Coverage gaps:** `0`
**Highest severity found:** `HIGH`
**Gate threshold:** `HIGH`
**Gate result:** ❌ FAIL
**Policy profile:** `ci`
**Presentation minimum severity:** `LOW`
**Rule strictness:** `balanced`
**Policy source map:** `{"fail_on_severity": "profile_default", "fail_on_unknown": "profile_default", "min_severity": "profile_default", "strictness": "profile_default"}`
**Strictness-suppressed findings:** `2`
**SARIF artifact:** `results.sarif`

## Findings Overview

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | 0 |
| 🟠 HIGH     | 3 |
| 🟡 MEDIUM   | 0 |
| 🔵 LOW      | 0 |
| **Total**   | **3** |

## IR Extraction Summary

- Signals: 0
- States: 0
- Modes: 0
- Transitions: 0
- Requirements: 2
- Constraints: 26
- Assumptions: 1
- Code files analyzed: 0
- Code constants extracted: 0
- Code comparisons extracted: 0

## Extraction Warnings

- ⚠️  No signals found. Add a '## Signals' section to your spec.
- ⚠️  No states found. Add a '## States' section to your spec.

## Top Findings

_Showing findings at or above `LOW` (3 of 3 total)._

- 🟠 **F-001** [NAV2_ACCEL_OVERDECLARED] Controller declares linear acceleration limit 1.20x the downstream smoother limit
- 🟠 **F-002** [NAV2_ACCEL_OVERDECLARED] Controller declares linear deceleration limit 1.20x the downstream smoother limit
- 🟠 **F-003** [NAV2_ACCEL_OVERDECLARED] Controller declares angular acceleration limit 1.09x the downstream smoother limit