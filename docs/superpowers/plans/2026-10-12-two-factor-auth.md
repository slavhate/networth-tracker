# Two-Factor Authentication (TOTP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users opt in to authenticator-app (TOTP) 2FA with one-time backup codes, enforced through a two-step login.

**Architecture:**
- **Backend:** a new pure module, `backend/two_factor.py`, holds all TOTP, backup-code and lockout logic. It does no I/O and takes the clock as a parameter.
  - `auth.py` gains a short-lived `mfa` challenge JWT.
  - `main.py` gains `/api/auth/login/2fa` and four `/api/auth/2fa/*` management endpoints.
  - 2FA state lives as optional fields on the user record in `data.json`.
- **Frontend:**
  - `Login.jsx` gains a second "code" step.
  - A new `Security.jsx` page handles enrollment (QR code), the backup codes, and disabling 2FA.

**Tech Stack:** FastAPI 0.115, python-jose JWT, `pyotp==2.9.0`, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3, `qrcode.react` ^4.2.0.

**Spec:** `docs/superpowers/specs/2026-10-12-two-factor-auth-design.md`. Read it before starting any task.

## Global Constraints

- Work on branch `feat/2fa-login`, in a checkout separate from any other in-progress work.
- Environment: Python 3.12 with a virtualenv that has `backend/requirements-dev.txt` installed (it pulls in `requirements.txt`, so `pyotp==2.9.0` and `pytest==8.3.4`), and Node 18+ for the frontend. All commands below run from the repository root in a POSIX shell (on Windows, use WSL).
- **Backend test command.** `TZ=Asia/Kolkata` is mandatory: pyotp treats naive datetimes as local time, and the tests only catch a missing UTC conversion off-UTC.
  ```bash
  cd backend && TZ=Asia/Kolkata python -m pytest tests -v
  ```
  To run one test, append `::test_name` to the file path, e.g. `tests/test_two_factor.py::test_x`.
- **New dependencies:** exactly `pyotp==2.9.0` (backend) and `qrcode.react` `^4.2.0` (frontend). Nothing else.
- **Clock:** "now" is **naive UTC** everywhere in app code (`datetime.utcnow()`), and `totp_locked_until` is stored as a naive ISO string. Only `two_factor._as_utc()` makes it aware, right before pyotp is called.
- **Error contract** (exact strings):
  - `/api/auth/login/2fa`:
    - 401 `"Invalid or expired login session"`
    - 401 `"Invalid authentication code"`
    - 429 `"Too many attempts. Try again in N minutes."`
  - Authenticated `/api/auth/2fa/*` endpoints never return 401 for a wrong password or code. They use 400 (`"Incorrect password"`, `"Invalid authentication code"`, `"Start setup first"`, `"Two-factor authentication is already enabled"`, `"Two-factor authentication is not enabled"`) and 429.
- **Constants:**
  - `MAX_FAILED_ATTEMPTS = 5`, `LOCKOUT_MINUTES = 15`
  - `BACKUP_CODE_COUNT = 10`, backup code format `xxxx-xxxx` from alphabet `abcdefghijklmnopqrstuvwxyz234567`
  - `ISSUER = "NetWorth Tracker"`, `MFA_TOKEN_EXPIRE_MINUTES = 5`
- **Commits:** every commit message ends with a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Style:** follow existing patterns. Backend uses module-level functions, `db.` helpers and `HTTPException`. Frontend uses Tailwind component classes `card`, `input`, `label`, `btn-primary`, `btn-secondary`, `btn-danger` with `dark:` variants on app pages.

## Review Focus

1. **Server timezone isn't UTC** (e.g. a Docker host with `TZ=Asia/Kolkata`). Codes from a phone must still verify. Covered by a step-pinned unit test run under `TZ=Asia/Kolkata` (Task 1).
2. **Odd characters in the code field:** Arabic-Indic digits, letters, a spaced `123 456`, a 65-char string. These must produce 401/422 or be accepted, never a 500. `hmac.compare_digest` raises on non-ASCII `str`. Covered in Task 1 (unit) and Task 4 (API).
3. **Mistyping the password while disabling 2FA must not sign the user out.** The global axios 401 handler would otherwise do that. Covered in Task 5 (400 + session still valid).
4. **Copy buttons on a self-hosted install served over plain `http://<LAN-IP>`.** `navigator.clipboard` is undefined there, and Copy must still work. Covered by the `copyText` fallback with a manual check (Task 7).
5. **Existing `data.json` users with none of the new fields** must log in unchanged and see "2FA off". Covered in Task 2 (unit), Task 4 (`test_login_without_2fa_is_unchanged`) and Task 5 (`test_status_is_disabled_for_existing_users`).

## Local Run (used by Tasks 6–7 for manual verification)

Run the backend and frontend in two terminals. `SECRET_KEY` here is a throwaway dev value; never reuse it.

```bash
mkdir -p /tmp/nwt-2fa && cd backend && DATA_FILE=/tmp/nwt-2fa/data.json SECRET_KEY="$(openssl rand -hex 32)" uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

The frontend is at `http://localhost:3000`. Vite proxies `/api` to `:8000`.

---

### Task 1: TOTP and backup-code primitives + test scaffolding

