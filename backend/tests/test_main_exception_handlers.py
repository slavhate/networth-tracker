from fastapi.testclient import TestClient


def test_concurrent_write_error_returns_409(monkeypatch, tmp_path):
    from config import settings
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", False)

    import main
    import database as db

    client = TestClient(main.app)

    register_resp = client.post("/api/auth/register", json={
        "username": "conflictuser", "email": "c@example.com", "password": "pw12345"
    })
    assert register_resp.status_code == 201

    login_resp = client.post("/api/auth/login", data={"username": "conflictuser", "password": "pw12345"})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    def boom(*args, **kwargs):
        raise db.ConcurrentWriteError("simulated conflict")

    monkeypatch.setattr(db, "create_asset", boom)

    resp = client.post(
        "/api/assets",
        json={"name": "Test", "category": "cash", "value": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert resp.json() == {
        "detail": "This data changed elsewhere before your update was saved. Please refresh and try again."
    }
