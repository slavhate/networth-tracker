from collections import Counter

import auth
import database as db
from api_helpers import enable_2fa, fire_concurrently
from totp_helpers import NOW_STEP, code_for, wrong_code

OLD = "secret123"  # password of the auth_headers fixture's user "tester"
NEW = "n3w-passw0rd"


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


def test_null_token_version_is_treated_as_zero(client, auth_headers, clock):
    # data.json is hand-edited for 2FA recovery, so a null token_version is plausible.
    user = db.get_user_by_username("tester")
    db.update_user(user["id"], {"token_version": None})
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 200
    resp = change(client, auth_headers, OLD, NEW)
    assert resp.status_code == 200
    assert auth.decode_access_token(resp.json()["access_token"])["ver"] == 1


def test_wrong_current_password_is_400_and_changes_nothing(client, auth_headers, clock):
    resp = change(client, auth_headers, "wrong-pass", NEW)
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
        assert change(client, auth_headers, "wrong-pass", NEW).status_code == 400
    locked = change(client, auth_headers, OLD, NEW)
    assert locked.status_code == 429
    assert locked.json()["detail"] == "Too many attempts. Try again in 15 minutes."
    assert login(client, OLD).status_code == 200


def test_concurrent_wrong_passwords_cannot_bypass_the_lockout(client, auth_headers, clock):
    attempt = ("/api/auth/password", auth_headers, {"current_password": "wrong-pass", "new_password": NEW})
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


def test_same_password_is_rejected_before_spending_a_backup_code(client, auth_headers, clock):
    _, codes = enable_2fa(client, auth_headers)
    resp = change(client, auth_headers, OLD, OLD, code=codes[0])
    assert resp.status_code == 400
    assert resp.json()["detail"] == "New password must be different from the current password"
    status = client.get("/api/auth/2fa/status", headers=auth_headers).json()
    assert status["backup_codes_remaining"] == 10


def test_2fa_challenge_started_before_the_change_cannot_finish(client, auth_headers, clock):
    secret, codes = enable_2fa(client, auth_headers)
    mfa_token = login(client, OLD).json()["mfa_token"]
    assert change(client, auth_headers, OLD, NEW, code=code_for(secret, NOW_STEP + 1)).status_code == 200
    resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": codes[0]})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"
