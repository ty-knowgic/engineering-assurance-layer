# Constraint Violations

## F-001 — Controller declares linear acceleration limit 1.20x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `ax_max` = 3.0 m/s^2 (controller_server.ros__parameters.FollowPath.ax_max); downstream velocity_smoother `max_accel[0]` = 2.5 m/s^2 (velocity_smoother.ros__parameters.max_accel[0]). The controller's figure exceeds the smoother's by 1.20x. In the default bringup chain the smoother bounds what reaches the base.

**Details:** The velocity_smoother expresses the platform's hard limits; the controller expresses what it would like to do, which may legitimately be less. Declaring more than the hard limit inverts that relationship: the controller is planning with capability the platform is not configured to deliver. The two are intended to be set independently, with the controller permitted to sit below the platform's hard limit — but not above it. Nav2 maintainer, ros-navigation/navigation2#6357 (2026-08-14): "they are intended to be differently defined such that there can be different limits in different situations... The velocity smoother is more enforcing hard limitations than behavioral desires that a controller may compute as part of what it would like to do." Asked about this exact pair of defaults in nav2_params.yaml, the same maintainer replied that the mismatch is "odd and unintentional". EAL still reports the values and the direction rather than ruling on your configuration; your stack may have a reason. But over-declaration is not the intended use of this pair. This comparison holds only under two assumptions the parameter file cannot establish: that the plugin evaluated here is the controller the goal selects (FollowPath chooses one per goal by controller_id), and that the deployed graph follows the default bringup chain, with velocity_smoother between the controller and the base. The smoother figure is a declaration of what the platform is configured to enforce, not evidence of what it can physically do.

**Related IR nodes:** NAV2-CONTROLLER_A_ACCEL_LINEAR, NAV2-SMOOTHER_A_ACCEL_LINEAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:controller_server.ros__parameters.FollowPath.ax_max, tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:velocity_smoother.ros__parameters.max_accel[0]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_accel[0]` to 3.0, or lower `ax_max` to 2.5, whichever matches the platform's real capability. Lowering the controller asserts nothing new; raising the smoother asserts that the hardware can deliver 3.0 m/s^2 and needs measured evidence.

---

## F-002 — Controller declares linear deceleration limit 1.20x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `ax_min` = -3.0 m/s^2 (controller_server.ros__parameters.FollowPath.ax_min); downstream velocity_smoother `max_decel[0]` = -2.5 m/s^2 (velocity_smoother.ros__parameters.max_decel[0]). The controller's figure exceeds the smoother's by 1.20x. In the default bringup chain the smoother bounds what reaches the base.

**Details:** The velocity_smoother expresses the platform's hard limits; the controller expresses what it would like to do, which may legitimately be less. Declaring more than the hard limit inverts that relationship: the controller is planning with capability the platform is not configured to deliver. The two are intended to be set independently, with the controller permitted to sit below the platform's hard limit — but not above it. Nav2 maintainer, ros-navigation/navigation2#6357 (2026-08-14): "they are intended to be differently defined such that there can be different limits in different situations... The velocity smoother is more enforcing hard limitations than behavioral desires that a controller may compute as part of what it would like to do." Asked about this exact pair of defaults in nav2_params.yaml, the same maintainer replied that the mismatch is "odd and unintentional". EAL still reports the values and the direction rather than ruling on your configuration; your stack may have a reason. But over-declaration is not the intended use of this pair. This comparison holds only under two assumptions the parameter file cannot establish: that the plugin evaluated here is the controller the goal selects (FollowPath chooses one per goal by controller_id), and that the deployed graph follows the default bringup chain, with velocity_smoother between the controller and the base. The smoother figure is a declaration of what the platform is configured to enforce, not evidence of what it can physically do.

**Related IR nodes:** NAV2-CONTROLLER_A_DECEL_LINEAR, NAV2-SMOOTHER_A_DECEL_LINEAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:controller_server.ros__parameters.FollowPath.ax_min, tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:velocity_smoother.ros__parameters.max_decel[0]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_decel[0]` to -3.0, or lower `ax_min` to -2.5, whichever matches the platform's real capability. Lowering the controller asserts nothing new; raising the smoother asserts that the hardware can deliver -3.0 m/s^2 and needs measured evidence.

---

## F-003 — Controller declares angular acceleration limit 1.09x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `az_max` = 3.5 rad/s^2 (controller_server.ros__parameters.FollowPath.az_max); downstream velocity_smoother `max_accel[2]` = 3.2 rad/s^2 (velocity_smoother.ros__parameters.max_accel[2]). The controller's figure exceeds the smoother's by 1.09x. In the default bringup chain the smoother bounds what reaches the base.

**Details:** The velocity_smoother expresses the platform's hard limits; the controller expresses what it would like to do, which may legitimately be less. Declaring more than the hard limit inverts that relationship: the controller is planning with capability the platform is not configured to deliver. The two are intended to be set independently, with the controller permitted to sit below the platform's hard limit — but not above it. Nav2 maintainer, ros-navigation/navigation2#6357 (2026-08-14): "they are intended to be differently defined such that there can be different limits in different situations... The velocity smoother is more enforcing hard limitations than behavioral desires that a controller may compute as part of what it would like to do." Asked about this exact pair of defaults in nav2_params.yaml, the same maintainer replied that the mismatch is "odd and unintentional". EAL still reports the values and the direction rather than ruling on your configuration; your stack may have a reason. But over-declaration is not the intended use of this pair. This comparison holds only under two assumptions the parameter file cannot establish: that the plugin evaluated here is the controller the goal selects (FollowPath chooses one per goal by controller_id), and that the deployed graph follows the default bringup chain, with velocity_smoother between the controller and the base. The smoother figure is a declaration of what the platform is configured to enforce, not evidence of what it can physically do.

**Related IR nodes:** NAV2-CONTROLLER_A_ACCEL_ANGULAR, NAV2-SMOOTHER_A_ACCEL_ANGULAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:controller_server.ros__parameters.FollowPath.az_max, tests/fixtures/nav2_upstream_params/nav2_no_map_params.yaml:velocity_smoother.ros__parameters.max_accel[2]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_accel[2]` to 3.5, or lower `az_max` to 3.2, whichever matches the platform's real capability. Lowering the controller asserts nothing new; raising the smoother asserts that the hardware can deliver 3.5 rad/s^2 and needs measured evidence.

---
