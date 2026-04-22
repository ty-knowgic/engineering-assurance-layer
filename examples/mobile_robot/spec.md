# Mobile Robot Navigation — Engineering Specification

## System Overview

Autonomous mobile robot for indoor warehouse navigation.
Shares floor space with human workers and forklifts.

## Entities

- mobile_base: differential-drive mobile platform
- lidar: 2D laser range finder for obstacle detection
- battery: lithium-ion battery pack
- charging_dock: fixed docking station

## Signals

- linear_velocity: actuator, m/s, bounds=[0, 2.0]
- angular_velocity: actuator, rad/s, bounds=[-1.5, 1.5]
- battery_level: sensor, percent, bounds=[0, 100]
- obstacle_distance: sensor, m, bounds=[0, 10]
- dock_aligned: sensor, bool, bounds=[0, 1]

## Modes

- NAVIGATION: autonomous path following
- DOCKING: approach and connect to charging dock
- CHARGING: battery charging in progress
- STANDBY: idle, low-power state
- FAULT: hardware or software fault detected

## States

- MOVING: platform in motion
- STOPPED: platform stationary
- DOCKING_APPROACH: moving toward dock
- CHARGING_ACTIVE: connected to dock, charging
- ERROR: unrecoverable fault

## Transitions

- STOPPED -> MOVING: guard=path_available=true
- MOVING -> STOPPED: guard=obstacle_distance <= 0.3
- STOPPED -> DOCKING_APPROACH: guard=battery_level <= 20
- DOCKING_APPROACH -> CHARGING_ACTIVE: guard=dock_aligned=true
- CHARGING_ACTIVE -> STOPPED: guard=battery_level >= 90

<!-- INTENTIONAL ISSUE: no transition from MOVING to DOCKING_APPROACH -->
<!-- Robot can only start docking from STOPPED, but what if battery dies while MOVING? -->

## Requirements

- REQ-001: linear_velocity must be 0 when mode = CHARGING.
- REQ-002: The robot must transition to STOPPED when obstacle_distance <= 0.3 m.
- REQ-003: Battery level must trigger DOCKING mode when battery_level <= 20 percent.
- REQ-004: In NAVIGATION mode, obstacle avoidance shall respond within 200 ms.
- REQ-005: angular_velocity must not exceed 1.0 rad/s when linear_velocity > 1.5 m/s.

<!-- INTENTIONAL ISSUE: No timing parameter for REQ-004 (200 ms response) -->

## Assumptions

- ASM-001: The LiDAR operates with a scan frequency of >= 10 Hz.
- ASM-002: The charging dock supplies 24V at >= 10A.

<!-- INTENTIONAL ISSUE: No assumption about obstacle detection latency -->
<!-- INTENTIONAL ISSUE: No assumption about battery sensor accuracy -->

## Safety Constraints

- CON-001: linear_velocity = 0 when mode = CHARGING
- CON-002: linear_velocity <= 0.5 when obstacle_distance <= 1.0

## Forbidden Conditions

- FC-001: linear_velocity > 0 when mode = CHARGING
- FC-002: mode = NAVIGATION when battery_level <= 5

<!-- INTENTIONAL ISSUE: FC-002 has no guard transition enforcing it -->
<!-- INTENTIONAL ISSUE: No invariant preventing NAVIGATION + CHARGING simultaneously -->

## Timing Constraints

- TC-001: Obstacle detection response shall cause MOVING -> STOPPED within 200 ms
- TC-002: Docking alignment shall complete within 30 seconds of DOCKING_APPROACH entry

<!-- INTENTIONAL ISSUE: Neither 200ms nor 30s has a parameter in the model -->
