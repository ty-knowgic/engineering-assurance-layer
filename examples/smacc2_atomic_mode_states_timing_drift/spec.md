# SMACC2 Atomic Mode States — Timing Drift Variant

## Entities

- smacc2_atomic_mode_machine: minimal event-driven state-machine slice adapted for EAL review

## Signals

- mode_request: internal, bool, bounds=[0, 1]
- transition_ack: internal, bool, bounds=[0, 1]
- state_residency_ms: timing, ms, bounds=[0, 500]

## Modes

- MODE_A: first atomic behavior mode
- MODE_B: second atomic behavior mode

## States

- StModeA: active behavior for mode A
- StModeB: active behavior for mode B

## Transitions

- StModeA -> StModeB: guard=mode_request == 1
- StModeB -> StModeA: guard=mode_request == 0

## Requirements

- REQ-001: mode_request must remain <= 1 in MODE_A mode.
- REQ-002: mode_request must remain <= 1 in MODE_B mode.
- REQ-003: Transition StModeA -> StModeB shall complete within 100 ms of mode_request activation.

## Assumptions

- ASM-001: Runtime executor scheduling jitter remains below 20 ms.
- ASM-002: transition_ack is asserted by the integration layer on successful state entry.

## Safety Constraints

- CON-001: mode_request <= 1 when mode = MODE_A
- CON-002: mode_request <= 1 when mode = MODE_B

## Forbidden Conditions

- FC-001: mode_request > 1 in MODE_A mode

## Timing Constraints

- TC-001: StModeA -> StModeB within 100 ms of mode_request activation
