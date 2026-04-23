# Complex Control System — Validation Testbed

## Entities

- reactor_core: thermal process vessel
- coolant_loop: closed-loop cooling subsystem
- heater_bank: electric heating subsystem
- emergency_circuit: hardware emergency shutdown circuit

## Signals

- pressure_bar: sensor, bar, bounds=[0, 12]
- coolant_flow_lps: sensor, lps, bounds=[0, 8]
- heater_power_kw: actuator, kw, bounds=[0, 40]
- reactor_temperature_c: sensor, c, bounds=[20, 500]
- e_stop_active: sensor, bool, bounds=[0, 1]

## Modes

- NORMAL: nominal process control
- CALIBRATION: calibration mode with reduced pressure envelope
- MAINTENANCE: maintenance mode with reduced heater envelope
- EMERGENCY: emergency shutdown mode

## States

- IDLE: process idle
- WARMUP: heating ramp before reaction phase
- REACTION: active reaction control
- SAFE_STOP: controlled shutdown sequence
- FAULT: faulted state awaiting intervention

## Transitions

- IDLE -> WARMUP: guard=start_command=true
- WARMUP -> REACTION: guard=temperature_ready=true
- REACTION -> SAFE_STOP: guard=e_stop_active=true
- REACTION -> FAULT: guard=pressure_fault=true
- SAFE_STOP -> IDLE: guard=fault_cleared=true

## Requirements

- REQ-001: reactor_temperature_c must remain <= 450 C in NORMAL mode.
- REQ-002: pressure_bar must remain <= 5.0 bar in CALIBRATION mode.
- REQ-003: Emergency stop shall transition system to SAFE_STOP within 120 ms.
- REQ-004: coolant_flow_lps must remain >= 2.0 lps in NORMAL mode.
- REQ-005: In MAINTENANCE mode, heater_power_kw must remain <= 20.0 kw.

## Assumptions

- ASM-001: Feedstock composition variation remains within validated process window.

## Safety Constraints

- CON-001: pressure_bar <= 5.0 when mode = CALIBRATION
- CON-002: heater_power_kw <= 20.0 when mode = MAINTENANCE

## Forbidden Conditions

- FC-001: heater_power_kw > 0 when coolant_flow_lps < 1.0

## Timing Constraints

- TC-001: REACTION -> SAFE_STOP within 120 ms of e_stop_active activation

