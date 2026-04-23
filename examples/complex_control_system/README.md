# Complex Control System Validation Note

## Scenario
Thermal process controller with multiple operating modes, shutdown timing requirements, and pressure/heater safety envelopes.

## What EAL should detect today
- Mode-scoped unsatisfiable constraints (`UNSAT_IN_MODE` / `MODE_SCOPED_CONFLICT`) for calibration pressure limits.
- Code/spec-model bound mismatch (`CODE_BOUND_MISMATCH`) for pressure/heater constants.
- Code/spec-model timing mismatch (`CODE_TIMING_MISMATCH`) for emergency-stop response constants.

## What EAL is not expected to prove
- Full closed-loop control stability.
- Continuous-time dynamics correctness.
- Controller implementation correctness beyond extracted constants/comparisons.

## Expected finding style
High/critical findings concentrated on mode scope contradictions and code-declared thresholds that violate declared engineering envelopes.

