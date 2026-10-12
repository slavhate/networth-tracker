from datetime import timedelta

import pytest

import database as db
import two_factor as tf
from config import settings
from totp_helpers import NOW, NOW_STEP, code_for, step_of, wrong_code

PASSWORD = "secret123"


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
    resp = client.post("/api/auth/login", data={"username": "alice", "password": "wrong-pass"})
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