**Files:**
- Modify: `backend/requirements.txt` (append `pyotp==2.9.0`)
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/totp_helpers.py`
- Create: `backend/two_factor.py`
- Test: `backend/tests/test_two_factor.py`

**Interfaces:**
- Consumes: nothing.
- Produces (in `two_factor`):
  - constants: `ISSUER`, `BACKUP_CODE_COUNT`, `BACKUP_CODE_ALPHABET`, `MAX_FAILED_ATTEMPTS`, `LOCKOUT_MINUTES`
  - `generate_secret() -> str`
  - `provisioning_uri(secret: str, username: str) -> str`
  - `normalize_code(code: str) -> str`
  - `verify_totp(secret: str, code: str, last_used_step: Optional[int], now: datetime) -> Optional[int]`
  - `generate_backup_codes(n: int = BACKUP_CODE_COUNT) -> List[str]`
  - `hash_backup_code(code: str) -> str`
  - `consume_backup_code(hashes: List[str], code: str) -> Optional[List[str]]`
- Produces (in tests):
  - fixtures `client`, `auth_headers` (`tests/conftest.py`)
  - helpers `NOW`, `NOW_STEP`, `SECRET`, `step_of(when) -> int`, `code_for(secret, step) -> str`, `wrong_code(secret, step) -> str` (`tests/totp_helpers.py`)

- [ ] **Step 1: Add dependencies and test scaffolding**

Append to `backend/requirements.txt` (new last line):

```
pyotp==2.9.0
```

Create `backend/requirements-dev.txt`:

```
-r requirements.txt
pytest==8.3.4
```

Create `backend/tests/conftest.py`. The `client` and `auth_headers` shapes are identical to the `feat/zerodha-mf-import` branch on purpose.

```python
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by a throwaway data file."""
    from fastapi.testclient import TestClient
    from config import settings
    import main

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))
    return TestClient(main.app)


@pytest.fixture
def auth_headers(client):
    client.post("/api/auth/register", json={"username": "tester", "password": PASSWORD, "email": "t@example.com"})
    resp = client.post("/api/auth/login", data={"username": "tester", "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
```

Create `backend/tests/totp_helpers.py`:

```python
"""Shared TOTP helpers for tests. Steps are computed TZ-independently."""
import calendar
from datetime import datetime

import pyotp

# Naive UTC, the same shape as datetime.utcnow() in the app.
NOW = datetime(2026, 10, 12, 12, 0, 0)

# Fixed secret so codes are deterministic (steps NOW_STEP-2..+2 give 5 distinct codes).
SECRET = pyotp.random_base32()


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
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_two_factor.py`:

```python
import re
from datetime import timezone

import two_factor as tf
from totp_helpers import NOW, NOW_STEP, SECRET, code_for


def test_verify_totp_returns_current_step_for_naive_utc_now():
    # Pins the absolute step: fails under TZ=Asia/Kolkata if naive `now` reaches pyotp unconverted.
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), None, NOW) == NOW_STEP


def test_verify_totp_treats_aware_and_naive_utc_the_same():
    aware = NOW.replace(tzinfo=timezone.utc)
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), None, aware) == NOW_STEP


def test_verify_totp_accepts_one_step_of_clock_drift():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 1), None, NOW) == NOW_STEP - 1
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 1), None, NOW) == NOW_STEP + 1


def test_verify_totp_rejects_two_steps_of_drift():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 2), None, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 2), None, NOW) is None


def test_verify_totp_rejects_replayed_or_older_steps():
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP), NOW_STEP, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP - 1), NOW_STEP, NOW) is None
    assert tf.verify_totp(SECRET, code_for(SECRET, NOW_STEP + 1), NOW_STEP, NOW) == NOW_STEP + 1


def test_verify_totp_ignores_spaces_and_dashes():
    code = code_for(SECRET, NOW_STEP)
    assert tf.verify_totp(SECRET, f" {code[:3]} {code[3:]} ", None, NOW) == NOW_STEP
    assert tf.verify_totp(SECRET, f"{code[:3]}-{code[3:]}", None, NOW) == NOW_STEP


def test_verify_totp_rejects_malformed_codes_without_raising():
    for bad in ["", "12345", "1234567", "abcdef", "١٢٣٤٥٦", "12 34 5"]:
        assert tf.verify_totp(SECRET, bad, None, NOW) is None


def test_provisioning_uri_names_issuer_user_and_secret():
    uri = tf.provisioning_uri(SECRET, "alice")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=NetWorth%20Tracker" in uri
    assert "alice" in uri
    assert f"secret={SECRET}" in uri


def test_generate_secret_is_base32_and_unique():
    a, b = tf.generate_secret(), tf.generate_secret()
    assert re.fullmatch(r"[A-Z2-7]{32}", a)
    assert a != b


def test_generate_backup_codes_format_and_uniqueness():
    codes = tf.generate_backup_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for code in codes:
        assert re.fullmatch(r"[a-z2-7]{4}-[a-z2-7]{4}", code)


def test_hash_backup_code_ignores_case_dashes_and_spaces():
    expected = tf.hash_backup_code("abcd-efgh")
    assert tf.hash_backup_code("ABCDEFGH") == expected
    assert tf.hash_backup_code(" abcd efgh ") == expected


def test_consume_backup_code_removes_only_the_used_code():
    codes = tf.generate_backup_codes()
    hashes = [tf.hash_backup_code(c) for c in codes]
    remaining = tf.consume_backup_code(hashes, codes[3].upper().replace("-", ""))
    assert remaining == hashes[:3] + hashes[4:]
    assert tf.consume_backup_code(remaining, codes[3]) is None


def test_consume_backup_code_rejects_unknown_code():
    hashes = [tf.hash_backup_code(c) for c in tf.generate_backup_codes()]
    assert tf.consume_backup_code(hashes, "zzzz-zzzz") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run the backend test command from Global Constraints with `tests/test_two_factor.py`.
Expected: collection error `ModuleNotFoundError: No module named 'two_factor'`.

- [ ] **Step 4: Write the implementation**

Create `backend/two_factor.py`:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run the backend test command with `tests/test_two_factor.py`.
Expected: 13 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/tests/conftest.py backend/tests/totp_helpers.py backend/two_factor.py backend/tests/test_two_factor.py
git commit -m "feat: add TOTP and backup code primitives for 2FA" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Second-factor verification and lockout

**Files:**
- Modify: `backend/two_factor.py` (append)
- Test: `backend/tests/test_two_factor.py` (append)

**Interfaces:**
- Consumes (Task 1): `verify_totp`, `consume_backup_code`, `normalize_code`, `MAX_FAILED_ATTEMPTS`, `LOCKOUT_MINUTES`.
- Produces (in `two_factor`):
  - `is_locked(user: dict, now: datetime) -> bool`
  - `lock_minutes_remaining(user: dict, now: datetime) -> int`
  - `record_failure(user: dict, now: datetime) -> Dict`
  - `verify_second_factor(user: dict, code: str, now: datetime) -> Tuple[bool, Dict]`
  - Returned dicts are user-field updates for the caller to persist.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_two_factor.py`. Add `from datetime import timedelta` to the imports at the top, and change the `totp_helpers` import to `from totp_helpers import NOW, NOW_STEP, SECRET, code_for, wrong_code`.

```python
def enabled_user(**overrides):
    user = {
        "id": "u1",
        "totp_enabled": True,
        "totp_secret": SECRET,
        "totp_last_used_step": None,
        "backup_code_hashes": [tf.hash_backup_code("abcd-efgh"), tf.hash_backup_code("ijkl-mnop")],
        "totp_failed_attempts": 0,
        "totp_locked_until": None,
    }
    user.update(overrides)
    return user


def test_second_factor_totp_success_records_step_and_resets_failures():
    ok, updates = tf.verify_second_factor(enabled_user(totp_failed_attempts=3), code_for(SECRET, NOW_STEP), NOW)
    assert ok is True
    assert updates == {"totp_last_used_step": NOW_STEP, "totp_failed_attempts": 0, "totp_locked_until": None}


def test_second_factor_backup_code_success_consumes_it():
    ok, updates = tf.verify_second_factor(enabled_user(), "IJKL-MNOP", NOW)
    assert ok is True
    assert updates == {
        "backup_code_hashes": [tf.hash_backup_code("abcd-efgh")],
        "totp_failed_attempts": 0,
        "totp_locked_until": None,
    }


def test_second_factor_wrong_code_counts_a_failure():
    ok, updates = tf.verify_second_factor(enabled_user(totp_failed_attempts=1), wrong_code(SECRET, NOW_STEP), NOW)
    assert ok is False
    assert updates == {"totp_failed_attempts": 2}


def test_second_factor_malformed_code_counts_a_failure():
    ok, updates = tf.verify_second_factor(enabled_user(), "12345", NOW)
    assert ok is False
    assert updates == {"totp_failed_attempts": 1}


def test_fifth_failure_locks_for_fifteen_minutes():
    ok, updates = tf.verify_second_factor(enabled_user(totp_failed_attempts=4), wrong_code(SECRET, NOW_STEP), NOW)
    assert ok is False
    assert updates == {
        "totp_failed_attempts": 0,
        "totp_locked_until": (NOW + timedelta(minutes=15)).isoformat(),
    }


def test_record_failure_uses_the_same_counter():
    assert tf.record_failure(enabled_user(totp_failed_attempts=2), NOW) == {"totp_failed_attempts": 3}


def test_is_locked_only_before_locked_until():
    until = (NOW + timedelta(minutes=15)).isoformat()
    assert tf.is_locked(enabled_user(), NOW) is False
    assert tf.is_locked(enabled_user(totp_locked_until=until), NOW) is True
    assert tf.is_locked(enabled_user(totp_locked_until=until), NOW + timedelta(minutes=15)) is False


def test_lock_minutes_remaining_rounds_up():
    until = (NOW + timedelta(minutes=10, seconds=30)).isoformat()
    assert tf.lock_minutes_remaining(enabled_user(totp_locked_until=until), NOW) == 11


def test_missing_fields_behave_like_defaults():
    legacy = {"id": "u1", "totp_secret": SECRET}  # records written before 2FA lack the counters
    assert tf.is_locked(legacy, NOW) is False
    assert tf.verify_second_factor(legacy, wrong_code(SECRET, NOW_STEP), NOW) == (False, {"totp_failed_attempts": 1})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run the backend test command with `tests/test_two_factor.py`.
Expected: the 9 new tests FAIL with `AttributeError: module 'two_factor' has no attribute ...`, and the 13 Task 1 tests pass.

- [ ] **Step 3: Write the implementation**

In `backend/two_factor.py`:
- change the imports to `import math`, `from datetime import datetime, timedelta, timezone` and `from typing import Dict, List, Optional, Tuple`
- append:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run the backend test command with `tests/test_two_factor.py`.
Expected: 22 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/two_factor.py backend/tests/test_two_factor.py
git commit -m "feat: add second-factor verification with lockout" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: MFA challenge token and `update_user`

**Files:**
- Modify: `backend/config.py` (`Settings`, after `ACCESS_TOKEN_EXPIRE_MINUTES`)
- Modify: `backend/auth.py` (`decode_token`; new functions after it)
- Modify: `backend/database.py` (new function after `create_user`)
- Test: `backend/tests/test_auth_tokens.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `settings.MFA_TOKEN_EXPIRE_MINUTES: int = 5`
  - `auth.create_mfa_token(username: str, user_id: str) -> str`
  - `auth.decode_mfa_token(token: str) -> Optional[dict]`, which returns the payload with `sub`, `user_id`, `type == "mfa"`
  - `auth.decode_token` now returns `None` for mfa tokens
  - `db.update_user(user_id: str, updates: Dict) -> Optional[Dict]`, which applies every key including `None`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_tokens.py`:

```python
import pytest

import auth
import database as db
from config import settings


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


def test_mfa_token_round_trips_through_decode_mfa_token():
    payload = auth.decode_mfa_token(auth.create_mfa_token("alice", "u1"))
    assert payload["sub"] == "alice"
    assert payload["user_id"] == "u1"
    assert payload["type"] == "mfa"


def test_mfa_token_is_not_an_access_token():
    assert auth.decode_token(auth.create_mfa_token("alice", "u1")) is None


def test_access_token_is_not_an_mfa_token():
    access = auth.create_access_token({"sub": "alice", "user_id": "u1"})
    assert auth.decode_mfa_token(access) is None
    assert auth.decode_token(access) == "alice"  # tokens issued before 2FA have no "type" claim


def test_expired_mfa_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MFA_TOKEN_EXPIRE_MINUTES", -1)
    assert auth.decode_mfa_token(auth.create_mfa_token("alice", "u1")) is None


def test_decode_mfa_token_rejects_garbage():
    assert auth.decode_mfa_token("not-a-jwt") is None


def test_update_user_sets_and_clears_fields(data_file):
    user = db.create_user("alice", "a@example.com", "hash")
    db.update_user(user["id"], {"totp_secret": "ABC", "totp_enabled": True})
    assert db.get_user_by_id(user["id"])["totp_secret"] == "ABC"

    updated = db.update_user(user["id"], {"totp_secret": None})
    assert updated["totp_secret"] is None
    stored = db.get_user_by_id(user["id"])
    assert stored["totp_secret"] is None
    assert stored["totp_enabled"] is True


def test_update_user_unknown_id_returns_none(data_file):
    assert db.update_user("missing", {"totp_enabled": True}) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run the backend test command with `tests/test_auth_tokens.py`.
Expected: FAIL with `AttributeError: module 'auth' has no attribute 'create_mfa_token'` (and `'database' has no attribute 'update_user'`). `test_access_token_is_not_an_mfa_token` fails too.

- [ ] **Step 3: Write the implementation**

In `backend/config.py`, below `ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours`, add:

```python
    MFA_TOKEN_EXPIRE_MINUTES: int = 5  # 2FA login challenge lifetime
```

In `backend/auth.py`, replace `decode_token` with the version below and add the two new functions after it:

```python
def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") == "mfa":
            return None  # a 2FA challenge token is not an access token
        username: str = payload.get("sub")
        if username is None:
            return None
        return username
    except JWTError:
        return None

def create_mfa_token(username: str, user_id: str) -> str:
    """Short-lived token proving the password step of a 2FA login succeeded."""
    return create_access_token(
        data={"sub": username, "user_id": user_id, "type": "mfa"},
        expires_delta=timedelta(minutes=settings.MFA_TOKEN_EXPIRE_MINUTES)
    )

def decode_mfa_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "mfa" or not payload.get("sub") or not payload.get("user_id"):
        return None
    return payload
```

In `backend/database.py`, directly after `create_user`, add:

```python
def update_user(user_id: str, updates: Dict) -> Optional[Dict]:
    """Apply every key in updates, including None (used to clear 2FA fields)."""
    data = load_data()
    for i, user in enumerate(data["users"]):
        if user["id"] == user_id:
            data["users"][i].update(updates)
            save_data(data)
            return data["users"][i]
    return None
```

- [ ] **Step 4: Run all backend tests to verify they pass**

Run the backend test command with `tests`.
Expected: 29 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/auth.py backend/database.py backend/tests/test_auth_tokens.py
git commit -m "feat: add 2FA challenge token and user update helper" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Two-step login endpoints

**Files:**
- Modify: `backend/models.py` (`Token`; new `MfaLoginRequest` after `TokenData`)
- Modify: `backend/main.py` (imports at lines 1–28; `login` at lines 67–83; new helpers + endpoint)
- Modify: `backend/tests/conftest.py` (add `clock` fixture)
- Test: `backend/tests/test_two_factor_login.py`

**Interfaces:**
- Consumes:
  - Task 2: `two_factor.is_locked`, `lock_minutes_remaining`, `verify_second_factor`
  - Task 3: `auth.create_mfa_token`, `auth.decode_mfa_token`, `db.update_user`
  - Task 1: `two_factor.generate_secret`, `generate_backup_codes`, `hash_backup_code` (tests only)
- Produces:
  - `main._now() -> datetime` (naive UTC; tests monkeypatch it)
  - `main._access_token_for(user: dict) -> Token`
  - `main._too_many_attempts(user: dict, now: datetime) -> HTTPException`
  - endpoint `POST /api/auth/login/2fa`
  - `models.Token` with optional `access_token`, `mfa_required: bool = False`, `mfa_token: Optional[str]`
  - `models.MfaLoginRequest`
  - pytest fixture `clock` (dict with key `"now"`)

- [ ] **Step 1: Add the `clock` fixture**

Append to `backend/tests/conftest.py`:

```python
@pytest.fixture
def clock(monkeypatch):
    """Freeze main._now(); move time by assigning clock["now"]."""
    import main
    from totp_helpers import NOW

    state = {"now": NOW}
    monkeypatch.setattr(main, "_now", lambda: state["now"])
    return state
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_two_factor_login.py`:

```python
from datetime import timedelta

import pytest

import database as db
import two_factor as tf
from config import settings
from totp_helpers import NOW, NOW_STEP, code_for, step_of, wrong_code

PASSWORD = secrets.token_urlsafe(16)


@pytest.fixture
def mfa_user(client):
    """Registered user 'alice' with 2FA switched on directly in the data file."""
    client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "email": "a@example.com"})
    user = db.get_user_by_username("alice")
    secret = tf.generate_secret()
    codes = tf.generate_backup_codes()
    db.update_user(user["id"], {
        "totp_enabled": True,
        "totp_secret": secret,
        "backup_code_hashes": [tf.hash_backup_code(c) for c in codes],
    })
    return {"secret": secret, "codes": codes}


def start_login(client):
    resp = client.post("/api/auth/login", data={"username": "alice", "password": PASSWORD})
    assert resp.status_code == 200
    return resp.json()["mfa_token"]


def finish_login(client, mfa_token, code):
    return client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": code})


def test_login_without_2fa_is_unchanged(client):
    client.post("/api/auth/register", json={"username": "bob", "password": PASSWORD, "email": "b@example.com"})
    resp = client.post("/api/auth/login", data={"username": "bob", "password": PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "token_type", "mfa_required"}
    assert body["token_type"] == "bearer"
    assert body["mfa_required"] is False
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_wrong_password_is_still_401(client, mfa_user):
    resp = client.post("/api/auth/login", data={"username": "alice", "password": WRONG_PASSWORD})
    assert resp.status_code == 401


def test_login_with_2fa_returns_challenge_instead_of_access_token(client, mfa_user):
    body = client.post("/api/auth/login", data={"username": "alice", "password": PASSWORD}).json()
    assert body["mfa_required"] is True
    assert body["token_type"] == "mfa"
    assert body["mfa_token"]
    assert "access_token" not in body


def test_mfa_token_cannot_call_the_api(client, mfa_user):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {start_login(client)}"})
    assert resp.status_code == 401


def test_totp_code_completes_login(client, mfa_user, clock):
    resp = finish_login(client, start_login(client), code_for(mfa_user["secret"], NOW_STEP))
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["username"] == "alice"


def test_totp_code_cannot_be_replayed(client, mfa_user, clock):
    code = code_for(mfa_user["secret"], NOW_STEP)
    assert finish_login(client, start_login(client), code).status_code == 200
    resp = finish_login(client, start_login(client), code)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid authentication code"


def test_backup_code_works_once(client, mfa_user, clock):
    code = mfa_user["codes"][0].upper()
    assert finish_login(client, start_login(client), code).status_code == 200
    assert finish_login(client, start_login(client), code).status_code == 401
    assert len(db.get_user_by_username("alice")["backup_code_hashes"]) == 9


def test_wrong_code_is_401(client, mfa_user, clock):
    resp = finish_login(client, start_login(client), wrong_code(mfa_user["secret"], NOW_STEP))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid authentication code"


@pytest.mark.parametrize("code", ["١٢٣٤٥٦", "12345", "not a code"])
def test_malformed_code_is_401_not_500(client, mfa_user, clock, code):
    assert finish_login(client, start_login(client), code).status_code == 401


def test_oversized_code_is_rejected_by_validation(client, mfa_user, clock):
    assert finish_login(client, start_login(client), "1" * 65).status_code == 422


def test_expired_mfa_token_is_401(client, mfa_user, clock, monkeypatch):
    monkeypatch.setattr(settings, "MFA_TOKEN_EXPIRE_MINUTES", -1)
    resp = finish_login(client, start_login(client), code_for(mfa_user["secret"], NOW_STEP))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"


def test_garbage_mfa_token_is_401(client, mfa_user, clock):
    resp = finish_login(client, "garbage", code_for(mfa_user["secret"], NOW_STEP))
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"


def test_lockout_after_five_failures_then_recovers(client, mfa_user, clock):
    secret = mfa_user["secret"]
    mfa_token = start_login(client)
    for _ in range(5):
        assert finish_login(client, mfa_token, wrong_code(secret, NOW_STEP)).status_code == 401

    locked = finish_login(client, mfa_token, code_for(secret, NOW_STEP))
    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many attempts. Try again in 15 minutes."

    clock["now"] = NOW + timedelta(minutes=15)
    resp = finish_login(client, start_login(client), code_for(secret, step_of(clock["now"])))
    assert resp.status_code == 200
```

- [ ] **Step 3: Run the tests to verify they fail**

Run the backend test command with `tests/test_two_factor_login.py`.
Expected:
- Collection/fixture errors `AttributeError: <module 'main'> has no attribute '_now'` for tests using `clock`.
- `test_login_without_2fa_is_unchanged` FAILS (no `mfa_required` key).
- `test_login_with_2fa_returns_challenge...` FAILS.

- [ ] **Step 4: Update the models**

In `backend/models.py`, replace `class Token`:

```python
class Token(BaseModel):
    access_token: Optional[str] = None
    token_type: str
    mfa_required: bool = False
    mfa_token: Optional[str] = None
```

After `class TokenData`, add:

```python
class MfaLoginRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., max_length=64)
```

- [ ] **Step 5: Update `main.py` imports**

In `backend/main.py`:
- change `from datetime import timedelta` to `from datetime import datetime, timedelta`
- change the models import first line from `UserCreate, User, Token,` to `UserCreate, User, Token, MfaLoginRequest,`
- change the auth import to:

```python
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, create_mfa_token, decode_mfa_token
)
```

- after `import database as db`, add `import two_factor`

- [ ] **Step 6: Replace the login endpoint and add the 2FA step**

In `backend/main.py`, replace the whole `@app.post("/api/auth/login", ...)` function (from its decorator through `return Token(access_token=access_token, token_type="bearer")`) with:

```python
def _now() -> datetime:
    """Naive UTC; patched in tests."""
    return datetime.utcnow()

def _access_token_for(user: dict) -> Token:
    access_token = create_access_token(
        data={"sub": user["username"], "user_id": user["id"]},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return Token(access_token=access_token, token_type="bearer")

def _too_many_attempts(user: dict, now: datetime) -> HTTPException:
    minutes = two_factor.lock_minutes_remaining(user, now)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many attempts. Try again in {minutes} minutes."
    )

@app.post("/api/auth/login", response_model=Token, response_model_exclude_none=True)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login and get an access token, or a 2FA challenge token if 2FA is enabled"""
    user = db.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.get("totp_enabled"):
        return Token(
            token_type="mfa",
            mfa_required=True,
            mfa_token=create_mfa_token(user["username"], user["id"])
        )

    return _access_token_for(user)

