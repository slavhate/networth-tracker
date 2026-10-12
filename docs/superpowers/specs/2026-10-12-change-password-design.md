# Change Password — Design Spec

**Date:** 2026-10-12
**Branch:** `feat/change-password` (from `main` at `bf40faf`, which includes 2FA)
**Context:** Self-hosted FastAPI + React app; users in `data/data.json`; stateless JWT access tokens (24 h); optional TOTP 2FA with a shared lockout counter.

---

## 1. Goal

A logged-in user can change their own password from the Security page. Changing it **signs out every other session**; the browser that made the change stays logged in.

**Decisions (agreed):**
- Requires the current password. When 2FA is on, it also requires a current authenticator or backup code, the same rule as disabling 2FA.
- Wrong current-password or code attempts count toward the existing lockout (5 failures → 15 minutes).
- Other sessions are revoked with a per-user **token version** embedded in every token (approach A).
- The new password follows the registration rule (at least 6 characters) and must differ from the current one.

**Out of scope:**
- "Forgot password" / reset by email (there is no email infrastructure).
- Password-strength meters or rules beyond the registration minimum.
- A separate "sign out all sessions" button.
- Lockout for the password step of normal login (unchanged; predates this feature).

---

## 2. Data Model

New optional field on each user record:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `token_version` | int | `0` | Bumped by 1 on every password change; tokens carrying an older version are rejected |

A missing field counts as 0, so existing `data.json` files need no migration.

---

## 3. Tokens and the Auth Check (`auth.py`, `main.py`)

- **Access tokens** carry a `ver` claim equal to the user's `token_version` at issue time. `main._access_token_for(user)` adds `"ver": user.get("token_version", 0)`.
- **2FA challenge tokens** also carry `ver`: `create_mfa_token(username, user_id, token_version=0)`. `POST /api/auth/login` passes `user.get("token_version", 0)` when it issues one.
- **Tokens issued before this feature** have no `ver`, which counts as 0. Every existing session therefore stays valid until that user's first password change.
- **New `auth.decode_access_token(token) -> Optional[dict]`.** It returns the access-token payload (same signature, expiry and `type` allowlist rules as today), or `None`. `decode_token(token)` stays as a thin wrapper returning `payload["sub"]`, so its existing callers and tests are unaffected.
- **`auth.get_current_user`** (the dependency behind every authenticated endpoint) now:
  1. decodes with `decode_access_token`; failure → 401 "Could not validate credentials" (unchanged);
  2. loads the user with `db.get_user_by_username(payload["sub"])`;
  3. if the user is missing, or `payload.get("ver", 0) != user.get("token_version", 0)`, → the same 401;
  4. returns the username, as today.

  A token for a user who no longer exists now gets 401 here, where some endpoints used to return 404 later. `auth.py` importing `database` creates no import cycle (`database` imports only `config`).
- **`POST /api/auth/login/2fa`:** after decoding the challenge token and loading the user, if `payload.get("ver", 0) != user.get("token_version", 0)`, return 401 "Invalid or expired login session". A login started with the old password cannot be completed after the change.

---

## 4. Endpoint: `POST /api/auth/password`

Authenticated, via `get_current_user_record`. Request model `PasswordChange`:

| Field | Rule |
|---|---|
| `current_password` | `str`, required |
| `new_password` | `str`, `min_length=6` (shorter → 422) |
| `code` | `Optional[str]`, `max_length=64`, default `None` |

The steps run in this order. Every error is **400, never 401** (the frontend treats any 401 outside `/api/auth/login*` as "session expired" and logs the user out), apart from the lockout's 429.

1. `user = db.get_user_by_id(user["id"])`: re-read inside the body. The dependency runs in a worker thread before the async body, so under concurrent requests its copy can be stale.
2. `two_factor.is_locked(user, now)` → 429 via `_too_many_attempts` ("Too many attempts. Try again in N minutes.").
3. `verify_password(current_password, hashed_password)` fails → persist `two_factor.record_failure(user, now)`, then 400 "Incorrect password".
4. `verify_password(new_password, hashed_password)` succeeds → 400 "New password must be different from the current password". Using `verify_password` handles bcrypt's 72-byte truncation consistently. This check comes before step 5, so a backup code is never used up by a request that would fail anyway.
5. If `user.get("totp_enabled")`:
   - `code` missing or empty → 400 "Authentication code required". This does **not** count as a failure.
   - Otherwise run `two_factor.verify_second_factor(user, code, now)`. On failure, persist its updates (which count toward the lockout) and return 400 "Invalid authentication code". On success, keep its updates: the used TOTP step or the consumed backup code, plus the reset counters.

   When 2FA is off, any `code` sent is ignored.
