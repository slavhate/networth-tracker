import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient backed by a throwaway data file."""
    from fastapi.testclient import TestClient
    from config import settings
    import main

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))
    return TestClient(main.app)


@pytest.fixture
def auth_headers(client):
    client.post("/api/auth/register", json={"username": "tester", "password": "secret123", "email": "t@example.com"})
    resp = client.post("/api/auth/login", data={"username": "tester", "password": "secret123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def clock(monkeypatch):
    """Freeze main._now(); move time by assigning clock["now"]."""
    import main
    from totp_helpers import NOW

    state = {"now": NOW}
    monkeypatch.setattr(main, "_now", lambda: state["now"])
    return state