@app.post("/api/auth/login/2fa", response_model=Token, response_model_exclude_none=True)
async def login_2fa(request: MfaLoginRequest):
    """Complete a 2FA login with an authenticator or backup code"""
    payload = decode_mfa_token(request.mfa_token)
    user = db.get_user_by_id(payload["user_id"]) if payload else None
    if not user or not user.get("totp_enabled"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired login session"
        )

    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)

    ok, updates = two_factor.verify_second_factor(user, request.code, now)
    db.update_user(user["id"], updates)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication code"
        )

    return _access_token_for(user)
```

- [ ] **Step 7: Run all backend tests to verify they pass**

Run the backend test command with `tests`.
Expected: 44 passed (29 earlier + 15 new; the parametrized test counts 3).

- [ ] **Step 8: Commit**

```bash
git add backend/models.py backend/main.py backend/tests/conftest.py backend/tests/test_two_factor_login.py
git commit -m "feat: require a second factor at login when 2FA is enabled" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 2FA management endpoints + API docs

**Files:**
- Modify: `backend/two_factor.py` (append `DISABLED_FIELDS`)
- Modify: `backend/models.py` (append after `MfaLoginRequest`)
- Modify: `backend/main.py` (models import; new section after `get_me`, before `# ============== Asset Routes ==============`)
- Modify: `README.md` (Authentication API table, around line 307)
- Test: `backend/tests/test_two_factor_manage.py`

