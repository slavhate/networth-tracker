# Change Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user change their own password from the Security page. The change signs out every other session.

**Architecture:**
- Every access token and 2FA challenge token carries a `ver` claim matching the user's `token_version` (missing means 0). The shared `get_current_user` dependency rejects tokens whose `ver` doesn't match.
- A new `POST /api/auth/password` checks the current password (plus a 2FA code when 2FA is on, with the existing lockout), stores the new hash, bumps `token_version`, and returns a fresh token.
- The frontend adds a "Change password" card to the Security page and swaps in the returned token.

**Tech Stack:** FastAPI 0.115, python-jose, passlib/bcrypt, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-12-change-password-design.md`. Read it before starting any task.

## Global Constraints

- **Branch:** `feat/change-password` (from `main` at `bf40faf`, which includes 2FA), in its own worktree.
- **Environment:** Python 3.12 with a virtualenv that has `backend/requirements-dev.txt` installed, and Node 18+. Commands run from the repository root in a POSIX shell (on Windows, inside WSL).
- **Backend test command:** `cd backend && python -m pytest tests -v`.
  - `tests/conftest.py` pins `TZ=Asia/Kolkata` automatically.
  - To run one file, replace `tests` with its path; for one test, append `::test_name`.
  - Expected totals: 63 before this work, 71 after Task 1, 87 after Task 2.
- **No new dependencies** (backend or frontend).
- **Data model:** user field `token_version` (int; missing means 0). Token claim `ver` (missing means 0).
- **Error contract** (exact strings). Every error from `POST /api/auth/password` is 400, never 401, apart from the lockout's 429:
  - `"Incorrect password"`
  - `"New password must be different from the current password"`
  - `"Authentication code required"`
  - `"Invalid authentication code"`
  - 429: `"Too many attempts. Try again in N minutes."`
  - A stale or unknown token gets the existing 401 `"Could not validate credentials"`. A stale 2FA challenge gets 401 `"Invalid or expired login session"`.
- **Validation:** `new_password` at least 6 characters (422); `code` at most 64 characters (422).
- **Commits:**
  - Commit with the repository's configured no-reply identity.
  - Every message ends with a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Style:** follow existing patterns. Backend uses module-level functions, `db.` helpers and `HTTPException`. Frontend uses Tailwind component classes (`card`, `input`, `label`, `btn-primary`) with `dark:` variants.

## Review Focus

1. **Sessions from before this ships must stay valid.** A token with no `ver`, for a user with no `token_version`, keeps working; the same token stops working after that user's first password change. Covered in Task 1 and Task 2.
2. **Long (>72-byte) and non-ASCII passwords.** bcrypt truncates at 72 bytes. Changing to such a password must work and must allow login afterwards, with no 500. Covered in Task 2 (`test_long_and_unicode_passwords_work`).
3. **A 2FA user sends an empty code (`""`) rather than none.** That must be treated as missing (400 "Authentication code required") and must not count toward the lockout. Covered in Task 2.
4. **"Other sessions" means other browsers.** Tabs of one origin share `localStorage`, so they pick up the new token; that's expected. The manual check must use a second *origin* (`127.0.0.1` vs `localhost`) or an API token. Covered in Task 3's manual check.
5. **Parallel wrong password guesses on the new endpoint** must not get past the 5-attempt lockout. Covered in Task 2 (`test_concurrent_wrong_passwords_cannot_bypass_the_lockout`).

---

### Task 1: Token versioning

**Files:**
- Modify: `backend/auth.py` (imports; `decode_token`; `create_mfa_token`; `get_current_user`; new `decode_access_token`)
- Modify: `backend/main.py` (`_access_token_for`, `login`, `login_2fa`)
- Test: `backend/tests/test_auth_tokens.py` (append 2 tests)
- Test: `backend/tests/test_token_version.py` (new, 6 tests)

**Interfaces:**
- Consumes: `db.get_user_by_username`, `db.update_user`, `two_factor.generate_secret`; test fixtures `client`, `auth_headers`, `clock`; `totp_helpers.NOW_STEP` and `code_for`.
- Produces:
  - `auth.decode_access_token(token: str) -> Optional[dict]`
  - `auth.create_mfa_token(username: str, user_id: str, token_version: int = 0) -> str`
  - `auth.get_current_user` rejects tokens whose `ver` doesn't match the user's `token_version`
  - `main._access_token_for(user)` embeds `"ver"`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_auth_tokens.py`:

