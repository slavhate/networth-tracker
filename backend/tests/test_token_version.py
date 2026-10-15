import auth
import database as db
import two_factor as tf
from credentials import OTHER_EMAIL, OTHER_USERNAME, PASSWORD, USERNAME
from totp_helpers import NOW_STEP, code_for


def me(client, token):
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})


def test_login_token_carries_version_zero_for_existing_users(client, auth_headers):
    token = auth_headers["Authorization"].split()[1]
    assert auth.decode_access_token(token)["ver"] == 0


def test_token_without_ver_works_for_users_without_token_version(client, auth_headers):
    user = db.get_user_by_username(USERNAME)
    assert "token_version" not in user
    legacy = auth.create_access_token({"sub": USERNAME, "user_id": user["id"]})
    assert me(client, legacy).status_code == 200


def test_token_with_stale_version_is_rejected(client, auth_headers):
    user = db.get_user_by_username(USERNAME)
    db.update_user(user["id"], {"token_version": 1})
    assert client.get("/api/auth/me", headers=auth_headers).status_code == 401
    fresh = client.post("/api/auth/login", data={"username": USERNAME, "password": PASSWORD}).json()["access_token"]
    assert auth.decode_access_token(fresh)["ver"] == 1
    assert me(client, fresh).status_code == 200


def test_stale_version_is_rejected_on_data_endpoints_too(client, auth_headers):
    user = db.get_user_by_username(USERNAME)
    db.update_user(user["id"], {"token_version": 1})
    assert client.get("/api/assets", headers=auth_headers).status_code == 401


def test_token_for_unknown_user_is_rejected(client):
    ghost = auth.create_access_token({"sub": "ghost", "user_id": "nope"})
    assert me(client, ghost).status_code == 401


def test_mfa_challenge_with_stale_version_cannot_complete_login(client, clock):
    client.post("/api/auth/register", json={"username": OTHER_USERNAME, "password": PASSWORD, "email": OTHER_EMAIL})
    user = db.get_user_by_username(OTHER_USERNAME)
    secret = tf.generate_secret()
    db.update_user(user["id"], {"totp_enabled": True, "totp_secret": secret})
    mfa_token = client.post("/api/auth/login", data={"username": OTHER_USERNAME, "password": PASSWORD}).json()["mfa_token"]
    db.update_user(user["id"], {"token_version": 1})
    resp = client.post("/api/auth/login/2fa", json={"mfa_token": mfa_token, "code": code_for(secret, NOW_STEP)})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired login session"
