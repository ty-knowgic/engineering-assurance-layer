# System Interlock Demo Validation Note

## Scenario
Machine interlock design across spindle, clamp, and access-door subsystems with setup-mode speed limits and emergency-stop response requirements.

## What EAL should detect today
- Interlock structure issues such as undefined transition targets (`TRANSITION_GAP`).
- Undefined requirement references (`UNDEFINED_REFERENCE`) for undeclared interface/sensor names.
- Unguarded forbidden conditions (`FORBIDDEN_UNCHECKED`).
- Code/spec-model speed and timing threshold mismatches (`CODE_BOUND_MISMATCH`, `CODE_TIMING_MISMATCH`).

## What EAL is not expected to prove
- Complete interlock PLC logic correctness.
- Exhaustive deadlock/liveness guarantees across all runtime conditions.
- Runtime I/O synchronization correctness.

## Expected finding style
A mixed set of structural, requirement-quality, and code-threshold findings that show practical review value on subsystem interlock designs.

