# SMACC2 Atomic Mode States — Transition Guard Gap Analysis Note

## Injected Defect

This variant keeps the baseline SMACC2 slice structure but injects one
transition-intent defect:

- Spec declares `FC-001` forbidding `StModeA -> StModeB` when `e_stop_active = 1`.
- Model transitions do not encode any `e_stop_active` guard for that edge.

## Expected EAL Signal

EAL should report `FORBIDDEN_UNCHECKED` because the forbidden transition
condition is not enforced by transition guards and no assumption explicitly
binds `e_stop_active` to transition blocking behavior.

## Why This Matters

In a state-machine review, this is a meaningful safety drift: transition intent
is declared in review artifacts but not reflected in executable transition
conditions.

SMACC2 compile-time validation can prove structural correctness of state-machine
construction, but this cross-artifact intent mismatch is the assurance slice
EAL is designed to surface.
