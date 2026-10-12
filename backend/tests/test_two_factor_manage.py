from collections import Counter

import database as db
import two_factor as tf
from api_helpers import enable_2fa, fire_concurrently
from totp_helpers import NOW_STEP, code_for, wrong_code

PASSWORD = "secret123"  # password of the auth_headers fixture's user "tester"


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
    resp = disable(client, auth_headers, "wrong-pass", code_for(secret, NOW_STEP + 1))
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
        assert disable(client, auth_headers, "wrong-pass", "123456").status_code == 400
    assert disable(client, auth_headers, PASSWORD, code_for(secret, NOW_STEP + 1)).status_code == 429


def test_concurrent_disable_attempts_cannot_bypass_the_lockout(client, auth_headers, clock):
    secret, _ = enable_2fa(client, auth_headers)
    attempt = ("/api/auth/2fa/disable", auth_headers, {"password": PASSWORD, "code": wrong_code(secret, NOW_STEP + 1)})
    statuses = Counter(r.status_code for r in fire_concurrently([attempt] * 30))
    assert statuses == {400: 5, 429: 25}
    assert client.get("/api/auth/2fa/status", headers=auth_headers).json()["enabled"] is True


def test_concurrent_enable_succeeds_only_once(client, auth_headers, clock):
    setup = client.post("/api/auth/2fa/setup", headers=auth_headers).json()
    attempt = ("/api/auth/2fa/enable", auth_headers, {"code": code_for(setup["secret"], NOW_STEP)})
    statuses = Counter(r.status_code for r in fire_concurrently([attempt] * 10))
    assert statuses == {200: 1, 400: 9}
