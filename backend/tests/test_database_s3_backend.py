import pytest

import database as db


def test_create_and_fetch_user(s3_bucket):
    user = db.create_user("alice", "alice@example.com", "hashed-pw")
    assert user["username"] == "alice"

    fetched = db.get_user_by_username("alice")
    assert fetched == user


def test_duplicate_username_raises(s3_bucket):
    db.create_user("bob", "bob@example.com", "hashed-pw")
    with pytest.raises(ValueError):
        db.create_user("bob", "other@example.com", "other-hash")


def test_asset_crud_round_trip(s3_bucket):
    user = db.create_user("carol", "carol@example.com", "hashed-pw")
    user_id = user["id"]

    created = db.create_asset(user_id, {"name": "Emergency Fund", "category": "cash", "value": 1000})
    assert db.get_assets_by_user(user_id) == [created]

    updated = db.update_asset(created["id"], user_id, {"value": 2000})
    assert updated["value"] == 2000

    assert db.delete_asset(created["id"], user_id) is True
    assert db.get_assets_by_user(user_id) == []


def test_concurrent_write_conflict_surfaces_as_concurrent_write_error(s3_bucket):
    user = db.create_user("dave", "dave@example.com", "hashed-pw")
    user_id = user["id"]

    stale = db.load_data(user_id)
    fresh = db.load_data(user_id)

    stale["assets"].append({"id": "a1"})
    db.save_data(user_id, stale)

    fresh["assets"].append({"id": "a2"})
    with pytest.raises(db.ConcurrentWriteError):
        db.save_data(user_id, fresh)
