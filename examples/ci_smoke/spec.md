# CI Smoke Example — Engineering Specification

## Entities

- test_bench: deterministic CI smoke fixture

## Signals

- speed: actuator, m/s, bounds=[0, 5]
- command: internal, level, bounds=[0, 1]

## Modes

- NORMAL: nominal operation

## States

- IDLE: waiting for command
- RUNNING: active motion state

## Transitions

- IDLE -> RUNNING: guard=command == 1
- RUNNING -> IDLE: guard=command == 0

## Requirements

- REQ-001: speed must remain <= 4.0 in NORMAL mode.

## Assumptions

- ASM-001: Actuator calibration is verified before operation.

## Safety Constraints

- CON-001: speed <= 4.0 when mode = NORMAL
