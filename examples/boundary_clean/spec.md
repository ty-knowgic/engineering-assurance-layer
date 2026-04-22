# Boundary Clean Example — Engineering Specification

## Entities

- conveyor_unit: deterministic boundary-clean fixture

## Signals

- conveyor_speed: actuator, m/s, bounds=[0, 1.0]
- start_command: internal, bool, bounds=[0, 1]
- stop_command: internal, bool, bounds=[0, 1]

## Modes

- NORMAL: nominal operation

## States

- IDLE: waiting for start
- RUNNING: conveyor active
- STOPPED: conveyor halted

## Transitions

- IDLE -> RUNNING: guard=start_command=true
- RUNNING -> STOPPED: guard=stop_command=true

## Requirements

- REQ-001: conveyor_speed must remain <= 1.0 in NORMAL mode.
- REQ-002: Control loop response shall complete within 50 ms.

## Assumptions

- ASM-001: Control loop timing is guaranteed by hardware monitor.

## Safety Constraints

- CON-001: conveyor_speed <= 1.0 when mode = NORMAL

## Timing Constraints

- TC-001: RUNNING -> STOPPED within 50 ms
