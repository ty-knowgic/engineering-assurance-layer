# Engineering Assurance Review Summary

**Run ID:** `eal-DEMO-NORMALIZED`
**Spec:** `demo/spec/nav2_motion_limits.md`
**Generated:** 1970-01-01T00:00:00+00:00
**Review status:** ⚠️ UNKNOWN
**Analysis status:** `INCOMPLETE`
**Coverage gaps:** `2`
**Highest severity found:** `NONE`
**Gate threshold:** `HIGH`
**Gate result:** ⚠️ UNKNOWN
**Policy profile:** `ci`
**Presentation minimum severity:** `LOW`
**Rule strictness:** `balanced`
**Policy source map:** `{"fail_on_severity": "profile_default", "fail_on_unknown": "profile_default", "min_severity": "profile_default", "strictness": "profile_default"}`
**Strictness-suppressed findings:** `0`
**SARIF artifact:** `results.sarif`

## ⚠️ Analysis Coverage Incomplete

EAL was asked to analyze input it could not fully model. **The finding counts below describe only the analyzed portion.** Absence of findings in the unanalyzed regions is not evidence of their correctness.

### U-001 — BehaviorTree XML contains 7 unmodelled node type(s)

**Category:** `UNSUPPORTED_INPUT_CONSTRUCT`  
**Affected input:** `tests/fixtures/nav2_upstream_bt/navigate_to_pose_w_replanning_and_recovery.xml`  

The BehaviorTree importer skipped node types it does not model: RecoveryNode, PipelineSequence, RateController, ReactiveSequence, Inverter, ReactiveFallback, RoundRobin. Control flow expressed through these nodes was not analyzed, so the absence of findings for those branches is not evidence of their correctness.

**Unanalyzed constructs:** `RecoveryNode`, `PipelineSequence`, `RateController`, `ReactiveSequence`, `Inverter`, `ReactiveFallback`, `RoundRobin`

**Suggested fix:** Express the affected behaviour in a supported construct, or treat this tree as outside EAL's current analysis envelope.

### U-002 — No analyzable content in merged IR

**Category:** `NO_ANALYZABLE_CONTENT`  
**Affected input:** `demo/spec/nav2_motion_limits.md`  

The merged IR contains no signals, constraints, or transitions. No deterministic rule or solver check could have fired. A zero-finding result here carries no assurance information.

**Suggested fix:** Provide a spec with Signals/Constraints/Transitions sections, or a model YAML supplying them.

## Findings Overview

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | 0 |
| 🟠 HIGH     | 0 |
| 🟡 MEDIUM   | 0 |
| 🔵 LOW      | 0 |
| **Total**   | **0** |

## IR Extraction Summary

- Signals: 0
- States: 21
- Modes: 0
- Transitions: 0
- Requirements: 2
- Constraints: 0
- Assumptions: 3
- Code files analyzed: 0
- Code constants extracted: 0
- Code comparisons extracted: 0

## Extraction Warnings

- ⚠️  No signals found. Add a '## Signals' section to your spec.
- ⚠️  No states found. Add a '## States' section to your spec.
- ⚠️  BT XML importer ignored unsupported node(s): RecoveryNode, PipelineSequence, RateController, ReactiveSequence, Inverter, ReactiveFallback, RoundRobin

_No findings at or above `LOW` (0 total findings exist)._