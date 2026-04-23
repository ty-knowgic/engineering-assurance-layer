MAX_SPINDLE_SPEED_RPM = 360
ESTOP_RESPONSE_MS = 260
MIN_CLAMP_PRESSURE_BAR = 1.5


def setup_speed_guard(spindle_speed_rpm: float, mode: str) -> bool:
    if mode == "SETUP":
        return spindle_speed_rpm <= MAX_SPINDLE_SPEED_RPM
    return True


def interlock_pressure_guard(clamp_pressure_bar: float, spindle_speed_rpm: float) -> bool:
    if spindle_speed_rpm > 0:
        return clamp_pressure_bar >= MIN_CLAMP_PRESSURE_BAR
    return True


def stop_handler(e_stop_active: bool, elapsed_ms: float, state: str) -> str:
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    if e_stop_active:
        return "SAFE_STOP"
    return state

