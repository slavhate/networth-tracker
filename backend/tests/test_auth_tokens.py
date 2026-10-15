import pytest

import auth
import database as db
from config import settings
from credentials import EMAIL, USERNAME


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


def test_mfa_token_round_trips_through_decode_mfa_token():
    payload = auth.decode_mfa_token(auth.create_mfa_token(USERNAME, "u1"))
    assert payload["sub"] == USERNAME
    assert payload["user_id"] == "u1"
    assert payload["type"] == "mfa"


def test_mfa_token_is_not_an_access_token():
    assert auth.decode_token(auth.create_mfa_token(USERNAME, "u1")) is None


def test_access_token_is_not_an_mfa_token():
    access = auth.create_access_token({"sub": USERNAME, "user_id": "u1"})
    assert auth.decode_mfa_token(access) is None
    assert auth.decode_token(access) == USERNAME  # tokens issued before 2FA have no "type" claim


def test_decode_token_rejects_any_other_token_type():
    token = auth.create_access_token({"sub": USERNAME, "user_id": "u1", "type": "something-else"})
    assert auth.decode_token(token) is None


def test_expired_mfa_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MFA_TOKEN_EXPIRE_MINUTES", -1)
    assert auth.decode_mfa_token(auth.create_mfa_token(USERNAME, "u1")) is None


def test_decode_mfa_token_rejects_garbage():
    assert auth.decode_mfa_token("not-a-jwt") is None


def test_update_user_sets_and_clears_fields(data_file):
    user = db.create_user(USERNAME, EMAIL, "hash")
    db.update_user(user["id"], {"totp_secret": "ABC", "totp_enabled": True})
    assert db.get_user_by_id(user["id"])["totp_secret"] == "ABC"

    updated = db.update_user(user["id"], {"totp_secret": None})
    assert updated["totp_secret"] is None
    stored = db.get_user_by_id(user["id"])
    assert stored["totp_secret"] is None
    assert stored["totp_enabled"] is True


def test_update_user_unknown_id_returns_none(data_file):
    assert db.update_user("missing", {"totp_enabled": True}) is None


def test_decode_access_token_returns_the_payload():
    payload = auth.decode_access_token(auth.create_access_token({"sub": USERNAME, "user_id": "u1", "ver": 3}))
    assert payload["sub"] == USERNAME
    assert payload["ver"] == 3
    assert auth.decode_access_token(auth.create_mfa_token(USERNAME, "u1")) is None


def test_mfa_token_carries_the_token_version():
    assert auth.decode_mfa_token(auth.create_mfa_token(USERNAME, "u1", 4))["ver"] == 4
    assert auth.decode_mfa_token(auth.create_mfa_token(USERNAME, "u1"))["ver"] == 0
