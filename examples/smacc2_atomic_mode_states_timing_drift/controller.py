"""SMACC2 adapter-like timing constants for EAL validation.

This file intentionally drifts from spec/model timing (100 ms) to validate
code/spec/model mismatch detection in EAL.
"""

MODE_SWITCH_RESPONSE_MS = 150
MAX_MODE_REQUEST = 1


def on_mode_request(mode_request: int, elapsed_ms: int) -> bool:
    if mode_request > MAX_MODE_REQUEST:
        return False
    if elapsed_ms > MODE_SWITCH_RESPONSE_MS:
        return False
    return True
