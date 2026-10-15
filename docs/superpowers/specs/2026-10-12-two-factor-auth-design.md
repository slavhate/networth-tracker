# Two-Factor Authentication (TOTP) — Design Spec

**Date:** 2026-10-12
**Branch:** `feat/2fa-login`
**Context:** Self-hosted personal finance app; users stored in `data/data.json`; JWT auth; no email/SMS infrastructure.

---

## 1. Goal

A user who turns on 2FA cannot obtain an access token with only their password. Users who have not turned it on log in exactly as they do today.

**Decisions (agreed):**
- Second factor: authenticator app (TOTP, RFC 6238). No email/SMS.
- Opt-in per user, from a new Security page. Not enforceable globally.
- Recovery: 10 one-time backup codes shown once at enrollment.
- Login flow: two-step, with a short-lived challenge token (`mfa_token`).

**Out of scope:**
- Regenerating backup codes without re-enrolling (disable + enable issues a fresh set).
- Revoking already-issued access tokens when 2FA is enabled (no revocation mechanism exists; tokens expire within 24 h).
- Global "require 2FA" switch, email/SMS OTP, WebAuthn.
- Frontend unit-test framework.

---

## 2. Data Model

New optional fields on each object in `data["users"]`. A missing field means its default, so existing `data.json` files need no migration.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `totp_enabled` | bool | `false` | 2FA is active for login |
| `totp_secret` | str \| null | `null` | Confirmed base32 secret |
| `totp_pending_secret` | str \| null | `null` | Secret issued by setup, not yet confirmed |
| `totp_last_used_step` | int \| null | `null` | Last accepted 30 s time step (replay protection) |
| `backup_code_hashes` | list[str] | `[]` | SHA-256 hex of each unused backup code |
| `totp_failed_attempts` | int | `0` | Consecutive failed second-factor attempts |
| `totp_locked_until` | ISO str \| null | `null` | UTC time until which verification is refused |

The TOTP secret is stored in plaintext, alongside the password hashes. Encrypting it with `SECRET_KEY` was rejected. Anyone who can read `data.json` already has all of the financial data. Also, when `SECRET_KEY` is unset it is regenerated on every restart, which would make encrypted secrets unreadable.

`/api/export` exports financial collections only, never the user record, so 2FA material never appears in backups.

**`database.py`:** add `update_user(user_id: str, updates: Dict) -> Optional[Dict]`. Unlike the other `update_*` helpers, it applies **every** key, including `None` values, so fields can be cleared. It returns the updated user, or `None` if the user is not found.

---

## 3. Backend Module: `backend/two_factor.py`

Pure functions, with no I/O. Every time-dependent function takes `now: datetime` (naive UTC) so tests are deterministic. Before calling pyotp, `now` is converted to an aware UTC datetime, because pyotp interprets a naive datetime as the server's *local* time. New dependency: `pyotp==2.9.0`.

| Function | Behaviour |
|---|---|
| `generate_secret() -> str` | `pyotp.random_base32()` (32 chars) |
| `provisioning_uri(secret, username) -> str` | `otpauth://` URI, issuer `"NetWorth Tracker"` |
| `verify_totp(secret, code, last_used_step, now) -> Optional[int]` | Applies `normalize_code(code)` and returns `None` unless the result is exactly 6 digits. Then checks steps `current-1`, `current`, `current+1`. Returns the matching step only if it is `> last_used_step` (or `last_used_step` is `None`). Uses `hmac.compare_digest`. Otherwise returns `None`. |
| `generate_backup_codes(n=10) -> List[str]` | `n` unique codes, 8 chars from the lowercase base32 alphabet `a-z2-7` (40 bits), formatted `xxxx-xxxx` |
| `normalize_code(code) -> str` | Strip whitespace and `-`, lowercase |
| `hash_backup_code(code) -> str` | SHA-256 hex of `normalize_code(code)` |
| `consume_backup_code(hashes, code) -> Optional[List[str]]` | If the hash matches one entry (constant-time compare), returns the list without it. Otherwise returns `None`. |
| `is_locked(user, now) -> bool` | `totp_locked_until` is set and `> now` |
| `lock_minutes_remaining(user, now) -> int` | Minutes until unlock, rounded up, minimum 1 (for the 429 message) |
| `record_failure(user, now) -> Dict` | The failure-counter updates described below. Also used for a wrong password on disable. |
| `verify_second_factor(user, code, now) -> Tuple[bool, Dict]` | See below |
| `DISABLED_FIELDS` | Dict of every 2FA field mapped to its default (section 2). Written on disable. |

