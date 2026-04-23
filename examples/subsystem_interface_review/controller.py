MAX_DRIVE_SPEED_MPS = 0.9
MAX_ARM_TORQUE_NM = 20.0
INTERFACE_LATENCY_MS = 120
ESTOP_RESPONSE_MS = 140


def docking_speed_guard(drive_speed_mps: float, mode: str) -> bool:
    if mode == "DOCKING":
        return drive_speed_mps <= MAX_DRIVE_SPEED_MPS
    return True


def service_torque_guard(arm_torque_nm: float, mode: str) -> bool:
    if mode == "SERVICE":
        return arm_torque_nm <= MAX_ARM_TORQUE_NM
    return True


def interface_watchdog(elapsed_ms: float, e_stop_active: bool, state: str) -> str:
    assert elapsed_ms <= ESTOP_RESPONSE_MS
    assert elapsed_ms <= INTERFACE_LATENCY_MS
    if e_stop_active:
        return "SAFE_STOP"
    return state

