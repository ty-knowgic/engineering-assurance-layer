# SMACC2 Atomic Mode States — Assumption Gap Variant Note

## Injected Defect

The slice introduces `e_stop_active` as a safety-relevant signal in requirements
and safety constraints, but keeps assumptions limited to scheduling/ack behavior.
No assumption states detector reliability, latency guarantee, or certified
response behavior for e-stop signaling.

## What EAL Should Detect

- `MISSING_ASSUMPTION`

## Why This Matters in Review

State-machine structure can look correct while the assurance argument is still
incomplete. Safety behavior that depends on external detection quality requires
explicit assumption traceability for review readiness.

## Compile-Time Validation Coverage

Compile-time state-machine checks generally do not verify whether safety sensor
reliability assumptions are explicitly documented across spec/model artifacts.
