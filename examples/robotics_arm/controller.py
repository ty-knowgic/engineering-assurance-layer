"""
Robotics arm controller — illustrative Python stub.
Included for code-input demonstration only.
"""

MAX_SPEED_CALIBRATION = 1.5  # NOTE: inconsistent with spec REQ-001 (should be 1.2)
MAX_TORQUE_MAINTENANCE = 10.0


def check_speed_limit(joint_speed: float, mode: str) -> bool:
    if mode == "CALIBRATION":
        return joint_speed <= MAX_SPEED_CALIBRATION  # Bug: uses 1.5, spec says 1.2
    return True


def emergency_stop_handler(e_stop_active: bool, current_state: str) -> str:
    if e_stop_active:
        return "SAFE_STOP"
    return current_state


def gripper_interlock(human_detected: bool, gripper_force: float) -> float:
    # Missing: should force gripper_force = 0 when human_detected
    return gripper_force  # Bug: no interlock applied