**Interfaces:**
- Consumes:
  - Task 4: `main._now`, `main._too_many_attempts`, fixture `clock`
  - Task 2: `two_factor.is_locked`, `record_failure`, `verify_second_factor`
  - Task 1: `generate_secret`, `provisioning_uri`, `verify_totp`, `generate_backup_codes`, `hash_backup_code`
  - Task 3: `db.update_user`
- Produces:
  - `two_factor.DISABLED_FIELDS: Dict`
  - models `TwoFactorCode`, `TwoFactorDisable`, `TwoFactorStatus`, `TwoFactorSetup`, `TwoFactorBackupCodes`
  - endpoints (the frontend relies on these exact paths and shapes):
    - `GET /api/auth/2fa/status` → `{enabled, backup_codes_remaining}`
    - `POST /api/auth/2fa/setup` → `{secret, otpauth_uri}`
    - `POST /api/auth/2fa/enable {code}` → `{backup_codes}`
    - `POST /api/auth/2fa/disable {password, code}` → 204

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_two_factor_manage.py`:

```python
import database as db
import two_factor as tf
from totp_helpers import NOW_STEP, code_for, wrong_code

PASSWORD = secrets.token_urlsafe(16)  # password of the auth_headers fixture's user "tester"


def enable_2fa(client, headers):
    """Run setup + enable at NOW_STEP. Later TOTP logins must use NOW_STEP + 1 (replay protection)."""
    setup = client.post("/api/auth/2fa/setup", headers=headers).json()
    resp = client.post("/api/auth/2fa/enable", headers=headers, json={"code": code_for(setup["secret"], NOW_STEP)})
    assert resp.status_code == 200
    return setup["secret"], resp.json()["backup_codes"]


