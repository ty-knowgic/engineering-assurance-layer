# Code Mismatch Demo — Engineering Specification

## Entities

- robot_arm: controller under review

## Signals

- joint_speed: actuator, rad/s, bounds=[0, 1.2]
- e_stop_active: sensor, bool, bounds=[0, 1]

## Modes

- NORMAL: standard operation
- EMERGENCY: emergency handling mode

## States

- OPERATING: executing motion
- SAFE_STOP: controlled halt

## Transitions

- OPERATING -> SAFE_STOP: guard=e_stop_active=true

## Requirements

- REQ-001: joint_speed must remain <= 1.2 in NORMAL mode.
- REQ-002: Emergency stop shall transition system to SAFE_STOP within 100 ms of e_stop_active activation.

## Assumptions

- ASM-001: The e_stop sensor response is guaranteed within 20 ms by certified hardware.

## Safety Constraints

- CON-001: joint_speed <= 1.2 when mode = NORMAL

## Timing Constraints

- TC-001: OPERATING -> SAFE_STOP within 100 ms of e_stop_active activation
