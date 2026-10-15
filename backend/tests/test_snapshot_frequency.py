"""How often the dashboard saves an automatic snapshot: weekly, every 2 weeks, monthly or quarterly."""
from datetime import date

import pytest

import valuation
from credentials import OTHER_EMAIL, OTHER_PASSWORD, OTHER_USERNAME


def ts(*days):
    return [f"{d}T00:00:00" for d in days]


@pytest.mark.parametrize("frequency, taken, on, expected", [
    ("weekly", [], date(2026, 10, 15), date(2026, 10, 15)),
    ("weekly", ts("2026-10-08"), date(2026, 10, 15), date(2026, 10, 15)),        # 7 days old: due
    ("weekly", ts("2026-10-09"), date(2026, 10, 15), date(2026, 10, 16)),        # 6 days old: tomorrow
    ("fortnightly", ts("2026-10-02"), date(2026, 10, 15), date(2026, 10, 16)),   # 13 days old
    ("fortnightly", ts("2026-10-01"), date(2026, 10, 15), date(2026, 10, 15)),   # 14 days old
    ("monthly", ts("2026-09-30"), date(2026, 10, 15), date(2026, 10, 15)),
    ("monthly", ts("2026-10-01"), date(2026, 10, 15), date(2026, 11, 1)),
    ("monthly", ts("2026-12-03"), date(2026, 12, 20), date(2027, 1, 1)),
    ("quarterly", ts("2026-03-31"), date(2026, 4, 1), date(2026, 4, 1)),         # a new quarter
    ("quarterly", ts("2026-04-01"), date(2026, 6, 30), date(2026, 7, 1)),
    ("quarterly", ts("2026-11-15"), date(2026, 12, 31), date(2027, 1, 1)),
    ("unknown", ts("2026-10-01"), date(2026, 10, 15), date(2026, 11, 1)),        # treated as monthly
])
def test_next_snapshot_date(frequency, taken, on, expected):
    assert valuation.next_snapshot_date(frequency, taken, on) == expected
    assert valuation.snapshot_due(frequency, taken, on) == (expected == on)


def test_future_snapshots_do_not_count():
    assert valuation.snapshot_due("weekly", ts("2026-10-20"), date(2026, 10, 15))


def settings(client, headers):
    return client.get("/api/settings/snapshots", headers=headers)


def test_default_is_monthly(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 10, 15)
    assert settings(client, auth_headers).json() == {"frequency": "monthly", "next_snapshot_on": "2026-10-15"}


def test_frequency_can_be_changed(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 10, 15)
    resp = client.put("/api/settings/snapshots", json={"frequency": "weekly"}, headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["frequency"] == "weekly"
    assert settings(client, auth_headers).json()["frequency"] == "weekly"


@pytest.mark.parametrize("bad", [{"frequency": "daily"}, {"frequency": ""}, {}])
def test_unknown_frequency_is_rejected(client, auth_headers, bad):
    assert client.put("/api/settings/snapshots", json=bad, headers=auth_headers).status_code == 422


def test_each_user_has_their_own_frequency(client, auth_headers):
    client.put("/api/settings/snapshots", json={"frequency": "quarterly"}, headers=auth_headers)
    client.post("/api/auth/register", json={"username": OTHER_USERNAME, "password": OTHER_PASSWORD,
                                            "email": OTHER_EMAIL})
    token = client.post("/api/auth/login", data={"username": OTHER_USERNAME, "password": OTHER_PASSWORD}).json()
    other = {"Authorization": f"Bearer {token['access_token']}"}
    assert settings(client, other).json()["frequency"] == "monthly"


def test_settings_need_login(client):
    assert client.get("/api/settings/snapshots").status_code == 401
    assert client.put("/api/settings/snapshots", json={"frequency": "weekly"}).status_code == 401


def test_dashboard_takes_weekly_snapshots(client, auth_headers, frozen_today):
    client.post("/api/assets", json={"name": "Cash", "category": "cash", "value": 1000}, headers=auth_headers)
    client.put("/api/settings/snapshots", json={"frequency": "weekly"}, headers=auth_headers)
    frozen_today["date"] = date(2026, 10, 1)
    first = client.get("/api/dashboard", headers=auth_headers).json()
    assert len(first["net_worth_history"]) == 1
    assert (first["snapshot_frequency"], first["next_snapshot_on"]) == ("weekly", "2026-10-08")
    frozen_today["date"] = date(2026, 10, 7)  # 6 days later: not yet
    assert len(client.get("/api/dashboard", headers=auth_headers).json()["net_worth_history"]) == 1
    frozen_today["date"] = date(2026, 10, 8)  # 7 days later: due
    assert len(client.get("/api/dashboard", headers=auth_headers).json()["net_worth_history"]) == 2


def test_dashboard_reports_the_next_monthly_snapshot(client, auth_headers, frozen_today):
    client.post("/api/assets", json={"name": "Cash", "category": "cash", "value": 1000}, headers=auth_headers)
    frozen_today["date"] = date(2026, 10, 15)
    body = client.get("/api/dashboard", headers=auth_headers).json()
    assert (body["snapshot_frequency"], body["next_snapshot_on"]) == ("monthly", "2026-11-01")
