# ros2_control Joint Limits Slice — Analysis Note

## Source Style

This fixture is inspired by a small ros2_control / ros2_controllers review
slice: a position controller activates only after expected state interfaces are
ready, commands stay within a declared joint limit, and hardware error handling
pushes the controller into an error state within a bounded interval.

The included `controller.yaml` is illustrative controller configuration context
only. EAL is not parsing full ros2_control semantics here; the review input is
the EAL markdown spec plus YAML model.

## What Was Abstracted Into EAL Inputs

- interface claim and lifecycle activation before entering `ACTIVE`
- required `position` and `velocity` state feedback before command execution
- a nominal shoulder joint command limit
- timeout-backed return to `INACTIVE`
- bounded transition from `ACTIVE` to `ERROR` on hardware error

## What EAL Should Detect Here

This clean baseline is intended to review cleanly under
`--fail-on-severity HIGH`:

- activation preconditions are represented in the modeled guard
- the position limit appears as both a requirement and a mode constraint
- the error reaction timing requirement is backed by a timing parameter
- the forbidden active-state conditions are covered by guards or assumptions

## What EAL Is Not Proving

- Full ros2_control lifecycle or controller-manager semantics
- Correct runtime behavior of hardware plugins, interface claiming, or executor timing
- Closed-loop control correctness or hardware-in-the-loop safety evidence
