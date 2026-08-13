# Constraint Violations

## F-001 — Controller declares linear acceleration limit 1.20x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `ax_max` = 3.0 m/s^2 (controller_server.ros__parameters.FollowPath.ax_max); downstream velocity_smoother `max_accel[0]` = 2.5 m/s^2 (velocity_smoother.ros__parameters.max_accel[0]). The controller's figure exceeds the smoother's by 1.20x, and the smoother is what the base actually receives.

**Details:** The controller rolls out and validates candidate trajectories against its own figure. Because the smoother caps what actually reaches the base, a trajectory accepted as feasible or collision-free under the controller's figure may not be achievable in execution. This leans in the unsafe direction. Whether this is a defect depends on intent, which is not recorded in the configuration: a generically-tuned controller paired with a platform-tuned smoother can produce this legitimately. EAL reports both values and the direction; the judgement is yours.

**Related IR nodes:** NAV2-CONTROLLER_A_ACCEL_LINEAR, NAV2-SMOOTHER_A_ACCEL_LINEAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_params.yaml:controller_server.ros__parameters.FollowPath.ax_max, tests/fixtures/nav2_upstream_params/nav2_params.yaml:velocity_smoother.ros__parameters.max_accel[0]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_accel[0]` to 3.0, or lower `ax_max` to 2.5, whichever matches the platform's real capability.

---

## F-002 — Controller declares linear deceleration limit 1.20x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `ax_min` = -3.0 m/s^2 (controller_server.ros__parameters.FollowPath.ax_min); downstream velocity_smoother `max_decel[0]` = -2.5 m/s^2 (velocity_smoother.ros__parameters.max_decel[0]). The controller's figure exceeds the smoother's by 1.20x, and the smoother is what the base actually receives.

**Details:** The controller rolls out and validates candidate trajectories against its own figure. Because the smoother caps what actually reaches the base, a trajectory accepted as feasible or collision-free under the controller's figure may not be achievable in execution. This leans in the unsafe direction. Whether this is a defect depends on intent, which is not recorded in the configuration: a generically-tuned controller paired with a platform-tuned smoother can produce this legitimately. EAL reports both values and the direction; the judgement is yours.

**Related IR nodes:** NAV2-CONTROLLER_A_DECEL_LINEAR, NAV2-SMOOTHER_A_DECEL_LINEAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_params.yaml:controller_server.ros__parameters.FollowPath.ax_min, tests/fixtures/nav2_upstream_params/nav2_params.yaml:velocity_smoother.ros__parameters.max_decel[0]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_decel[0]` to -3.0, or lower `ax_min` to -2.5, whichever matches the platform's real capability.

---

## F-003 — Controller declares angular acceleration limit 1.09x the downstream smoother limit

**Severity:** 🟠 HIGH  
**Category:** NAV2_ACCEL_OVERDECLARED  

**Summary:** Controller `az_max` = 3.5 rad/s^2 (controller_server.ros__parameters.FollowPath.az_max); downstream velocity_smoother `max_accel[2]` = 3.2 rad/s^2 (velocity_smoother.ros__parameters.max_accel[2]). The controller's figure exceeds the smoother's by 1.09x, and the smoother is what the base actually receives.

**Details:** The controller rolls out and validates candidate trajectories against its own figure. Because the smoother caps what actually reaches the base, a trajectory accepted as feasible or collision-free under the controller's figure may not be achievable in execution. This leans in the unsafe direction. Whether this is a defect depends on intent, which is not recorded in the configuration: a generically-tuned controller paired with a platform-tuned smoother can produce this legitimately. EAL reports both values and the direction; the judgement is yours.

**Related IR nodes:** NAV2-CONTROLLER_A_ACCEL_ANGULAR, NAV2-SMOOTHER_A_ACCEL_ANGULAR

**Source refs:** tests/fixtures/nav2_upstream_params/nav2_params.yaml:controller_server.ros__parameters.FollowPath.az_max, tests/fixtures/nav2_upstream_params/nav2_params.yaml:velocity_smoother.ros__parameters.max_accel[2]

**Suggested fix:** Reconcile the two declarations: either raise `velocity_smoother.max_accel[2]` to 3.5, or lower `az_max` to 3.2, whichever matches the platform's real capability.

---