**`verify_second_factor`** decides and returns `(ok, updates)`, where `updates` is the dict of user fields to persist. The caller persists them and acts on `ok`. It never checks the lock; callers check `is_locked` first.
- Normalized code is 6 digits → TOTP path against `totp_secret`. On success, `updates` sets `totp_last_used_step`.
- Normalized code is 8 chars → backup-code path. On success, `updates` sets `backup_code_hashes` to the reduced list.
- Any other shape counts as a failure.
- Success → `updates` also sets `totp_failed_attempts=0` and `totp_locked_until=None`.
- Failure → `totp_failed_attempts += 1`. When that reaches **5**, `updates` sets `totp_locked_until = now + 15 min` and resets `totp_failed_attempts=0`.

Constants: `MAX_FAILED_ATTEMPTS = 5`, `LOCKOUT_MINUTES = 15`, `BACKUP_CODE_COUNT = 10`, `ISSUER = "NetWorth Tracker"`.

---

## 4. Auth Changes: `auth.py`, `config.py`, `models.py`

- `config.Settings`: add `MFA_TOKEN_EXPIRE_MINUTES: int = 5`.
- `auth.create_mfa_token(username, user_id) -> str`: JWT with `{"sub", "user_id", "type": "mfa", "exp": now + MFA_TOKEN_EXPIRE_MINUTES}`.
- `auth.decode_mfa_token(token) -> Optional[dict]`: returns the payload only if the signature and expiry are valid and `type == "mfa"`.
- `auth.decode_token`: returns `None` when `payload.get("type") == "mfa"`, so challenge tokens are never accepted as access tokens. Existing access tokens have no `type` claim and stay valid.
- `models.Token`: `access_token` becomes `Optional[str] = None`; add `mfa_required: bool = False` and `mfa_token: Optional[str] = None`. The 2FA-off response serializes the same fields as before plus `mfa_required: false`.
- New request models: `MfaLoginRequest {mfa_token: str, code: str}`, `TwoFactorEnable {password: str, code: str}` (the password was added after the initial release; see §5.2), `TwoFactorDisable {password: str, code: str}`.
- New response models: `TwoFactorStatus {enabled: bool, backup_codes_remaining: int}`, `TwoFactorSetup {secret: str, otpauth_uri: str}`, `TwoFactorBackupCodes {backup_codes: List[str]}`.

`main.py` gets a module-level `def _now() -> datetime: return datetime.utcnow()`. Endpoints call `_now()`, and tests monkeypatch it.

---

## 5. API

### 5.1 Login

**`POST /api/auth/login`** (form, unchanged input)
- Wrong credentials → 401, as today.
- User without `totp_enabled` → `200 {access_token, token_type: "bearer", mfa_required: false}`, as today.
- User with `totp_enabled` → `200 {mfa_required: true, mfa_token, token_type: "mfa"}`, with no `access_token`.

**`POST /api/auth/login/2fa`** — body `MfaLoginRequest`
1. `decode_mfa_token` fails, or the user is missing or no longer has 2FA → 401 `"Invalid or expired login session"`.
2. `is_locked` → 429 `"Too many attempts. Try again in N minutes."` (N = remaining minutes, rounded up). The code is not checked.
3. `verify_second_factor` → persist `updates` via `db.update_user`.
   - Fail → 401 `"Invalid authentication code"`.
   - OK → 200 `Token` with an access token, identical to today's non-2FA login.

