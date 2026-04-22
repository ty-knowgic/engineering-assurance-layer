"""
Code mismatch demo controller.
This file intentionally violates spec/model limits.
"""

MAX_JOINT_SPEED = 1.5
ESTOP_RESPONSE_MS = 150


def speed_guard(joint_speed: float, mode: str) -> bool:
    if mode == "NORMAL":
        return joint_speed <= MAX_JOINT_SPEED
    return True


def estop_handler(e_stop_active: bool, elapsed_ms: float, current_state: str) -> str:
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    if e_stop_active:
        return "SAFE_STOP"
    return current_state
