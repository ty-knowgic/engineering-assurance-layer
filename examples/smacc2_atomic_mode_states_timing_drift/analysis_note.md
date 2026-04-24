# SMACC2 Atomic Mode States — Timing Drift Variant Note

## Injected Defect

The code-side timing constant `MODE_SWITCH_RESPONSE_MS` is intentionally set to
`150`, while spec/model timing declarations require `<= 100 ms` transition
completion for `StModeA -> StModeB`.

## What EAL Should Detect

- `CODE_TIMING_MISMATCH`

## Why This Matters in Review

This is a realistic integration drift: architecture/spec and model still encode
one timing budget, but implementation constants have silently diverged. The
state-machine structure can still compile while violating declared response
budgets.

## Compile-Time Validation Coverage

SMACC2 compile-time validation focuses on state-machine construction integrity.
Cross-artifact timing-budget drift between review spec/model and external
integration constants is typically outside compile-time template checks.
