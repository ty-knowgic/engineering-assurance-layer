# System Interlock Demo — Validation Testbed

## Entities

- spindle_unit: rotating tool subsystem
- clamp_unit: workpiece clamp subsystem
- safety_door: machine access door subsystem
- interlock_plc: interlock logic controller

## Signals

- spindle_speed_rpm: sensor, rpm, bounds=[0, 500]
- clamp_pressure_bar: sensor, bar, bounds=[0, 10]
- door_closed: sensor, bool, bounds=[0, 1]
- interlock_channel_ok: sensor, bool, bounds=[0, 1]
- e_stop_active: sensor, bool, bounds=[0, 1]

## Modes

- AUTO: production machining mode
- SETUP: setup mode with lower speed limit
- MAINTENANCE: maintenance mode

## States

- IDLE: machine idle
- ARMED: interlocks satisfied and ready
- MACHINING: spindle active
- SAFE_STOP: machine decelerating to standstill

## Transitions

- IDLE -> ARMED: guard=interlock_channel_ok=true
- ARMED -> MACHINING: guard=door_closed=true
- MACHINING -> SAFE_STOP: guard=e_stop_active=true
- SAFE_STOP -> RECOVERY: guard=reset_ack=true

## Requirements

- REQ-001: spindle_speed_rpm must remain <= 300 rpm in SETUP mode.
- REQ-002: Emergency stop shall transition system to SAFE_STOP within 200 ms.
- REQ-003: latch_sensor_fault must remain = 0 during MACHINING.
- REQ-004: clamp_pressure_bar must remain >= 2.0 bar when spindle_speed_rpm > 0.

## Assumptions

- ASM-001: Operators verify fixture alignment before startup.

## Safety Constraints

- CON-001: spindle_speed_rpm <= 300 when mode = SETUP

## Forbidden Conditions

- FC-001: spindle_speed_rpm > 0 when door_closed = 0
- FC-002: clamp_pressure_bar < 2.0 when spindle_speed_rpm > 0

## Timing Constraints

- TC-001: MACHINING -> SAFE_STOP within 200 ms of e_stop_active activation