```python
def test_decode_access_token_returns_the_payload():
    payload = auth.decode_access_token(auth.create_access_token({"sub": "alice", "user_id": "u1", "ver": 3}))
    assert payload["sub"] == "alice"
    assert payload["ver"] == 3
    assert auth.decode_access_token(auth.create_mfa_token("alice", "u1")) is None


def test_mfa_token_carries_the_token_version():
    assert auth.decode_mfa_token(auth.create_mfa_token("alice", "u1", 4))["ver"] == 4
    assert auth.decode_mfa_token(auth.create_mfa_token("alice", "u1"))["ver"] == 0
```

Create `backend/tests/test_token_version.py`:

```python
import auth
import database as db
import two_factor as tf
from totp_helpers import NOW_STEP, code_for


def me(client, token):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_login_token_carries_version_zero_for_existing_users(client, auth_headers):
    token = auth_headers["Authorization"].split()[1]
    assert auth.decode_access_token(token)["ver"] == 0


def test_token_without_ver_works_for_users_without_token_version(client, auth_headers):
    user = db.get_user_by_username("tester")
    assert "token_version" not in user
    legacy = auth.create_access_token({"sub": "tester", "user_id": user["id"]})
    assert me(client, legacy).status_code == 200


def test_token_with_stale_version_is_rejected(client, auth_headers):
    user = db.get_user_by_username("tester")
    db.update_user(user["id"], {"token_version": 1})
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
    fresh = client.post("/api/auth/login", data={"username": "tester", "password": PASSWORD}).json()["access_token"]
    assert auth.decode_access_token(fresh)["ver"] == 1
    assert me(client, fresh).status_code == 200


def test_stale_version_is_rejected_on_data_endpoints_too(client, auth_headers):
    user = db.get_user_by_username("tester")
    db.update_user(user["id"], {"token_version": 1})
    assert client.get("/api/assets", headers=auth_headers).status_code == 401


def test_token_for_unknown_user_is_rejected(client):
    ghost = auth.create_access_token({"sub": "ghost", "user_id": "nope"})
    assert me(client, ghost).status_code == 401


def test_mfa_challenge_with_stale_version_cannot_complete_login(client, clock):
    client.post("/api/auth/register", json={"username": "alice", "password": PASSWORD, "email": "a@example.com"})
    user = db.get_user_by_username("alice")
    secret = tf.generate_secret()
    db.update_user(user["id"], {"totp_enabled": True, "totp_secret": secret})
    mfa_token = client.post("/api/auth/login", data={"username": "alice", "password": PASSWORD}).json()["mfa_token"]
    db.update_user(user["id"], {"token_version": 1})
    resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": code_for(secret, NOW_STEP)})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth_tokens.py tests/test_token_version.py -v`

Expected:
- `AttributeError: module 'auth' has no attribute 'decode_access_token'` and a `TypeError` for the extra argument to `create_mfa_token`.
- The stale-version tests and the 2FA-challenge test FAIL (200 or a token instead of 401).
- `test_token_for_unknown_user_is_rejected` FAILS: `/api/auth/me` returns 404 today.
- `test_token_without_ver_works_for_users_without_token_version` already passes. It's a regression guard.

- [ ] **Step 3: Implement token versioning in `auth.py`**

Add `import database as db` after the `from models import TokenData` line.

Replace `decode_token` with the following two functions, keeping its position:

```python
def decode_access_token(token: str) -> Optional[dict]:
    """Payload of a valid access token (untyped or type "access"), else None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") not in (None, "access"):
        return None  # a 2FA challenge token (or any other typed token) is not an access token
    if payload.get("sub") is None:
        return None
    return payload

def decode_token(token: str) -> Optional[str]:
    payload = decode_access_token(token)
    return payload["sub"] if payload else None
```

