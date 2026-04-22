# Robotics Arm Controller — Engineering Specification

## System Overview

6-DOF articulated robot arm for collaborative assembly tasks.
Operates in a shared workspace with human operators.

## Entities

- robot_arm: 6-DOF articulated manipulator
- gripper: pneumatic end-effector
- proximity_sensor: IR-based human presence detector
- e_stop: hardware emergency stop button and watchdog

## Signals

- joint_speed: sensor, rad/s, bounds=[0, 2.5]
- motor_torque: actuator, Nm
- human_detected: sensor, bool, bounds=[0, 1]
- e_stop_active: sensor, bool, bounds=[0, 1]
- gripper_force: actuator, N, bounds=[0, 80]
- arm_position: sensor, deg

<!-- INTENTIONAL ISSUE: motor_torque has no upper bound defined -->
<!-- INTENTIONAL ISSUE: arm_position has no upper bound defined -->

## Modes

- NORMAL: standard collaborative operation
- CALIBRATION: factory calibration routine, reduced speed
- MAINTENANCE: manual override mode, reduced torque limit
- EMERGENCY: system halted, all actuators de-energised

## States

- IDLE: system initialised, awaiting task
- OPERATING: executing motion plan
- SAFE_STOP: controlled deceleration to standstill
- FAULT: unrecoverable error, requires operator reset

## Transitions

- IDLE -> OPERATING: guard=task_ready
- OPERATING -> SAFE_STOP: guard=e_stop_active=true
- OPERATING -> FAULT: guard=motor_overtemp=true
- SAFE_STOP -> IDLE: guard=fault_cleared
- FAULT -> IDLE: guard=operator_reset=true

<!-- INTENTIONAL ISSUE: transition references undefined state RECOVERY -->
- FAULT -> RECOVERY: guard=auto_recovery=true

## Requirements

- REQ-001: Joint speed must remain <= 1.2 rad/s in CALIBRATION mode.
- REQ-002: The gripper must not close when human_detected = true.
- REQ-003: Emergency stop shall transition system to SAFE_STOP within 100 ms.
- REQ-004: In MAINTENANCE mode, motor_torque must remain <= 10 Nm.
- REQ-005: arm_position must not exceed 270 deg during OPERATING state.
- REQ-006: The undefined_sensor reading must stay below threshold during operation.

<!-- INTENTIONAL ISSUE: REQ-006 references undefined_sensor which is not in ## Signals -->

## Assumptions

- ASM-001: The proximity sensor latency is < 10 ms under normal operating conditions.

<!-- INTENTIONAL ISSUE: No assumption about e_stop hardware response time -->
<!-- INTENTIONAL ISSUE: No assumption about sensor reliability for safety constraints -->

## Safety Constraints

- CON-001: motor_torque <= 10 Nm when mode = MAINTENANCE
- CON-002: joint_speed <= 1.2 rad/s when mode = CALIBRATION

## Forbidden Conditions

- FC-001: gripper_force > 0 when human_detected = true
- FC-002: mode = NORMAL when e_stop_active = true

<!-- INTENTIONAL ISSUE: FC-001 and FC-002 have no guard in ## Transitions -->

## Timing Constraints

- TC-001: OPERATING -> SAFE_STOP within 100 ms of e_stop_active activation

<!-- INTENTIONAL ISSUE: No timing parameter defined in model.yaml -->