**Note:** Swagger's "Authorize" button keeps working for users without 2FA, but cannot complete a 2FA login. This is acceptable.

### 5.2 Management (all require `get_current_user`)

| Endpoint | Behaviour |
|---|---|
| `GET /api/auth/2fa/status` | `TwoFactorStatus` |
| `POST /api/auth/2fa/setup` | 400 `"Two-factor authentication is already enabled"` if enabled. Otherwise stores a fresh `totp_pending_secret` (replacing any earlier one) and returns `TwoFactorSetup`. |
| `POST /api/auth/2fa/enable` (`TwoFactorEnable`: `password`, `code`) | 400 if already enabled, 400 `"Start setup first"` if no pending secret. `is_locked` → 429. Wrong password → 400 `"Incorrect password"`, which counts as a failed attempt (`record_failure`); added after the initial release, so a stolen session can't enroll its own authenticator. `verify_totp(pending, code, None, now)` fails → 400 `"Invalid authentication code"` (does not count toward lockout). OK → set `totp_secret`=pending, `totp_pending_secret`=None, `totp_enabled`=True, `totp_last_used_step`=matched step, store hashes of 10 new codes. Returns `TwoFactorBackupCodes` with the plain codes; this is the only time they are ever returned. |
| `POST /api/auth/2fa/disable` (`TwoFactorDisable`) | 400 if not enabled. `is_locked` → 429. Wrong password → 400 `"Incorrect password"`, which counts as a failed attempt (`record_failure`). Then `verify_second_factor`; fail → persist updates, 400 `"Invalid authentication code"`. OK → write `DISABLED_FIELDS`. Returns 204. |

Errors from these authenticated endpoints are **400, never 401**. The frontend treats any 401 from a non-login endpoint as "session expired" and logs the user out.

Both login endpoints use `response_model_exclude_none=True`, so the 2FA-off login response is exactly `{access_token, token_type, mfa_required}`.

Request `code` fields are limited to `max_length=64`, so a longer code gets 422.

---

## 6. Frontend

### 6.1 `api.js`
- Response interceptor: do **not** redirect on 401 when `error.config.url` starts with `/api/auth/login`. The error propagates to the caller so it can show an inline message. This also fixes the wrong password message being lost to a page reload.
- `authAPI.verify2fa(mfaToken, code)` → `POST /api/auth/login/2fa`.
- `twoFactorAPI = { status, setup, enable(password, code), disable(password, code) }`.

### 6.2 `AuthContext.jsx`
- `login(credentials)`: if `response.data.mfa_required`, return `{ mfaRequired: true, mfaToken }` without touching storage. Otherwise behave as today and return `{ mfaRequired: false, user }`.
- New `completeMfaLogin(mfaToken, code)`: calls `verify2fa`, stores the token, loads `getMe`, sets the user.
- `register`: unchanged. Its `login` call returns `mfaRequired: false` for a new user.

### 6.3 `pages/Login.jsx`
- Step `credentials` (current form). On `mfaRequired`, switch to step `code`.
- Step `code`:
  - Heading "Two-factor authentication".
  - Numeric input (`inputMode="numeric"`, `autoComplete="one-time-code"`, `maxLength=6`, autofocus).
  - "Use a backup code instead" toggles to a text input (placeholder `xxxx-xxxx`).
  - "Back to sign in" returns to step `credentials` with the password field cleared.
  - Errors are shown inline. A 401 whose detail is `"Invalid or expired login session"` returns to step `credentials` with the message "Login session expired, please sign in again".

### 6.4 `pages/Security.jsx` (new) + routing
- Route `/security` inside `PrivateRoute`. Nav item `{ to: '/security', icon: ShieldCheck, label: 'Security' }` added last in `Layout.jsx` `navItems`.
- **Disabled state:** card explaining 2FA, with an "Enable two-factor authentication" button that calls `setup` and shows:
  - QR code via `qrcode.react` (`QRCodeSVG`, value=`otpauth_uri`, white background for scannability in dark mode).
  - The secret grouped in 4-char blocks, with a copy button.
  - Password input (autofocus) and code input, plus a "Verify & enable" button that stays disabled until both are filled.
  - "Cancel" returns to the initial state.
