"""TOTP two-factor authentication helpers. Pure functions: no I/O.

`now` is naive UTC (datetime.utcnow()) throughout the app.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import List, Optional

import pyotp

ISSUER = "NetWorth Tracker"
BACKUP_CODE_COUNT = 10
BACKUP_CODE_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _as_utc(now: datetime) -> datetime:
    # pyotp treats naive datetimes as *local* time; the app passes naive UTC.
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def normalize_code(code: str) -> str:
    return "".join(code.split()).replace("-", "").lower()


def verify_totp(secret: str, code: str, last_used_step: Optional[int], now: datetime) -> Optional[int]:
    """Return the matched time step (current ±1), or None. Steps <= last_used_step are replays."""
    code = normalize_code(code)
    # isascii() guard: hmac.compare_digest raises TypeError on non-ASCII str
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    current = totp.timecode(_as_utc(now))
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> List[str]:
    codes: List[str] = []
    while len(codes) < n:
        raw = "".join(secrets.choice(BACKUP_CODE_ALPHABET) for _ in range(8))
        code = f"{raw[:4]}-{raw[4:]}"
        if code not in codes:
            codes.append(code)
    return codes


def hash_backup_code(code: str) -> str:
    # Codes are random with 40 bits of entropy, so a fast hash is sufficient.
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def consume_backup_code(hashes: List[str], code: str) -> Optional[List[str]]:
    """Return hashes without the matching code, or None if it doesn't match."""
    candidate = hash_backup_code(code)
    for i, stored in enumerate(hashes):
        if hmac.compare_digest(stored, candidate):
            return hashes[:i] + hashes[i + 1:]
    return None
