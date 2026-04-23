# SMACC2 Atomic Mode States — Analysis Note

## Source Material Used

This fixture is based on publicly documented SMACC2 concepts and the reference
state-machine example family, with focus on the minimal `sm_atomic_mode_states`
pattern (states, events, transitions, mode-like behavior switching).

The EAL inputs here are manually abstracted from that style of design into
EAL's markdown+YAML review format. No automatic parser for SMACC2 C++ templates
or ROS 2 launch/runtime artifacts is used.

## What Was Abstracted Into EAL Inputs

- Two representative states (`StModeA`, `StModeB`)
- Two mode labels (`MODE_A`, `MODE_B`)
- Deterministic transition guards on `mode_request`
- A timing expectation for mode switch response (`within 100 ms`)
- Mode-scoped constraints for `mode_request` consistency

## What EAL Should Detect Here

This slice is intentionally configured as a clean baseline. EAL should report a
meaningful clean result under `--fail-on-severity HIGH`, showing that:

- transitions/states are structurally consistent
- mode-scoped constraints are satisfiable
- timing expectations are model-backed (parameter present)

## What EAL Is Not Expected To Prove

- Full SMACC2 behavior correctness across all asynchronous ROS 2 execution paths
- C++ template-level validity checks that SMACC2 performs at compile time
- Runtime correctness of event dispatching, orthogonal interactions, or executor scheduling

## How This Differs From SMACC2 Compile-Time Validation

SMACC2 compile-time validation checks the static correctness of state-machine
construction in C++ (types, transitions, and framework-level constraints).

EAL is a separate assurance slice that checks cross-artifact consistency
(spec/model and optional code where supported) and emits structured review
artifacts for governance and CI workflows.