def password_login(client):
    return client.post("/api/auth/login", data={"username": "tester", "password": PASSWORD}).json()


def disable(client, headers, password, code):
    return client.post("/api/auth/2fa/disable", headers=headers, json={"password": password, "code": code})


def test_status_requires_login(client):
    assert client.get("/api/auth/2fa/status").status_code == 401


def test_status_is_disabled_for_existing_users(client, auth_headers):
    resp = client.get("/api/auth/2fa/status", headers=auth_headers)
    assert resp.json() == {"enabled": False, "backup_codes_remaining": 0}


def test_setup_issues_pending_secret_without_enabling(client, auth_headers):
    resp = client.post("/api/auth/2fa/setup", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["otpauth_uri"] == tf.provisioning_uri(body["secret"], "tester")
    user = db.get_user_by_username("tester")
    assert user["totp_pending_secret"] == body["secret"]
    assert not user.get("totp_enabled")
    assert "access_token" in password_login(client)


def test_setup_again_replaces_pending_secret(client, auth_headers):
    first = client.post("/api/auth/2fa/setup", headers=auth_headers).json()["secret"]
    second = client.post("/api/auth/2fa/setup", headers=auth_headers).json()["secret"]
    assert first != second
    assert db.get_user_by_username("tester")["totp_pending_secret"] == second


def test_enable_requires_setup_first(client, auth_headers, clock):
    resp = client.post("/api/auth/2fa/enable", headers=auth_headers, json={"code": "123456"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Start setup first"


def test_enable_with_wrong_code_is_400_and_stays_disabled(client, auth_headers, clock):
    secret = client.post("/api/auth/2fa/setup", headers=auth_headers).json()["secret"]
    resp = client.post("/api/auth/2fa/enable", headers=auth_headers, json={"code": wrong_code(secret, NOW_STEP)})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid authentication code"
    assert client.get("/api/auth/2fa/status", headers=auth_headers).json()["enabled"] is False


def test_enable_returns_backup_codes_and_turns_on_2fa(client, auth_headers, clock):
    secret, codes = enable_2fa(client, auth_headers)
    assert len(codes) == 10
    status = client.get("/api/auth/2fa/status", headers=auth_headers).json()
    assert status == {"enabled": True, "backup_codes_remaining": 10}
    user = db.get_user_by_username("tester")
    assert user["totp_secret"] == secret
    assert user["totp_pending_secret"] is None
    assert codes[0] not in str(user)  # only hashes are stored
    assert password_login(client)["mfa_required"] is True


def test_enrollment_code_cannot_be_reused_to_log_in(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    mfa_token = password_login(client)["mfa_token"]
    resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": code_for(secret, NOW_STEP)})
    assert resp.status_code == 401


def test_backup_code_login_lowers_remaining_count(client, auth_headers, clock):
    _, codes = enable_2fa(client, auth_headers)
    mfa_token = password_login(client)["mfa_token"]
    assert client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": codes[0]}).status_code == 200
    assert client.get("/api/auth/2fa/status", headers=auth_headers).json()["backup_codes_remaining"] == 9


def test_setup_and_enable_refused_while_enabled(client, auth_headers, clock):
    enable_2fa(client, auth_headers)
    setup = client.post("/api/auth/2fa/setup", headers=auth_headers)
    assert setup.status_code == 400
    assert setup.json()["detail"] == "Two-factor authentication is already enabled"
    assert client.post("/api/auth/2fa/enable", headers=auth_headers, json={"code": "123456"}).status_code == 400


def test_disable_when_not_enabled_is_400(client, auth_headers, clock):
    resp = disable(client, auth_headers, PASSWORD, "123456")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Two-factor authentication is not enabled"


def test_disable_wrong_password_is_400_and_keeps_session(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    resp = disable(client, auth_headers, WRONG_PASSWORD, code_for(secret, NOW_STEP + 1))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Incorrect password"
    # 400, not 401: the frontend logs the user out on any 401 from a non-login endpoint
    assert client.get("/api/auth/2fa/status", headers=auth_headers).json()["enabled"] is True


def test_disable_wrong_code_is_400(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    resp = disable(client, auth_headers, PASSWORD, wrong_code(secret, NOW_STEP + 1))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid authentication code"


def test_disable_clears_everything_and_restores_plain_login(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    assert disable(client, auth_headers, PASSWORD, code_for(secret, NOW_STEP + 1)).status_code == 204
    user = db.get_user_by_username("tester")
    for field, default in tf.DISABLED_FIELDS.items():
        assert user[field] == default
    status = client.get("/api/auth/2fa/status", headers=auth_headers).json()
    assert status == {"enabled": False, "backup_codes_remaining": 0}
    assert "access_token" in password_login(client)


def test_disable_with_backup_code(client, auth_headers, clock):
    _, codes = enable_2fa(client, auth_headers)
    assert disable(client, auth_headers, PASSWORD, codes[5]).status_code == 204


def test_disable_locks_after_five_wrong_passwords(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    for _ in range(5):
        assert disable(client, auth_headers, WRONG_PASSWORD, "123456").status_code == 400
    assert disable(client, auth_headers, PASSWORD, code_for(secret, NOW_STEP + 1)).status_code == 429
```

- [ ] **Step 2: Run the tests to verify they fail**

Run the backend test command with `tests/test_two_factor_manage.py`.
Expected: FAIL with 404s on `/api/auth/2fa/*` (e.g. `test_status_is_disabled_for_existing_users` gets `{"detail": "Not Found"}`).

- [ ] **Step 3: Add `DISABLED_FIELDS` and the models**

Append to `backend/two_factor.py`:

```python
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
```

In `backend/models.py`, after `MfaLoginRequest`, add:

```python
class TwoFactorCode(BaseModel):
    code: str = Field(..., max_length=64)

class TwoFactorDisable(BaseModel):
    password: str
    code: str = Field(..., max_length=64)

class TwoFactorStatus(BaseModel):
    enabled: bool
    backup_codes_remaining: int

class TwoFactorSetup(BaseModel):
    secret: str
    otpauth_uri: str

class TwoFactorBackupCodes(BaseModel):
    backup_codes: List[str]
```

- [ ] **Step 4: Add the endpoints**

In `backend/main.py`, extend the models import's first line to:

```python
    UserCreate, User, Token, MfaLoginRequest,
    TwoFactorCode, TwoFactorDisable, TwoFactorStatus, TwoFactorSetup, TwoFactorBackupCodes,
```

Then insert this block after the `get_me` function and before `# ============== Asset Routes ==============`:

```python
# ============== Two-Factor Auth Routes ==============
# Wrong passwords/codes here return 400, not 401: the frontend treats a 401 as an expired session.

def get_current_user_record(username: str = Depends(get_current_user)) -> dict:
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/api/auth/2fa/status", response_model=TwoFactorStatus)
async def two_factor_status(user: dict = Depends(get_current_user_record)):
    """Whether 2FA is enabled and how many backup codes remain"""
    return TwoFactorStatus(
        enabled=bool(user.get("totp_enabled")),
        backup_codes_remaining=len(user.get("backup_code_hashes") or [])
    )

@app.post("/api/auth/2fa/setup", response_model=TwoFactorSetup)
async def two_factor_setup(user: dict = Depends(get_current_user_record)):
    """Start enrollment: issue a pending secret for the authenticator app"""
    if user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled")
    secret = two_factor.generate_secret()
    db.update_user(user["id"], {"totp_pending_secret": secret})
    return TwoFactorSetup(secret=secret, otpauth_uri=two_factor.provisioning_uri(secret, user["username"]))

@app.post("/api/auth/2fa/enable", response_model=TwoFactorBackupCodes)
async def two_factor_enable(request: TwoFactorCode, user: dict = Depends(get_current_user_record)):
    """Confirm enrollment with a code; returns backup codes (shown only this once)"""
    if user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is already enabled")
    pending = user.get("totp_pending_secret")
    if not pending:
        raise HTTPException(status_code=400, detail="Start setup first")
    step = two_factor.verify_totp(pending, request.code, None, _now())
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid authentication code")

    codes = two_factor.generate_backup_codes()
    db.update_user(user["id"], {
        **two_factor.DISABLED_FIELDS,
        "totp_enabled": True,
        "totp_secret": pending,
        "totp_last_used_step": step,
        "backup_code_hashes": [two_factor.hash_backup_code(c) for c in codes],
    })
    return TwoFactorBackupCodes(backup_codes=codes)

@app.post("/api/auth/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def two_factor_disable(request: TwoFactorDisable, user: dict = Depends(get_current_user_record)):
    """Turn off 2FA; requires the password and a current authenticator or backup code"""
    if not user.get("totp_enabled"):
        raise HTTPException(status_code=400, detail="Two-factor authentication is not enabled")
    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)
    if not verify_password(request.password, user["hashed_password"]):
        db.update_user(user["id"], two_factor.record_failure(user, now))
        raise HTTPException(status_code=400, detail="Incorrect password")

    ok, updates = two_factor.verify_second_factor(user, request.code, now)
    if not ok:
        db.update_user(user["id"], updates)
        raise HTTPException(status_code=400, detail="Invalid authentication code")

    db.update_user(user["id"], two_factor.DISABLED_FIELDS)
```

Note: `**two_factor.DISABLED_FIELDS` in enable resets the lockout counters and clears `totp_pending_secret`; the keys after it override the rest.

- [ ] **Step 5: Run all backend tests to verify they pass**

Run the backend test command with `tests`.
Expected: 60 passed.

- [ ] **Step 6: Update the README API table**

In `README.md`, replace the `### Authentication` table rows with:

```markdown
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login and get token (returns a 2FA challenge when 2FA is on) |
| POST | `/api/auth/login/2fa` | Complete a 2FA login with an authenticator or backup code |
| GET | `/api/auth/me` | Get current user info |
| GET | `/api/auth/2fa/status` | Whether 2FA is on and how many backup codes remain |
| POST | `/api/auth/2fa/setup` | Start 2FA enrollment (returns secret + otpauth URI) |
| POST | `/api/auth/2fa/enable` | Confirm enrollment with a code; returns backup codes once |
| POST | `/api/auth/2fa/disable` | Turn off 2FA (requires password + code) |

> **Locked out of 2FA?** If a user has lost both their authenticator and their backup codes, stop the app, open `data/data.json`, and remove that user's `totp_*` and `backup_code_hashes` fields. They can then sign in with just their password.
```

- [ ] **Step 7: Commit**

```bash
git add backend/two_factor.py backend/models.py backend/main.py backend/tests/test_two_factor_manage.py README.md
git commit -m "feat: add 2FA setup, enable, disable and status endpoints" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Two-step login in the frontend

**Files:**
- Modify: `frontend/src/api.js` (response interceptor lines 21–32; `authAPI` lines 34–45; new `twoFactorAPI` after it)
- Modify: `frontend/src/AuthContext.jsx` (`login`, `register`, provider value)
- Modify: `frontend/src/pages/Login.jsx` (full replacement)

**Interfaces:**
- Consumes (Tasks 4–5): `POST /api/auth/login` → `{mfa_required, mfa_token}` or `{access_token}`; `POST /api/auth/login/2fa {mfa_token, code}`; the `/api/auth/2fa/*` shapes listed in Task 5.
- Produces:
  - `authAPI.verify2fa(mfaToken, code)`
  - `twoFactorAPI.{status(), setup(), enable(code), disable(password, code)}` (used by Task 7)
  - `useAuth().login(credentials) -> Promise<{mfaRequired: true, mfaToken} | {mfaRequired: false, user}>`
  - `useAuth().completeMfaLogin(mfaToken, code) -> Promise<user>`

- [ ] **Step 1: Update `api.js`**

Replace the `// Handle auth errors` interceptor block with:

```js
// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Login endpoints use 401 for bad credentials/codes; let the form show those inline.
    const isLoginRequest = error.config?.url?.startsWith('/api/auth/login');
    if (error.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

In `authAPI`, after the `getMe` line, add:

```js
  verify2fa: (mfaToken, code) => api.post('/api/auth/login/2fa', { mfa_token: mfaToken, code }),
```

After the `authAPI` object, add:

```js
// Two-Factor Authentication API
export const twoFactorAPI = {
  status: () => api.get('/api/auth/2fa/status'),
  setup: () => api.post('/api/auth/2fa/setup'),
  enable: (code) => api.post('/api/auth/2fa/enable', { code }),
  disable: (password, code) => api.post('/api/auth/2fa/disable', { password, code }),
};
```

- [ ] **Step 2: Update `AuthContext.jsx`**

Replace the `login` and `register` functions with the version below. It adds `finishLogin` and `completeMfaLogin`.

```jsx
  const finishLogin = async (accessToken) => {
    localStorage.setItem('token', accessToken);
    const userResponse = await authAPI.getMe();
    setUser(userResponse.data);
    return userResponse.data;
  };

  const login = async (credentials) => {
    const response = await authAPI.login(credentials);
    if (response.data.mfa_required) {
      return { mfaRequired: true, mfaToken: response.data.mfa_token };
    }
    const user = await finishLogin(response.data.access_token);
    return { mfaRequired: false, user };
  };

  const completeMfaLogin = async (mfaToken, code) => {
    const response = await authAPI.verify2fa(mfaToken, code);
    return finishLogin(response.data.access_token);
  };

  const register = async (data) => {
    await authAPI.register(data);
    return login({ username: data.username, password: data.password });
  };
```

Change the provider value to:

```jsx
    <AuthContext.Provider value={{ user, login, completeMfaLogin, register, logout, loading }}>
```

(`Register.jsx` only awaits `register(...)` and ignores its value, so it needs no change.)

- [ ] **Step 3: Replace `Login.jsx`**

Replace `frontend/src/pages/Login.jsx` entirely:

```jsx
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Eye, EyeOff } from 'lucide-react';

const SESSION_EXPIRED = 'Invalid or expired login session';

const errorDetail = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

export default function Login() {
  const [formData, setFormData] = useState({ username: '', password: '' });
  const [step, setStep] = useState('credentials');
  const [mfaToken, setMfaToken] = useState(null);
  const [code, setCode] = useState('');
  const [useBackupCode, setUseBackupCode] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();

  const backToCredentials = (message = '') => {
    setStep('credentials');
    setMfaToken(null);
    setCode('');
    setUseBackupCode(false);
    setFormData((prev) => ({ ...prev, password: '' }));
    setError(message);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await login(formData);
      if (result.mfaRequired) {
        setMfaToken(result.mfaToken);
        setCode('');
        setStep('code');
      } else {
        navigate('/');
      }
    } catch (err) {
      setError(errorDetail(err, 'Login failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleCodeSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await completeMfaLogin(mfaToken, code);
      navigate('/');
    } catch (err) {
      const detail = errorDetail(err, 'Verification failed. Please try again.');
      if (detail === SESSION_EXPIRED) {
        backToCredentials('Login session expired, please sign in again');
      } else {
        setError(detail);
        setCode('');
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleBackupCode = () => {
    setUseBackupCode(!useBackupCode);
    setCode('');
    setError('');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-white rounded-2xl shadow-lg mb-4">
            <span className="text-4xl">💰</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">
            {step === 'code' ? 'Two-factor authentication' : 'Welcome Back'}
          </h1>
          <p className="text-gray-600 mt-1">
            {step === 'code'
              ? (useBackupCode ? 'Enter one of your backup codes' : 'Enter the 6-digit code from your authenticator app')
              : 'Sign in to your Net Worth Tracker'}
          </p>
        </div>

        {/* Form */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          {step === 'credentials' ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label">Username</label>
                <input
                  type="text"
                  className="input"
                  placeholder="Enter your username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="input pr-12"
                    placeholder="Enter your password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCodeSubmit} className="space-y-5">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label" htmlFor="mfa-code">
                  {useBackupCode ? 'Backup code' : 'Authentication code'}
                </label>
                {useBackupCode ? (
                  <input
                    key="backup"
                    id="mfa-code"
                    type="text"
                    className="input font-mono tracking-wider"
                    placeholder="xxxx-xxxx"
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    maxLength={20}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    autoFocus
                    required
                  />
                ) : (
                  <input
                    key="totp"
                    id="mfa-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    className="input text-center text-2xl font-mono tracking-[0.5em]"
                    placeholder="000000"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    autoFocus
                    required
                  />
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Verifying...' : 'Verify'}
              </button>

              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-primary-600 hover:text-primary-700 font-medium"
                  onClick={toggleBackupCode}
                >
                  {useBackupCode ? 'Use authenticator app' : 'Use a backup code instead'}
                </button>
                <button
                  type="button"
                  className="text-gray-600 hover:text-gray-800"
                  onClick={() => backToCredentials()}
                >
                  Back to sign in
                </button>
              </div>
            </form>
          )}

          {step === 'credentials' && (
            <div className="mt-6 text-center">
              <p className="text-gray-600">
                Don't have an account?{' '}
                <Link to="/register" className="text-primary-600 hover:text-primary-700 font-medium">
                  Sign up
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build check**

```bash
cd frontend && npm install && npm run build
```

Expected: `✓ built in ...` with no errors. `npm install` creates `frontend/package-lock.json`. The repo doesn't track a lockfile, so **never commit it**; `frontend/dist/` and `node_modules/` are already gitignored.

- [ ] **Step 5: Manual verification in the browser**

1. Start the backend and frontend as in **Local Run**. Open `http://localhost:3000`.
2. Create a 2FA test user through the API. Remember the secret it prints.
   ```bash
   python - <<'EOF'
   import httpx, pyotp
   api = "http://localhost:8000"
   httpx.post(f"{api}/api/auth/register", json={"username": "mfademo", "password": PASSWORD, "email": "m@example.com"})
   tok = httpx.post(f"{api}/api/auth/login", data={"username": "mfademo", "password": PASSWORD}).json()["access_token"]
   h = {"Authorization": f"Bearer {tok}"}
   secret = httpx.post(f"{api}/api/auth/2fa/setup", headers=h).json()["secret"]
   codes = httpx.post(f"{api}/api/auth/2fa/enable", headers=h, json={"code": pyotp.TOTP(secret).now()}).json()["backup_codes"]
   print("SECRET", secret); print("BACKUP", codes)
   EOF
   ```
   Get a current code with the command below, waiting for the next 30-second window after enrollment because the enrollment code is used up:
   ```bash
   python -c "import pyotp,sys; print(pyotp.TOTP(sys.argv[1]).now())" <SECRET>
   ```
3. Check each of these:
   - **Plain user:** register a new user `plainuser` via `/register`. You land on the dashboard. Log out, log back in: there is no code step.
   - **Wrong password:** the inline error "Incorrect username or password" **stays visible** with no page reload.
   - **`mfademo` + password:** the card switches to "Two-factor authentication". A wrong 6-digit code shows "Invalid authentication code" inline and stays on the code step. The current code takes you to the dashboard.
   - **Backup code:** log out → `mfademo` → "Use a backup code instead" → enter one backup code in UPPERCASE → dashboard.
   - **"Back to sign in"** returns to the credentials form with the password cleared.
   - **Expired session:** stop the backend and restart it with `MFA_TOKEN_EXPIRE_MINUTES=1` added to its environment. Log in as `mfademo`, wait 65 s on the code step, then submit a current code. You return to the credentials form with "Login session expired, please sign in again". Afterwards, remove the env var and restart.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.js frontend/src/AuthContext.jsx frontend/src/pages/Login.jsx
git commit -m "feat: add 2FA code step to login" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Security page (enroll, backup codes, disable)

**Files:**
- Modify: `frontend/package.json` (dependencies)
- Create: `frontend/src/pages/Security.jsx`
- Modify: `frontend/src/App.jsx` (import + route)
- Modify: `frontend/src/components/Layout.jsx` (lucide import + `navItems`)
- Modify: `README.md` (Core Features list)

**Interfaces:**
- Consumes (Task 6): `twoFactorAPI.status()` → `{enabled, backup_codes_remaining}`, `setup()` → `{secret, otpauth_uri}`, `enable(code)` → `{backup_codes}`, `disable(password, code)` → 204. Errors carry `response.data.detail` (string).
- Produces: route `/security`, sidebar item "Security".

- [ ] **Step 1: Add the dependency**

In `frontend/package.json` `dependencies`, after `"lucide-react": "^0.468.0"`, add a comma and:

```json
    "qrcode.react": "^4.2.0"
```

- [ ] **Step 2: Create `Security.jsx`**

Create `frontend/src/pages/Security.jsx`:

```jsx
import { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { ShieldCheck, ShieldOff, Copy, Check, Download, KeyRound, AlertCircle } from 'lucide-react';
import { twoFactorAPI } from '../api';

const errorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

const groupSecret = (secret) => secret.match(/.{1,4}/g).join(' ');

const copyText = async (text) => {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // navigator.clipboard is unavailable over plain http (common for self-hosted LAN installs)
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
};

function BackupCodesModal({ codes, onClose }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join('\n');

  const handleCopy = async () => {
    await copyText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob(
      [`NetWorth Tracker backup codes\nEach code can be used once.\n\n${text}\n`],
      { type: 'text/plain' }
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'networth-tracker-backup-codes.txt';
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Save your backup codes</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Each code can be used once to sign in if you lose your authenticator app. They won't be shown again.
        </p>
        <div className="grid grid-cols-2 gap-2 my-5 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg font-mono text-sm text-gray-900 dark:text-gray-100">
          {codes.map((code) => (
            <span key={code} className="text-center">{code}</span>
          ))}
        </div>
        <div className="flex gap-3 mb-3">
          <button type="button" onClick={handleCopy} className="btn-secondary flex-1 flex items-center justify-center gap-2">
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copied ? 'Copied' : 'Copy all'}
          </button>
          <button type="button" onClick={handleDownload} className="btn-secondary flex-1 flex items-center justify-center gap-2">
            <Download className="w-4 h-4" />
            Download .txt
          </button>
        </div>
        <button type="button" onClick={onClose} className="btn-primary w-full">
          I've saved these codes
        </button>
      </div>
    </div>
  );
}

export default function Security() {
  const [status, setStatus] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState('');
  const [disableForm, setDisableForm] = useState({ password: '', code: '' });
  const [backupCodes, setBackupCodes] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [secretCopied, setSecretCopied] = useState(false);

  const loadStatus = async () => {
    try {
      const res = await twoFactorAPI.status();
      setStatus(res.data);
    } catch (err) {
      setLoadError(errorMessage(err, 'Failed to load security settings'));
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const startSetup = async () => {
    setError('');
    setBusy(true);
    try {
      const res = await twoFactorAPI.setup();
      setSetup(res.data);
      setCode('');
    } catch (err) {
      setError(errorMessage(err, 'Failed to start setup'));
    } finally {
      setBusy(false);
    }
  };

  const cancelSetup = () => {
    setSetup(null);
    setCode('');
    setError('');
  };

  const copySecret = async () => {
    await copyText(setup.secret);
    setSecretCopied(true);
    setTimeout(() => setSecretCopied(false), 2000);
  };

  const confirmEnable = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const res = await twoFactorAPI.enable(code);
      setSetup(null);
      setCode('');
      setBackupCodes(res.data.backup_codes);
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err, 'Failed to enable two-factor authentication'));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await twoFactorAPI.disable(disableForm.password, disableForm.code);
      setDisableForm({ password: '', code: '' });
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err, 'Failed to disable two-factor authentication'));
      setDisableForm((prev) => ({ ...prev, code: '' }));
    } finally {
      setBusy(false);
    }
  };

  const lowOnCodes = status?.enabled && status.backup_codes_remaining <= 3;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Security</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Protect your account with two-factor authentication</p>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {loadError}
        </div>
      )}

      {!status && !loadError && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
        </div>
      )}

      {status && (
        <div className="card max-w-3xl">
          <div className="flex items-start gap-4">
            <div className={`p-3 rounded-xl flex-shrink-0 ${status.enabled
              ? 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400'
              : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}
            >
              {status.enabled ? <ShieldCheck className="w-6 h-6" /> : <ShieldOff className="w-6 h-6" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Two-factor authentication</h2>
                {status.enabled && (
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400">
                    Enabled
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {status.enabled
                  ? 'Signing in requires a code from your authenticator app or a backup code.'
                  : 'Require a code from an authenticator app (Google Authenticator, Authy, 1Password, ...) in addition to your password when signing in.'}
              </p>
            </div>
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {!status.enabled && !setup && (
            <button type="button" onClick={startSetup} disabled={busy} className="btn-primary mt-6 disabled:opacity-50">
              Enable two-factor authentication
            </button>
          )}

          {!status.enabled && setup && (
            <div className="mt-6 space-y-5">
              <div className="flex flex-col sm:flex-row gap-6 items-center sm:items-start">
                <div className="p-3 bg-white rounded-lg border border-gray-200 flex-shrink-0">
                  <QRCodeSVG value={setup.otpauth_uri} size={176} bgColor="#ffffff" fgColor="#000000" />
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 space-y-3 min-w-0 w-full">
                  <p><span className="font-medium text-gray-900 dark:text-white">1.</span> Scan this QR code with your authenticator app.</p>
                  <p>Can't scan it? Enter this key manually:</p>
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 px-3 py-2 rounded-lg break-all">
                      {groupSecret(setup.secret)}
                    </code>
                    <button
                      type="button"
                      onClick={copySecret}
                      className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 flex-shrink-0"
                      title="Copy key"
                    >
                      {secretCopied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  <p><span className="font-medium text-gray-900 dark:text-white">2.</span> Enter the 6-digit code the app shows to confirm.</p>
                </div>
              </div>
              <form onSubmit={confirmEnable} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  className="input sm:max-w-[12rem] text-center font-mono tracking-[0.3em]"
                  placeholder="000000"
                  aria-label="Authentication code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                  autoFocus
                  required
                />
                <button type="submit" disabled={busy || code.length !== 6} className="btn-primary disabled:opacity-50">
                  Verify &amp; enable
                </button>
                <button type="button" onClick={cancelSetup} className="btn-secondary">
                  Cancel
                </button>
              </form>
            </div>
          )}

          {status.enabled && (
            <div className="mt-6 space-y-5">
              <div className={`flex items-center gap-2 text-sm ${lowOnCodes
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-gray-600 dark:text-gray-400'}`}
              >
                <KeyRound className="w-4 h-4 flex-shrink-0" />
                <span>
                  Backup codes remaining: <strong>{status.backup_codes_remaining}</strong>
                  {lowOnCodes && ' (disable and re-enable 2FA to get a new set)'}
                </span>
              </div>

              <form onSubmit={handleDisable} className="border-t border-gray-100 dark:border-gray-700 pt-5 space-y-4">
                <h3 className="font-medium text-gray-900 dark:text-white">Disable two-factor authentication</h3>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="label" htmlFor="disable-password">Password</label>
                    <input
                      id="disable-password"
                      type="password"
                      autoComplete="current-password"
                      className="input"
                      value={disableForm.password}
                      onChange={(e) => setDisableForm({ ...disableForm, password: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="disable-code">Authentication or backup code</label>
                    <input
                      id="disable-code"
                      type="text"
                      autoComplete="one-time-code"
                      className="input font-mono"
                      maxLength={20}
                      value={disableForm.code}
                      onChange={(e) => setDisableForm({ ...disableForm, code: e.target.value })}
                      required
                    />
                  </div>
                </div>
                <button type="submit" disabled={busy} className="btn-danger disabled:opacity-50">
                  Disable 2FA
                </button>
              </form>
            </div>
          )}
        </div>
      )}

      {backupCodes && <BackupCodesModal codes={backupCodes} onClose={() => setBackupCodes(null)} />}
    </div>
  );
}
```

- [ ] **Step 3: Wire up the route and nav**

In `frontend/src/App.jsx`:
- after `import Equities from './pages/Equities';`, add `import Security from './pages/Security';`
- after `<Route path="mutual-funds" element={<MutualFunds />} />`, add:

```jsx
              <Route path="security" element={<Security />} />
```

In `frontend/src/components/Layout.jsx`:
- add `ShieldCheck,` to the `lucide-react` import list, after `Shield,`
- append to `navItems` after the Mutual Funds entry:

```js
    { to: '/security', icon: ShieldCheck, label: 'Security' },
```

- [ ] **Step 4: Update the README feature list**

In `README.md` under `### Core Features`, after the `- **User Authentication** ...` line, add:

```markdown
- **Two-Factor Authentication** - Optional TOTP 2FA (Google Authenticator, Authy, 1Password, ...) with one-time backup codes, managed from the Security page
```

- [ ] **Step 5: Build check**

```bash
cd frontend && npm install && npm run build
```

Expected: `✓ built in ...` with no errors, and `qrcode.react` resolved.

- [ ] **Step 6: Manual verification in the browser**

Run backend and frontend as in **Local Run**. Use a fresh data file: `rm -rf /tmp/nwt-2fa` in WSL, then restart the backend. Then check each item:

1. Register `secuser`. "Security" appears last in the sidebar (desktop and mobile menu). The page shows the "Two-factor authentication" card, not enabled.
2. Click "Enable two-factor authentication":
   - A QR code renders, with dark modules on white.
   - The key is shown in 4-character groups.
   - Copy key → the clipboard holds the raw 32-character secret with no spaces.
3. Type a wrong 6-digit code → inline "Invalid authentication code"; the QR stays. Type the current code (from the secret, using the Task 6 `pyotp` one-liner) → the backup-codes modal opens with 10 codes in 2 columns.
4. In the modal:
   - "Copy all" → the clipboard holds 10 lines.
   - "Download .txt" downloads `networth-tracker-backup-codes.txt`.
   - Clicking the backdrop or pressing Esc does **not** close it. "I've saved these codes" does.
5. The card now shows the "Enabled" badge and "Backup codes remaining: 10".
6. Log out and log in with a backup code. Security then shows 9.
7. Disable with a wrong password → inline "Incorrect password", and you are **still logged in** (no redirect to /login). Then disable with the correct password and a current code → the card returns to the not-enabled state. Log out and back in: there is no code step.
8. **Low-code warning:** re-enable, then use 7 backup codes (log in 7 times, or call `/api/auth/login/2fa` via httpx) → the count turns amber with the "disable and re-enable" hint.
9. **Clipboard fallback:** in the browser console, run `Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })`. Then click Copy key during setup → no console error, and pasting gives the secret.
10. Toggle dark mode on the Security page and in the modal. Everything is readable, and the QR keeps its white background.
11. **Phone width:** resize to mobile (375 px). The QR and key stack vertically with no horizontal scroll.

- [ ] **Step 7: Run the full backend suite one last time**

Run the backend test command with `tests`.
Expected: 60 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/src/pages/Security.jsx frontend/src/App.jsx frontend/src/components/Layout.jsx README.md
git commit -m "feat: add Security page for 2FA enrollment and backup codes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
