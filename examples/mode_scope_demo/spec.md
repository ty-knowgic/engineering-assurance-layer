# Mode Scope Demo — Engineering Specification

## Entities

- pressure_loop: mode-scoped pressure controller

## Signals

- pressure: actuator, bar, bounds=[0, 10]
- command_ready: internal, bool, bounds=[0, 1]

## Modes

- NORMAL: standard control profile
- CALIBRATION: constrained calibration profile

## States

- IDLE: awaiting command
- ACTIVE: pressure control active

## Transitions

- IDLE -> ACTIVE: guard=command_ready=true
- ACTIVE -> IDLE: guard=command_ready=false

## Requirements

- REQ-001: pressure must remain <= 2.0 in CALIBRATION mode.

## Assumptions

- ASM-001: Pressure sensor calibration is validated before operation.