- **Backup-codes modal** (after a successful enable):
  - The 10 codes in a 2-column monospace grid.
  - "Copy all" and "Download .txt" (`networth-tracker-backup-codes.txt`) buttons.
  - Closes only via "I've saved these codes". There is no backdrop or Esc close.
- **Enabled state:**
  - "Enabled" badge.
  - "Backup codes remaining: N", highlighted amber when N ≤ 3 with the hint "Disable and re-enable 2FA to get a new set".
  - "Disable" form with password and code fields.
- Styling: existing Tailwind component classes (`card`, `input`, `label`, `btn-primary`) and dark-mode variants, as on the other pages.
- New dependency: `qrcode.react` (`^4.2.0`).

---

## 7. Testing

**Backend (pytest, written test-first):**
- `backend/requirements-dev.txt`: `-r requirements.txt`, `pytest==8.3.4`.
- `backend/tests/conftest.py`: `client` (TestClient against a temp `DATA_FILE`) and `auth_headers` fixtures, the same shapes as the `feat/zerodha-mf-import` branch. Expect a trivial add/add conflict on this file when both branches merge.
- `tests/test_two_factor.py` (unit):
  - TOTP accepts the current step and ±1 step, and rejects ±2.
  - A step `<= last_used_step` is rejected.
  - Backup codes: format, uniqueness, normalization (case, dash, spaces), single use.
  - `verify_second_factor` lockout on the 5th failure; counter reset on success.
- `tests/test_two_factor_api.py` (integration). Codes are generated with `pyotp.TOTP(secret).at(t)` and `main._now` is monkeypatched.
  - Login for a user without 2FA is unchanged (response has `access_token`).
  - setup → enable → a fresh `/api/auth/login` returns `mfa_required` → `/login/2fa` with TOTP returns a working access token.
  - The same login with a backup code works; reusing that backup code → 401.
  - Replaying the same TOTP step → 401.
  - `mfa_token` used as a Bearer token on `/api/auth/me` → 401.
  - Expired `mfa_token` → 401.
  - Five bad codes, then a correct one → 429; after 15 min (clock advanced) → 200.
  - Enable with a wrong code → 400 (not counted). Setup while enabled → 400. Enable without setup → 400.
  - Enable without a password → 422; with a wrong password → 400 and counted; five wrong passwords → 429; 30 concurrent wrong passwords → exactly 5×400 and 25×429.
  - Disable: wrong password → 400 and the session still works; wrong code → 400; both correct → 204 and every 2FA field is cleared; the next login returns `access_token` directly.
- **All backend tests run with `TZ=Asia/Kolkata`.** pyotp treats naive datetimes as local time, so the step-pinned tests only catch a missing UTC conversion on a machine whose zone isn't UTC.

**Frontend (manual, in the browser, against a local backend):**
- Enroll by scanning the QR code or entering the secret; confirm with your password and a code (a wrong password shows an inline error).
- Backup-codes modal: copy and download work.
- Log out, then log in with TOTP; log out, then log in with a backup code; the remaining count drops by one.
- A wrong code shows an inline error with no page reload. A wrong password also shows an inline error.
- Disable 2FA; the next login skips the code step.
- A user without 2FA logs in exactly as before. Check light and dark mode.

---

## 8. Docs & Rollout

- README:
  - "Two-Factor Authentication (TOTP)" bullet under Core Features.
  - New endpoints in the Authentication API table.
  - Recovery note: an operator can disable 2FA for a user by removing that user's `totp_*` and `backup_code_hashes` fields from `data/data.json` while the app is stopped.
- No migration. No change to Docker images beyond the new dependencies (`pyotp`, `qrcode.react`).
