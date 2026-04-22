"""
Boundary-clean controller.
Constants are intentionally set exactly at declared limits.
"""

MAX_CONVEYOR_SPEED = 1.0
LOOP_RESPONSE_MS = 50


def speed_guard(conveyor_speed: float, mode: str) -> bool:
    if mode == "NORMAL":
        return conveyor_speed <= MAX_CONVEYOR_SPEED
    return True


def stop_handler(elapsed_ms: float, current_state: str) -> str:
    assert elapsed_ms <= LOOP_RESPONSE_MS
    return "STOPPED" if current_state == "RUNNING" else current_state
