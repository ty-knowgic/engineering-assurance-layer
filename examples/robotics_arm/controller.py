"""
Robotics arm controller — illustrative Python stub.
Included for code-input demonstration only.
"""

MAX_JOINT_SPEED = 1.5  # NOTE: inconsistent with spec/model calibration bound (1.2)
ESTOP_RESPONSE_MS = 150  # NOTE: inconsistent with spec timing constraint (100 ms)
MAX_TORQUE_MAINTENANCE = 10.0


def check_speed_limit(joint_speed: float, mode: str) -> bool:
    if mode == "CALIBRATION":
        return joint_speed <= MAX_JOINT_SPEED  # Bug: uses 1.5, spec says 1.2
    return True


def emergency_stop_handler(e_stop_active: bool, elapsed_ms: float, current_state: str) -> str:
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    if e_stop_active:
        return "SAFE_STOP"
    return current_state


def gripper_interlock(human_detected: bool, gripper_force: float) -> float:
    # Missing: should force gripper_force = 0 when human_detected
    return gripper_force  # Bug: no interlock applied
