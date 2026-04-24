# ros2_control Joint Limits Slice — Interface Gap Analysis Note

## Intended Defect

This variant keeps the same joint limit and timing intent as the clean
baseline, but the modeled activation guard no longer references
`shoulder_velocity_state_ready`.

That drift represents a practical ros2_control review problem: the spec and
illustrative controller configuration still imply that both `position` and
`velocity` feedback must be available before the controller enters `ACTIVE`,
while the reviewed model slice allows activation with incomplete state
feedback.

## What EAL Should Detect

EAL should emit `FORBIDDEN_UNCHECKED` for the forbidden active-state condition:

- `FC-002: ACTIVE when shoulder_velocity_state_ready = 0`

The limit and timing declarations remain model-backed, so this fixture is not
trying to demonstrate limit or timing drift. It is a focused interface/guard
regression.

## Limits

As with the clean baseline, EAL is not proving full ros2_control semantics,
hardware-interface correctness, or runtime controller behavior. This is a
spec/model/config review artifact exercise.
