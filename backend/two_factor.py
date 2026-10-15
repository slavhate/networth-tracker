"""TOTP two-factor authentication helpers. Pure functions: no I/O.

`now` is naive UTC (UTC wall time without tzinfo) throughout the app.
"""
import hashlib
import hmac
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

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
    # Hashing only keeps backup codes out of casual view (e.g. a shared data.json). Anyone who can
    # read data.json already has the TOTP secret, so a slow hash would add nothing.
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def consume_backup_code(hashes: List[str], code: str) -> Optional[List[str]]:
    """Return hashes without the matching code, or None if it doesn't match."""
    candidate = hash_backup_code(code)
    for i, stored in enumerate(hashes):
        if hmac.compare_digest(stored, candidate):
            return hashes[:i] + hashes[i + 1:]
    return None


def is_locked(user: dict, now: datetime) -> bool:
    locked_until = user.get("totp_locked_until")
    if not locked_until:
        return False
    return datetime.fromisoformat(locked_until) > now


def lock_minutes_remaining(user: dict, now: datetime) -> int:
    remaining = datetime.fromisoformat(user["totp_locked_until"]) - now
    return max(1, math.ceil(remaining.total_seconds() / 60))


def record_failure(user: dict, now: datetime) -> Dict:
    """Updates for one failed attempt; the MAX_FAILED_ATTEMPTS-th failure starts a lockout."""
    attempts = (user.get("totp_failed_attempts") or 0) + 1
    if attempts >= MAX_FAILED_ATTEMPTS:
        locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        return {"totp_failed_attempts": 0, "totp_locked_until": locked_until.isoformat()}
    return {"totp_failed_attempts": attempts}


def verify_second_factor(user: dict, code: str, now: datetime) -> Tuple[bool, Dict]:
    """Check a TOTP (6 digits) or backup code (8 chars). Does not check the lock.

    Returns (ok, updates): the caller persists `updates` either way.
    """
    normalized = normalize_code(code)
    updates: Dict = {}
    if len(normalized) == 6:
        step = verify_totp(user["totp_secret"], normalized, user.get("totp_last_used_step"), now)
        if step is not None:
            updates["totp_last_used_step"] = step
    elif len(normalized) == 8:
        remaining = consume_backup_code(user.get("backup_code_hashes") or [], normalized)
        if remaining is not None:
            updates["backup_code_hashes"] = remaining
    if not updates:
        return False, record_failure(user, now)
    updates.update({"totp_failed_attempts": 0, "totp_locked_until": None})
    return True, updates

# Every 2FA field at its default; written to the user record when 2FA is disabled.
DISABLED_FIELDS = {
    "totp_enabled": False,
    "totp_secret": None,
    "totp_pending_secret": None,
    "totp_last_used_step": None,
    "backup_code_hashes": [],
    "totp_failed_attempts": 0,
    "totp_locked_until": None,
}
