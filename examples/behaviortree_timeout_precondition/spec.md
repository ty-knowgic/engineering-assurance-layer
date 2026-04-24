# BehaviorTree Timeout and Precondition Slice

## Entities

- bt_navigation_slice: behavior-tree-oriented navigation assurance slice
- bt_runtime: timeout and fallback execution runtime

## Signals

- goal_requested: internal, bool, bounds=[0, 1]
- battery_ok: sensor, bool, bounds=[0, 1]
- localization_ready: sensor, bool, bounds=[0, 1]
- navigation_timeout: internal, bool, bounds=[0, 1]
- recovery_retry_count: internal, count, bounds=[0, 1]

## Modes

- AUTO_NAV: nominal autonomous navigation mode

## States

- IDLE: no goal active
- PRECHECK: evaluating action preconditions
- NAVIGATING: main NavigateToPose action is active
- RECOVERING: fallback recovery branch is active
- ABORTED: recovery exhausted or navigation canceled

## Transitions

- IDLE -> PRECHECK: guard=goal_requested == true
- PRECHECK -> NAVIGATING: guard=battery_ok == true and localization_ready == true
- NAVIGATING -> RECOVERING: guard=navigation_timeout == true
- RECOVERING -> ABORTED: guard=recovery_retry_count >= 1

## Requirements

- REQ-001: NavigateToPose shall execute only when battery_ok = 1 and localization_ready = 1.
- REQ-002: If NavigateToPose does not report success within 100 ms, the tree shall enter RECOVERING.
- REQ-003: recovery_retry_count must remain <= 1 in AUTO_NAV mode.

## Assumptions

- ASM-001: The timeout decorator raises navigation_timeout within 5 ms of the configured limit expiring.
- ASM-002: The recovery branch issues at most one retry request per timeout event.

## Safety Constraints

- CON-001: recovery_retry_count <= 1 when mode = AUTO_NAV

## Forbidden Conditions

- FC-001: NAVIGATING when localization_ready = 0
- FC-002: NAVIGATING when battery_ok = 0

## Timing Constraints

- TC-001: NAVIGATING -> RECOVERING within 100 ms of navigation_timeout activation
