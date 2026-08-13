# Engineering Assurance Review Summary

**Run ID:** `eal-DEMO-NORMALIZED`
**Spec:** `demo/spec/nav2_motion_limits.md`
**Generated:** 1970-01-01T00:00:00+00:00
**Review status:** ⚠️ UNKNOWN
**Analysis status:** `INPUTS_NOT_FULLY_READ`
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

## What was NOT checked

**Hazard classes EAL does not check. A review that reports no findings says nothing about any of these. Measured by the adversarial evaluation in eval/, not asserted.**

Measured by adversarial evaluation: EAL detected 8 of 19 mutations that introduce a real hazard. 11 went undetected, in these classes:

- **Contradictory definitions in unexamined locations** (`conflicting_definitions`, worst observed hazard: moderate)  
  Duplicate keys in one mapping are detected. A second controller plugin block with contradictory limits is not: the importer resolves the first plugin entry and never inspects alternatives.
- **Physically implausible declared capability** (`false_safety_assumption`, worst observed hazard: severe)  
  EAL checks that declarations agree with each other, never that any of them is achievable. A platform declaring roughly ten g of braking, or zero actuation delay alongside a half-second control loop, is accepted without comment.
- **Slower control or perception loop** (`latency_increase`, worst observed hazard: severe)  
  Control frequency, costmap update rate, transform tolerance, and source timeouts are extracted as timing parameters but are never related to the speed the robot is permitted to travel. Sensor and actuator latency are absent from Nav2 configuration entirely and are not modelled at all.
- **Speed raised within an internally consistent configuration** (`max_speed_increase`, worst observed hazard: severe)  
  EAL compares the controller's declared limits against the downstream clamp. A speed increase applied to both keeps them in agreement and is not examined. Nothing relates speed to braking capability, sensor range, or stopping distance.
- **Weakened braking within an internally consistent configuration** (`min_decel_reduction`, worst observed hazard: severe)  
  As with speed: a deceleration limit lowered on both the controller and the smoother keeps them in agreement. Stopping distance is not modelled, so a coherent reduction in braking authority is invisible.
- **An entire configuration section absent** (`missing_parameter`, worst observed hazard: moderate)  
  A missing individual limit is reported as an incomplete comparison. A missing whole section, such as no velocity smoother at all, is treated as the check being inapplicable rather than unknown. That judgement is arguable and is recorded here so it stays visible.
- **Reduced sensing range or clearance margin** (`stopping_region_reduction`, worst observed hazard: severe)  
  Sensor marking range, raytrace range, and inflation radius are extracted but no check consumes them. A robot configured so that it cannot detect an obstacle in time to stop produces no finding.
- **Unit errors applied consistently** (`unit_mismatch`, worst observed hazard: moderate)  
  A unit conversion mistake made on both sides of a comparison is arithmetically coherent. EAL has no notion of a plausible magnitude for a physical quantity, so it cannot tell metres from feet or radians from degrees.

A result of no findings above means the checks that ran found nothing. It is not a statement that the configuration is safe, and it says nothing at all about any class listed here.

_No findings at or above `LOW` (0 total findings exist)._