6. Success: `db.update_user(user["id"], {...2FA updates, "hashed_password": get_password_hash(new_password), "token_version": user.get("token_version", 0) + 1, "totp_failed_attempts": 0, "totp_locked_until": None})`, then return a `Token` built from the **updated** user (`_access_token_for(updated_user)`). Use `response_model=Token, response_model_exclude_none=True`, so the body is `{access_token, token_type: "bearer", mfa_required: false}`.

The lockout fields keep their `totp_` names and live on users without 2FA too. For those users they only throttle this endpoint and `POST /api/auth/2fa/enable` (which also requires the password), because the normal login has no password lockout. Enabling 2FA later resets them (enable writes `DISABLED_FIELDS` first).

---

## 5. Frontend

- **`api.js`:** `authAPI.changePassword({ current_password, new_password, code })` → `POST /api/auth/password`.
- **`AuthContext.jsx`:** add `replaceToken(accessToken)`, which calls `localStorage.setItem('token', accessToken)`. Expose it in the provider value. The user object is unchanged.
- **`pages/Security.jsx`:** a new **"Change password"** card rendered above the 2FA card, with the same `card max-w-3xl` styling.
  - **Fields:**
    - Current password (`autoComplete="current-password"`)
    - New password (`autoComplete="new-password"`), with the hint "At least 6 characters"
    - Confirm new password (`autoComplete="new-password"`)
    - "Authentication or backup code" (`autoComplete="one-time-code"`, `maxLength={20}`), only when `status?.enabled` is true
  - **Client-side checks before sending**, each shown as an inline error with nothing sent:
    - new password shorter than 6 characters → "New password must be at least 6 characters"
    - confirmation differs → "New passwords do not match"
    - new equals current → "New password must be different from the current password"
  - **Submit:**
    - the button shows "Changing…" and is disabled while busy;
    - on success: call `replaceToken(res.data.access_token)`, clear all fields, and show a green `role="status"` message: "Password changed. You've been signed out on your other devices.";
    - on error: show the server's string `detail` inline (`role="alert"`, falling back to a fixed message), and clear the code field.
  - **Other browsers** get a 401 on their next request, and the existing interceptor sends them to `/login`.
- **Styling:** existing Tailwind component classes (`card`, `input`, `label`, `btn-primary`) with `dark:` variants.

---

## 6. Testing

**Backend (pytest, written test-first).** A new `backend/tests/test_change_password.py`, reusing the `client`, `auth_headers` and `clock` fixtures and `tests/totp_helpers.py`:
- **Success:**
  - the response includes a new `access_token`, which works on `/api/auth/me`;
  - the **old token** gets 401 on `/api/auth/me`;
  - login works with the new password and fails (401) with the old one.
- **Rejections** (and the password is unchanged afterwards):
  - wrong current password → 400 "Incorrect password";
  - new password equal to the current one → 400;
  - new password of 5 characters → 422.
- **Lockout:** 5 wrong current passwords, then the correct one → 429.
- **2FA user** (enabled via `/api/auth/2fa/setup` + `/enable`):
  - no code → 400 "Authentication code required", and it does not count toward the lockout;
  - wrong code → 400;
  - a backup code succeeds and the remaining count drops by 1;
  - the TOTP step used at enrollment can't be replayed here.
- **Token versions:**
  - a 2FA challenge token issued before the change → `/api/auth/login/2fa` returns 401 "Invalid or expired login session";
  - a token without `ver` (made with `auth.create_access_token({"sub": ..., "user_id": ...})`) still works for a user whose `token_version` is missing;
  - the same kind of token is rejected after that user changes their password;
  - a token for a username that doesn't exist → 401.
- **Concurrency:** 30 parallel requests with a wrong current password → exactly 5×400 and 25×429, using the `httpx.ASGITransport` pattern from `test_two_factor_manage.py`.
- **Regression:** all 63 existing tests still pass. They cover every endpoint through the changed `get_current_user`.

**Frontend (manual, in the browser, against the backend):**
- Change the password in tab A; tab B's next action lands on `/login`, while tab A stays logged in.
- Each client-side check shows inline; a wrong current password shows the server's error inline without logging you out.
- The code field appears only when 2FA is on, and a 2FA user can change their password with a code.
- Check dark mode and a 375 px layout.

**Build:** `npm run build` passes.

---

## 7. Docs & Rollout

- **README:**
  - add `POST /api/auth/password` ("Change your password; signs out other sessions") to the Authentication API table;
  - add a "Change Password" bullet under Core Features.
- **No migration:** a missing `token_version` and a missing `ver` both count as 0, so nobody is logged out when this ships.
- **Dependencies:** none new.
