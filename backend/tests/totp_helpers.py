"""Shared TOTP helpers for tests. Steps are computed TZ-independently."""
import calendar
from datetime import datetime

import pyotp

# Naive UTC, the same shape as datetime.utcnow() in the app.
NOW = datetime(2026, 10, 12, 12, 0, 0)

def step_of(when: datetime) -> int:
    """TOTP time step for a naive-UTC datetime, regardless of the machine's TZ."""
    return calendar.timegm(when.utctimetuple()) // 30


NOW_STEP = step_of(NOW)  # 59726880


def _random_secret() -> str:
    """A random base32 secret whose codes at steps NOW_STEP-2..+2 are 5 distinct values (the tests rely on that)."""
    while True:
        secret = pyotp.random_base32()
        if len({pyotp.TOTP(secret).generate_otp(NOW_STEP + offset) for offset in range(-2, 3)}) == 5:
            return secret


# Drawn at import so no secret is hardcoded in the repo; codes stay deterministic within a run.
SECRET = _random_secret()


def code_for(secret: str, step: int) -> str:
    return pyotp.TOTP(secret).generate_otp(step)


def wrong_code(secret: str, step: int) -> str:
    """A well-formed 6-digit code that is not valid at step-1, step or step+1."""
    valid = {code_for(secret, s) for s in (step - 1, step, step + 1)}
    return next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)