Replace `create_mfa_token`:

```python
def create_mfa_token(username: str, user_id: str, token_version: int = 0) -> str:
    """Short-lived token proving the password step of a 2FA login succeeded."""
    return create_access_token(
        data={"sub": username, "user_id": user_id, "type": "mfa", "ver": token_version},
        expires_delta=timedelta(minutes=settings.MFA_TOKEN_EXPIRE_MINUTES)
    )
```

Replace `get_current_user`:

```python
async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    # Tokens carry the user's token_version ("ver", missing = 0); a password change bumps it,
    # which revokes every token issued before the change.
    user = db.get_user_by_username(payload["sub"])
    if not user or payload.get("ver", 0) != user.get("token_version", 0):
        raise credentials_exception
    return payload["sub"]
```

- [ ] **Step 4: Embed the version in tokens issued by `main.py`**

In `_access_token_for`, change the `data=` line to:

```python
        data={"sub": user["username"], "user_id": user["id"], "ver": user.get("token_version", 0)},
```

In `login`, change the `mfa_token=` line to:

```python
            mfa_token=create_mfa_token(user["username"], user["id"], user.get("token_version", 0))
```

In `login_2fa`, change the guard `if not user or not user.get("totp_enabled"):` to:

```python
    if not user or not user.get("totp_enabled") or payload.get("ver", 0) != user.get("token_version", 0):
```

- [ ] **Step 5: Run all backend tests to verify they pass**

Run: `cd backend && python -m pytest tests -v`
Expected: 71 passed (63 existing + 8 new). There should be no new warning types; the pre-existing DeprecationWarnings from untouched code are accepted.

- [ ] **Step 6: Commit**

```bash
git add backend/auth.py backend/main.py backend/tests/test_auth_tokens.py backend/tests/test_token_version.py
git commit -m "feat: version access tokens so they can be revoked" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `POST /api/auth/password`

**Files:**
- Create: `backend/tests/api_helpers.py` (move `enable_2fa` and `fire_concurrently` here)
- Modify: `backend/tests/test_two_factor_manage.py` (import the moved helpers; drop now-unused imports)
- Modify: `backend/models.py` (new `PasswordChange` after `TwoFactorBackupCodes`)
- Modify: `backend/main.py` (models import; new section after `two_factor_disable`, before `# ============== Asset Routes ==============`)
- Modify: `README.md` (Authentication API table)
- Test: `backend/tests/test_change_password.py` (new, 16 tests)

**Interfaces:**
- Consumes:
  - Task 1: `_access_token_for(user)` embeds `ver`; `get_current_user` enforces it.
  - Existing: `get_current_user_record`, `_now`, `_too_many_attempts(user, now)`, `two_factor.is_locked`, `record_failure`, `verify_second_factor`, `verify_password`, `get_password_hash`, `db.get_user_by_id`, `db.update_user`.
- Produces:
  - `POST /api/auth/password`, body `{current_password, new_password, code?}`. On 200 it returns `{access_token, token_type: "bearer", mfa_required: false}`. Task 3's frontend relies on this exact path and shape.
  - Test helpers `api_helpers.enable_2fa(client, headers) -> (secret, backup_codes)` and `api_helpers.fire_concurrently(requests) -> responses`.

- [ ] **Step 1: Move the shared test helpers**

Create `backend/tests/api_helpers.py`:

```python
"""Shared API-level helpers for tests."""
import asyncio

import httpx

import main
from totp_helpers import NOW_STEP, code_for


def enable_2fa(client, headers):
    """Run setup + enable at NOW_STEP. Later TOTP uses must be NOW_STEP + 1 (replay protection)."""
    setup = client.post("/api/auth/2fa/setup", headers=headers).json()
    resp = client.post("/api/auth/2fa/enable", headers=headers, json={"code": code_for(setup["secret"], NOW_STEP)})
    assert resp.status_code == 200
    return setup["secret"], resp.json()["backup_codes"]


def fire_concurrently(requests):
    """Send (path, headers, json) requests all at once through the ASGI app; return the responses."""
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[ac.post(path, headers=h, json=body) for path, h, body in requests])

    return asyncio.run(run())
```

