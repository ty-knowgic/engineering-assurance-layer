# Engineering Assurance Review Summary

**Run ID:** `eal-DEMO-NORMALIZED`
**Spec:** `demo/spec/nav2_motion_limits.md`
**Generated:** 1970-01-01T00:00:00+00:00
**Review status:** ❌ REVIEW REQUIRED
**Analysis status:** `INPUTS_FULLY_READ`
**Coverage gaps:** `0`
**Highest severity found:** `HIGH`
**Gate threshold:** `HIGH`
**Gate result:** ❌ THRESHOLD EXCEEDED
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

## Top Findings

_Showing findings at or above `LOW` (3 of 3 total)._

- 🟠 **F-001** [NAV2_ACCEL_OVERDECLARED] Controller declares linear acceleration limit 1.20x the downstream smoother limit
- 🟠 **F-002** [NAV2_ACCEL_OVERDECLARED] Controller declares linear deceleration limit 1.20x the downstream smoother limit
- 🟠 **F-003** [NAV2_ACCEL_OVERDECLARED] Controller declares angular acceleration limit 1.09x the downstream smoother limit