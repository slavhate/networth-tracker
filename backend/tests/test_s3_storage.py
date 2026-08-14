import pytest

import s3_storage


def test_load_user_data_returns_empty_shape_when_missing(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    assert data["user"] is None
    assert data["assets"] == []
    assert data["_etag"] is None


def test_save_then_load_round_trips(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    data["user"] = {"id": "user-1", "username": "demo"}
    data["assets"].append({"id": "a1", "value": 100})
    s3_storage.save_user_data("user-1", data)

    reloaded = s3_storage.load_user_data("user-1")
    assert reloaded["user"] == {"id": "user-1", "username": "demo"}
    assert reloaded["assets"] == [{"id": "a1", "value": 100}]
    assert reloaded["_etag"] is not None


def test_save_user_data_conflict_raises(s3_bucket):
    data = s3_storage.load_user_data("user-1")
    s3_storage.save_user_data("user-1", data)  # first write (IfNoneMatch) succeeds

    stale_copy = s3_storage.load_user_data("user-1")
    fresh_copy = s3_storage.load_user_data("user-1")

    stale_copy["assets"].append({"id": "a1"})
    s3_storage.save_user_data("user-1", stale_copy)  # succeeds; object's etag moves on

    fresh_copy["assets"].append({"id": "a2"})
    with pytest.raises(s3_storage.ConflictError):
        s3_storage.save_user_data("user-1", fresh_copy)


def test_lookup_user_id_returns_none_when_absent(s3_bucket):
    assert s3_storage.lookup_user_id("nobody") is None


def test_register_username_claims_and_rejects_duplicate(s3_bucket):
    assert s3_storage.register_username("alice", "user-1") is True
    assert s3_storage.lookup_user_id("alice") == "user-1"
    assert s3_storage.register_username("alice", "user-2") is False