In `backend/tests/test_two_factor_manage.py`:
- delete its own `enable_2fa` and `fire_concurrently` definitions;
- delete the now-unused `import asyncio`, `import httpx` and `import main` lines (keep `from collections import Counter`);
- add `from api_helpers import enable_2fa, fire_concurrently` next to the `totp_helpers` import.

Run: `cd backend && python -m pytest tests/test_two_factor_manage.py -v`
Expected: 18 passed (behaviour unchanged).

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_change_password.py`:

```python
from collections import Counter

import auth
import database as db
from api_helpers import enable_2fa, fire_concurrently
from totp_helpers import NOW_STEP, code_for, wrong_code

OLD = PASSWORD  # password of the auth_headers fixture's user "tester"
NEW = OTHER_PASSWORD


def change(client, headers, current, new, code=None):
    body = {"current_password": current, "new_password": new}
    if code is not None:
        body["code"] = code
    return client.post("/api/auth/password", headers=headers, json=body)


def login(client, password):
    return client.post("/api/auth/login", data={"username": "tester", "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_change_password_requires_login(client):
    resp = client.post("/api/auth/password", json={"current_password": OLD, "new_password": NEW})
    assert resp.status_code == 401


def test_change_password_returns_a_working_token_and_revokes_the_old_one(client, auth_headers, clock):
    resp = change(client, auth_headers, OLD, NEW)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"access_token", "token_type", "mfa_required"}
    assert client.get("/api/auth/me", headers=bearer(body["access_token"])).status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401


def test_login_uses_the_new_password(client, auth_headers, clock):
    assert change(client, auth_headers, OLD, NEW).status_code == 200
    assert "access_token" in login(client, NEW).json()
    assert login(client, OLD).status_code == 401


def test_legacy_token_without_version_is_revoked_too(client, auth_headers, clock):
    user = db.get_user_by_username("tester")
    legacy = bearer(auth.create_access_token({"sub": "tester", "user_id": user["id"]}))
    assert change(client, auth_headers, OLD, NEW).status_code == 200
    assert client.get("/api/auth/me", headers=legacy).status_code == 401


def test_wrong_current_password_is_400_and_changes_nothing(client, auth_headers, clock):
    resp = change(client, auth_headers, WRONG_PASSWORD, NEW)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Incorrect password"
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200
    assert login(client, OLD).status_code == 200


def test_new_password_must_differ_from_the_current_one(client, auth_headers, clock):
    resp = change(client, auth_headers, OLD, OLD)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "New password must be different from the current password"


def test_short_new_password_is_rejected_by_validation(client, auth_headers, clock):
    assert change(client, auth_headers, OLD, "12345").status_code == 422
    assert login(client, OLD).status_code == 200


def test_long_and_unicode_passwords_work(client, auth_headers, clock):
    long_unicode = "pässwörd-ü-" + "x" * 100
    assert change(client, auth_headers, OLD, long_unicode).status_code == 200
    assert login(client, long_unicode).status_code == 200


def test_five_wrong_current_passwords_lock_the_endpoint(client, auth_headers, clock):
    for _ in range(5):
        assert change(client, auth_headers, WRONG_PASSWORD, NEW).status_code == 400
    locked = change(client, auth_headers, OLD, NEW)
    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many attempts. Try again in 15 minutes."
    assert login(client, OLD).status_code == 200


def test_concurrent_wrong_passwords_cannot_bypass_the_lockout(client, auth_headers, clock):
    attempt = ("/api/auth/password", auth_headers, {"current_password": WRONG_PASSWORD, "new_password": NEW})
    statuses = Counter(r.status_code for r in fire_concurrently([attempt] * 30))
    assert statuses == {400: 5, 429: 25}
    assert login(client, OLD).status_code == 200


def test_2fa_user_needs_a_code(client, auth_headers, clock):
    enable_2fa(client, auth_headers)
    for missing in (None, ""):
        resp = change(client, auth_headers, OLD, NEW, code=missing)
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Authentication code required"
    assert db.get_user_by_username("tester").get("totp_failed_attempts", 0) == 0


def test_2fa_user_wrong_code_counts_toward_the_lockout(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    resp = change(client, auth_headers, OLD, NEW, code=wrong_code(secret, NOW_STEP + 1))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid authentication code"
    assert db.get_user_by_username("tester")["totp_failed_attempts"] == 1
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200


def test_2fa_user_can_change_with_a_current_code(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    resp = change(client, auth_headers, OLD, NEW, code=code_for(secret, NOW_STEP + 1))
    assert resp.status_code == 200
    assert client.get("/api/auth/me", headers=bearer(resp.json()["access_token"])).status_code == 200


def test_2fa_enrollment_code_cannot_be_replayed(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    resp = change(client, auth_headers, OLD, NEW, code=code_for(secret, NOW_STEP))
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid authentication code"


def test_2fa_user_can_change_with_a_backup_code(client, auth_headers, clock):
    _, codes = enable_2fa(client, auth_headers)
    resp = change(client, auth_headers, OLD, NEW, code=codes[0])
    assert resp.status_code == 200
    status = client.get("/api/auth/2fa/status", headers=bearer(resp.json()["access_token"])).json()
    assert status["backup_codes_remaining"] == 9


def test_2fa_challenge_started_before_the_change_cannot_finish(client, auth_headers, clock):
    secret, codes = enable_2fa(client, auth_headers)
    mfa_token = login(client, OLD).json()["mfa_token"]
    assert change(client, auth_headers, OLD, NEW, code=code_for(secret, NOW_STEP + 1)).status_code == 200
    resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": codes[0]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_change_password.py -v`
Expected: FAIL, since `/api/auth/password` returns 404 (e.g. `test_change_password_requires_login` gets 404 instead of 401).

- [ ] **Step 4: Add the request model**

In `backend/models.py`, after `class TwoFactorBackupCodes`, add:

```python
class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)
    code: Optional[str] = Field(None, max_length=64)
```

- [ ] **Step 5: Add the endpoint**

In `backend/main.py`, change the models import's second line to:

```python
    TwoFactorCode, TwoFactorDisable, TwoFactorStatus, TwoFactorSetup, TwoFactorBackupCodes, PasswordChange,
```

Insert this block after the `two_factor_disable` function and before `# ============== Asset Routes ==============`:

```python
# ============== Password Routes ==============

@app.post("/api/auth/password", response_model=Token, response_model_exclude_none=True)
async def change_password(request: PasswordChange, user: dict = Depends(get_current_user_record)):
    """Change the current user's password; signs out every other session"""
    user = db.get_user_by_id(user["id"])  # fresh copy: lockout counters must not be stale under concurrent requests
    now = _now()
    if two_factor.is_locked(user, now):
        raise _too_many_attempts(user, now)
    if not verify_password(request.current_password, user["hashed_password"]):
        db.update_user(user["id"], two_factor.record_failure(user, now))
        raise HTTPException(status_code=400, detail="Incorrect password")
    # Checked before the 2FA step so a backup code is never spent on a change that would fail anyway.
    if verify_password(request.new_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")

    second_factor_updates = {}
    if user.get("totp_enabled"):
        if not request.code:
            raise HTTPException(status_code=400, detail="Authentication code required")
        ok, second_factor_updates = two_factor.verify_second_factor(user, request.code, now)
        if not ok:
            db.update_user(user["id"], second_factor_updates)
            raise HTTPException(status_code=400, detail="Invalid authentication code")

    # Bumping token_version revokes every token issued before this change, including this request's.
    updated = db.update_user(user["id"], {
        **second_factor_updates,
        "hashed_password": get_password_hash(request.new_password),
        "token_version": user.get("token_version", 0) + 1,
        "totp_failed_attempts": 0,
        "totp_locked_until": None,
    })
    return _access_token_for(updated)
```

- [ ] **Step 6: Run all backend tests to verify they pass**

Run: `cd backend && python -m pytest tests -v`
Expected: 87 passed (71 + 16 new). No new warning types.

- [ ] **Step 7: Update the README API table**

In `README.md`'s `### Authentication` table, after the `/api/auth/2fa/disable` row, add:

```markdown
| POST | `/api/auth/password` | Change your password (current password, plus a code if 2FA is on); signs out other sessions |
```

- [ ] **Step 8: Commit**

```bash
git add backend/tests/api_helpers.py backend/tests/test_two_factor_manage.py backend/models.py backend/main.py backend/tests/test_change_password.py README.md
git commit -m "feat: add change-password endpoint that signs out other sessions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Change-password card on the Security page

**Files:**
- Create: `frontend/src/utils/errors.js`
- Create: `frontend/src/components/ChangePasswordCard.jsx`
- Modify: `frontend/src/api.js` (`authAPI`)
- Modify: `frontend/src/AuthContext.jsx` (`replaceToken` + provider value)
- Modify: `frontend/src/pages/Security.jsx` (imports, subtitle, render the card, use the shared `errorMessage`)
- Modify: `README.md` (Core Features list)

Note: the spec puts the card "on the Security page". It lives in its own component file so `Security.jsx` (about 360 lines, already focused on 2FA) doesn't grow further. `Security.jsx` renders it.

**Interfaces:**
- Consumes (Task 2): `POST /api/auth/password` with `{current_password, new_password, code?}` returns `{access_token, ...}`. Errors carry a string `response.data.detail`; a 422 carries an array.
- Produces:
  - `authAPI.changePassword(data)`
  - `useAuth().replaceToken(accessToken)`
  - `errorMessage(err, fallback)` in `utils/errors.js`
  - `<ChangePasswordCard twoFactorEnabled={bool} />`

- [ ] **Step 1: Shared error helper**

Create `frontend/src/utils/errors.js`:

```js
// FastAPI puts a human-readable message in `detail`; validation errors (422) carry an array instead.
export const errorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};
```

- [ ] **Step 2: API and auth context**

In `frontend/src/api.js` `authAPI`, after the `verify2fa` line, add:

```js
  changePassword: (data) => api.post('/api/auth/password', data),
```

In `frontend/src/AuthContext.jsx`, after `completeMfaLogin`, add:

```jsx
  // Swap in a fresh access token, e.g. after a password change revoked the old one.
  const replaceToken = (accessToken) => {
    localStorage.setItem('token', accessToken);
  };
```

Change the provider value to:

```jsx
    <AuthContext.Provider value={{ user, login, completeMfaLogin, replaceToken, register, logout, loading }}>
```

- [ ] **Step 3: The card component**

Create `frontend/src/components/ChangePasswordCard.jsx`:

```jsx
import { useState } from 'react';
import { KeyRound, AlertCircle, CheckCircle } from 'lucide-react';
import { authAPI } from '../api';
import { useAuth } from '../AuthContext';
import { errorMessage } from '../utils/errors';

const EMPTY_FORM = { current: '', next: '', confirm: '', code: '' };

export default function ChangePasswordCard({ twoFactorEnabled }) {
  const { replaceToken } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);

  const update = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const validate = () => {
    if (form.next.length < 6) return 'New password must be at least 6 characters';
    if (form.next !== form.confirm) return 'New passwords do not match';
    if (form.next === form.current) return 'New password must be different from the current password';
    return '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSuccess('');
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError('');
    setBusy(true);
    try {
      const res = await authAPI.changePassword({
        current_password: form.current,
        new_password: form.next,
        ...(twoFactorEnabled ? { code: form.code } : {}),
      });
      replaceToken(res.data.access_token);
      setForm(EMPTY_FORM);
      setSuccess("Password changed. You've been signed out on your other devices.");
    } catch (err) {
      setError(errorMessage(err, 'Failed to change password'));
      setForm((prev) => ({ ...prev, code: '' }));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card max-w-3xl">
      <div className="flex items-start gap-4">
        <div className="p-3 rounded-xl flex-shrink-0 bg-primary-50 text-primary-600 dark:bg-primary-900/50 dark:text-primary-300">
          <KeyRound className="w-6 h-6" />
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Change password</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Changing your password signs you out on all your other devices.
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="mt-4 flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {success && (
        <div role="status" className="mt-4 flex items-center gap-2 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 px-4 py-3 rounded-lg text-sm">
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          {success}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label" htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              className="input"
              value={form.current}
              onChange={update('current')}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="new-password">New password</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              className="input"
              value={form.next}
              onChange={update('next')}
              required
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">At least 6 characters</p>
          </div>
          <div>
            <label className="label" htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              className="input"
              value={form.confirm}
              onChange={update('confirm')}
              required
            />
          </div>
          {twoFactorEnabled && (
            <div className="sm:col-span-2">
              <label className="label" htmlFor="change-password-code">Authentication or backup code</label>
              <input
                id="change-password-code"
                type="text"
                autoComplete="one-time-code"
                className="input font-mono sm:max-w-xs"
                maxLength={20}
                value={form.code}
                onChange={update('code')}
                required
              />
            </div>
          )}
        </div>
        <button type="submit" disabled={busy} className="btn-primary disabled:opacity-50">
          {busy ? 'Changing…' : 'Change password'}
        </button>
      </form>
    </div>
  );
}
```

`noValidate` lets the component's own checks (with the spec's messages) run instead of the browser's generic "fill out this field" bubbles. An empty current password or code still reaches the server, which answers with the spec's 400 messages.

- [ ] **Step 4: Render it on the Security page**

In `frontend/src/pages/Security.jsx`:
- delete the local `const errorMessage = (err, fallback) => { ... };` helper (4 lines) and add `import { errorMessage } from '../utils/errors';` after the `twoFactorAPI` import;
- add `import ChangePasswordCard from '../components/ChangePasswordCard';`;
- change the header subtitle text to `Manage your password and two-factor authentication`;
- directly before the 2FA card's `{status && (` line, add:

```jsx
      {status && <ChangePasswordCard twoFactorEnabled={status.enabled} />}
```

The card renders once 2FA status has loaded, so the code field is never hidden from a 2FA user.

- [ ] **Step 5: README feature bullet**

In `README.md` under `### Core Features`, after the `- **Two-Factor Authentication** ...` line, add:

```markdown
- **Change Password** - Change your password from the Security page; your other signed-in devices are signed out
```

- [ ] **Step 6: Build check**

Run: `cd frontend && npm install && npm run build`
Expected: `✓ built in ...` with no errors. `npm install` may create an untracked `frontend/package-lock.json`. The repo doesn't track one, so never commit it.

- [ ] **Step 7: Manual browser verification**

Start the backend and frontend:

```bash
mkdir -p /tmp/nwt-pw && cd backend && DATA_FILE=/tmp/nwt-pw/data.json SECRET_KEY="$(openssl rand -hex 32)" uvicorn main:app --host 0.0.0.0 --port 8000
```

```bash
cd frontend && npm run dev
```

Check:
1. Register `pwuser` with a password of your choice. Security shows the "Change password" card above the 2FA card, with no code field.
2. Client-side checks show inline, and nothing is sent:
   - new password of 5 characters;
   - mismatched confirmation;
   - new password equal to the current one.
3. A wrong current password shows "Incorrect password" inline and you stay logged in.
4. **Other session:** log in as `pwuser` in a second *origin*, e.g. `http://127.0.0.1:3000` if the first tab is `http://localhost:3000`. Tabs of one origin share `localStorage`, so they'd share the new token. Change the password in the first tab: success message shown, fields cleared, and the first tab keeps working (reload the dashboard). In the second origin, the next navigation lands on `/login`.
5. Log in with the new password; the old one fails.
6. Turn on 2FA. The card now shows the code field. Changing the password with a current code works; with no code it shows "Authentication code required".
7. Check dark mode and a 375 px layout (no horizontal scroll).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/utils/errors.js frontend/src/components/ChangePasswordCard.jsx frontend/src/api.js frontend/src/AuthContext.jsx frontend/src/pages/Security.jsx README.md
git commit -m "feat: add change-password card to the Security page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
