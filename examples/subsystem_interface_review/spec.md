# Subsystem Interface Review — Validation Testbed

## Entities

- drive_controller: traction subsystem controller
- arm_controller: manipulator subsystem controller
- interface_gateway: command and telemetry gateway
- safety_supervisor: safety supervision subsystem

## Signals

- drive_speed_mps: actuator, mps, bounds=[0, 2.0]
- arm_torque_nm: actuator, nm, bounds=[0, 60]
- interface_latency_ms: timing, ms, bounds=[0, 80]
- watchdog_timeout_ms: timing, ms, bounds=[0, 90]
- safety_channel_ok: sensor, bool, bounds=[0, 1]
- e_stop_active: sensor, bool, bounds=[0, 1]

## Modes

- NORMAL: coordinated mobile manipulation
- DOCKING: low-speed docking operation
- SERVICE: service mode with reduced torque limit

## States

- IDLE: awaiting command
- COORDINATED_RUN: drive and arm coordinated operation
- DEGRADED: reduced capability mode
- SAFE_STOP: emergency hold state

## Transitions

- IDLE -> COORDINATED_RUN: guard=mission_ready=true
- COORDINATED_RUN -> DEGRADED: guard=interface_crc_error=true
- COORDINATED_RUN -> SAFE_STOP: guard=e_stop_active=true
- DEGRADED -> SAFE_STOP: guard=watchdog_timeout=true
- SAFE_STOP -> IDLE: guard=reset_ack=true

## Requirements

- REQ-001: drive_speed_mps must remain <= 0.6 mps in DOCKING mode.
- REQ-002: interface_latency_ms must remain <= 80 ms.
- REQ-003: Emergency stop shall transition interface to SAFE_STOP within 90 ms.
- REQ-004: torque_feedback_crc must remain = 0 during COORDINATED_RUN.
- REQ-005: arm_torque_nm must remain <= 15 nm in SERVICE mode.

## Assumptions

- ASM-001: Interface transport latency is guaranteed below 40 ms under validated network load.

## Safety Constraints

- CON-001: drive_speed_mps <= 0.6 when mode = DOCKING
- CON-002: arm_torque_nm <= 15 when mode = SERVICE

## Forbidden Conditions

- FC-001: arm_torque_nm > 0 when safety_channel_ok = 0

## Timing Constraints

- TC-001: COORDINATED_RUN -> SAFE_STOP within 90 ms of e_stop_active activation

