import pytest


@pytest.fixture
def local_backend(monkeypatch, tmp_path):
    from config import settings
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))
    import database as db
    yield db


def test_asset_crud_round_trip_on_local_backend(local_backend):
    db = local_backend
    user = db.create_user("localuser", "l@example.com", "hash")
    user_id = user["id"]

    created = db.create_asset(user_id, {"name": "Test", "category": "cash", "value": 500})
    assert db.get_assets_by_user(user_id) == [created]

    updated = db.update_asset(created["id"], user_id, {"value": 999})
    assert updated["value"] == 999

    assert db.delete_asset(created["id"], user_id) is True
    assert db.get_assets_by_user(user_id) == []


def test_duplicate_username_allowed_on_local_backend_matches_existing_behavior(local_backend):
    db = local_backend
    db.create_user("dup", "a@example.com", "hash1")
    # Local backend has no duplicate-username guard - this is pre-existing
    # behavior, unchanged by this migration, unlike the S3 backend which
    # rejects duplicates. Creating again just appends another user row.
    db.create_user("dup", "b@example.com", "hash2")
    data = db._load_local_data()
    matching = [u for u in data["users"] if u["username"] == "dup"]
    assert len(matching) == 2
