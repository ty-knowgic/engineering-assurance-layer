MAX_PRESSURE_BAR = 6.5
MAX_HEATER_POWER_KW = 25.0
ESTOP_RESPONSE_MS = 180


def pressure_guard(pressure_bar: float, mode: str) -> bool:
    if mode == "CALIBRATION" and pressure_bar > MAX_PRESSURE_BAR:
        return False
    return True


def heater_guard(heater_power_kw: float, mode: str) -> bool:
    if mode == "MAINTENANCE":
        return heater_power_kw <= MAX_HEATER_POWER_KW
    return True


def emergency_handler(elapsed_ms: float, e_stop_active: bool, state: str) -> str:
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    if e_stop_active:
        return "SAFE_STOP"
    return state

