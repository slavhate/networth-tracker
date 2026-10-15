import os
import sys
import time

import pytest

from credentials import EMAIL, PASSWORD, USERNAME

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture(scope="session", autouse=True)
def non_utc_timezone():
    """Run every test off-UTC: pyotp treats naive datetimes as local time, so a missing UTC conversion
    only shows up when the machine's timezone is not UTC."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Kolkata"
    if hasattr(time, "tzset"):
        time.tzset()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    if hasattr(time, "tzset"):
        time.tzset()


@pytest.fixture(autouse=True)
def fresh_login_limits():
    """Every test starts with no failed logins counted (the limiter is in memory, and every test client shares
    one address) and no per-user locks bound to an earlier test's event loop."""
    import login_limiter
    import main

    login_limiter.clear()
    main._password_check_locks.clear()
    yield
    login_limiter.clear()


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
    client.post("/api/auth/register", json={"username": USERNAME, "password": PASSWORD, "email": EMAIL})
    resp = client.post("/api/auth/login", data={"username": USERNAME, "password": PASSWORD})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def clock(monkeypatch):
    """Freeze main._now() and the login limiter's clock; move time by assigning clock["now"]."""
    import login_limiter
    import main
    from totp_helpers import NOW

    state = {"now": NOW}
    monkeypatch.setattr(main, "_now", lambda: state["now"])
    monkeypatch.setattr(login_limiter, "_clock", lambda: state["now"].timestamp())
    return state


@pytest.fixture
def offline_markets(monkeypatch):
    """No network: stock prices and NAVs are unavailable and USD→INR is fixed at 80."""
    import exchange_service
    import nav_service
    import stock_service

    async def fixed_rate():
        return 80.0

    async def no_nav(fund_name):
        return None

    monkeypatch.setattr(exchange_service, "fetch_usd_to_inr", fixed_rate)
    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", no_nav)
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze valuation.today(); move it by assigning frozen_today["date"]."""
    from datetime import date

    import valuation

    state = {"date": date(2026, 10, 14)}
    monkeypatch.setattr(valuation, "today", lambda: state["date"])
    return state
