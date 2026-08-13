# Nav2 Motion Limit Coherence

Minimal review spec for the Nav2 demo. It states the intent being reviewed;
the numeric values come from the Nav2 configuration file supplied via
`--nav2-params`, not from this document.

## Entities

- nav2_stack: ROS 2 Nav2 navigation stack under review

## Requirements

- REQ-001: Motion limits declared by the local controller must be achievable through the command chain that reaches the robot base.
- REQ-002: The trajectory prediction horizon must not reach past the edge of the local costmap the planner has data for.

## Assumptions

- ASM-001: The velocity_smoother is present in the cmd_vel chain and is the last stage that clamps commanded motion before the base controller.
