"""Shared TOTP helpers for tests. Steps are computed TZ-independently."""
import calendar
from datetime import datetime

import pyotp

# Naive UTC, the same shape as datetime.utcnow() in the app.
NOW = datetime(2026, 10, 12, 12, 0, 0)

# Fixed secret so codes are deterministic (steps NOW_STEP-2..+2 give 5 distinct codes).
SECRET = "JBSWY3DPEHPK3PXP"


def step_of(when: datetime) -> int:
    """TOTP time step for a naive-UTC datetime, regardless of the machine's TZ."""
    return calendar.timegm(when.utctimetuple()) // 30


NOW_STEP = step_of(NOW)  # 59726880


def code_for(secret: str, step: int) -> str:
    return pyotp.TOTP(secret).generate_otp(step)


def wrong_code(secret: str, step: int) -> str:
    """A well-formed 6-digit code that is not valid at step-1, step or step+1."""
    valid = {code_for(secret, s) for s in (step - 1, step, step + 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)
