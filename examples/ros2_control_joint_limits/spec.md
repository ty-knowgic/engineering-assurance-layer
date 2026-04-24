# ros2_control Joint Limits Slice

## Entities

- arm_position_controller: ros2_control-style joint position controller
- shoulder_joint_hw: hardware interface for shoulder_joint
- elbow_joint_hw: hardware interface for elbow_joint

## Signals

- interfaces_claimed: internal, bool, bounds=[0, 1]
- lifecycle_active: internal, bool, bounds=[0, 1]
- shoulder_position_state_ready: internal, bool, bounds=[0, 1]
- shoulder_velocity_state_ready: internal, bool, bounds=[0, 1]
- shoulder_position_command_rad: actuator, rad, bounds=[-1.2, 1.2]
- command_timeout: internal, bool, bounds=[0, 1]
- hardware_error: internal, bool, bounds=[0, 1]
- reset_ack: internal, bool, bounds=[0, 1]

## Modes

- NOMINAL: controller is serving commanded joint positions

## States

- UNCONFIGURED: controller not configured
- INACTIVE: controller configured but not accepting commands
- ACTIVE: command interfaces are active and publishing setpoints
- ERROR: hardware or controller error latched

## Transitions

- UNCONFIGURED -> INACTIVE: guard=interfaces_claimed == true
- INACTIVE -> ACTIVE: guard=lifecycle_active == true and shoulder_position_state_ready == true and shoulder_velocity_state_ready == true
- ACTIVE -> INACTIVE: guard=command_timeout == true
- ACTIVE -> ERROR: guard=hardware_error == true
- ERROR -> INACTIVE: guard=reset_ack == true and lifecycle_active == true

## Requirements

- REQ-001: The controller shall enter ACTIVE only when shoulder_position_state_ready = 1 and shoulder_velocity_state_ready = 1.
- REQ-002: shoulder_position_command_rad must remain <= 1.2 rad in NOMINAL mode.
- REQ-003: If hardware_error = 1, the controller shall enter ERROR within 20 ms.
- REQ-004: command_timeout shall return the controller to INACTIVE before further position commands are accepted.

## Assumptions

- ASM-001: The hardware interface exposes claimed command interfaces before activation is requested.
- ASM-002: The driver latches hardware_error within 5 ms of a detected actuator anomaly.

## Safety Constraints

- CON-001: shoulder_position_command_rad <= 1.2 when mode = NOMINAL

## Forbidden Conditions

- FC-001: ACTIVE when shoulder_position_state_ready = 0
- FC-002: ACTIVE when shoulder_velocity_state_ready = 0
- FC-003: ACTIVE when lifecycle_active = 0

## Timing Constraints

- TC-001: ACTIVE -> ERROR within 20 ms of hardware_error activation
