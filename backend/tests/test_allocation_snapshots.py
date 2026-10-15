import json
import logging
from datetime import date

import pytest

import database as db
from credentials import USERNAME

pytestmark = pytest.mark.usefixtures("offline_markets")


def add_asset(client, headers, **body):
    resp = client.post("/api/assets", headers=headers, json={"name": "Test asset", "category": "cash", "value": 1000, **body})
    assert resp.status_code == 201, resp.text


def snapshots(client, headers):
    return client.get("/api/export", headers=headers).json()["snapshots"]


def test_dashboard_reports_assets_by_class(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    add_asset(client, auth_headers, category="gold", value=500)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert metrics["assets_by_class"] == {"gold": 500, "cash": 1000}


def test_a_manual_snapshot_stores_the_breakdown(client, auth_headers, frozen_today):
    add_asset(client, auth_headers, category="ppf", value=2000)
    snapshot = client.post("/api/snapshot", headers=auth_headers).json()
    assert snapshot["assets_by_class"] == {"debt": 2000}
    assert snapshot["assets_by_category"] == {"ppf": 2000}
    assert snapshot["liabilities_by_category"] == {}


def test_the_first_dashboard_visit_each_month_saves_one_snapshot(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    client.get("/api/dashboard", headers=auth_headers)
    client.get("/api/dashboard", headers=auth_headers)
    [first] = snapshots(client, auth_headers)
    assert first["timestamp"] == "2026-10-14T00:00:00"
    assert first["assets_by_class"] == {"cash": 1000}

    frozen_today["date"] = date(2026, 11, 2)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert sorted(s["timestamp"] for s in snapshots(client, auth_headers)) == ["2026-10-14T00:00:00", "2026-11-02T00:00:00"]
    assert metrics["net_worth_history"][0]["timestamp"] == "2026-11-02T00:00:00"


def test_a_manual_snapshot_this_month_stops_the_automatic_one(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    frozen_today["date"] = date(2026, 10, 5)
    client.post("/api/snapshot", headers=auth_headers)
    frozen_today["date"] = date(2026, 10, 20)
    client.get("/api/dashboard", headers=auth_headers)
    [only] = snapshots(client, auth_headers)
    assert only["timestamp"].startswith("2026-10-05T")


def test_a_manual_snapshot_is_dated_by_the_app_clock(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    frozen_today["date"] = date(2026, 3, 9)
    snapshot = client.post("/api/snapshot", headers=auth_headers).json()
    assert snapshot["timestamp"].startswith("2026-03-09T")
    client.get("/api/dashboard", headers=auth_headers)
    assert len(snapshots(client, auth_headers)) == 1


def test_a_failed_automatic_snapshot_write_does_not_break_the_dashboard(client, auth_headers, frozen_today, monkeypatch, caplog):
    add_asset(client, auth_headers)

    def failing_save(data):
        raise OSError("disk full")

    with monkeypatch.context() as patched, caplog.at_level(logging.WARNING):
        patched.setattr(db, "save_data", failing_save)
        resp = client.get("/api/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total_assets"] == 1000
    assert "snapshot" in caplog.text.lower()
    assert snapshots(client, auth_headers) == []


def test_the_dashboard_history_is_not_capped(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    user_id = db.get_user_by_username(USERNAME)["id"]
    for i in range(34):
        db.create_snapshot(user_id, 100 + i, 0, timestamp=f"{2023 + i // 12}-{i % 12 + 1:02d}-01T00:00:00")
    db.create_snapshot(user_id, 500, 0, timestamp="2026-10-01T00:00:00")
    history = client.get("/api/dashboard", headers=auth_headers).json()["net_worth_history"]
    assert len(history) == 35


def test_an_empty_account_gets_no_automatic_snapshot(client, auth_headers, frozen_today):
    client.get("/api/dashboard", headers=auth_headers)
    assert snapshots(client, auth_headers) == []


def test_export_and_restore_keep_the_breakdown(client, auth_headers, frozen_today):
    add_asset(client, auth_headers, category="gold", value=500)
    client.get("/api/dashboard", headers=auth_headers)
    backup = client.get("/api/export", headers=auth_headers).json()
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    [restored] = snapshots(client, auth_headers)
    assert restored["assets_by_class"] == {"gold": 500}


def test_a_backup_without_breakdowns_still_restores(client, auth_headers, frozen_today):
    backup = {"snapshots": [{"total_assets": 10, "total_liabilities": 0, "timestamp": "2025-01-01T00:00:00"}]}
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    [restored] = snapshots(client, auth_headers)
    assert "assets_by_class" not in restored or restored["assets_by_class"] is None


def restore_backup(client, headers, backup):
    return client.post("/api/restore", headers=headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})


@pytest.mark.parametrize("field", ["assets_by_class", "assets_by_category", "liabilities_by_category"])
@pytest.mark.parametrize("bad", [-1, "inf"])
def test_restore_rejects_bad_breakdown_values(client, auth_headers, frozen_today, field, bad):
    backup = {"snapshots": [{"total_assets": 10, "total_liabilities": 0, "timestamp": "2025-01-01T00:00:00",
                             field: {"cash": bad}}]}
    resp = restore_backup(client, auth_headers, backup)
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith(f"snapshots[0].{field}.cash: ")


def test_restore_keeps_only_the_breakdown_keys_a_backup_has(client, auth_headers, frozen_today):
    backup = {"snapshots": [{"total_assets": 10, "total_liabilities": 0, "timestamp": "2025-01-01T00:00:00",
                             "assets_by_class": {"cash": 10}}]}
    assert restore_backup(client, auth_headers, backup).status_code == 200
    [restored] = snapshots(client, auth_headers)
    assert restored["assets_by_class"] == {"cash": 10}
    assert "assets_by_category" not in restored
    assert "liabilities_by_category" not in restored


def test_a_liabilities_only_account_gets_an_automatic_snapshot(client, auth_headers, frozen_today):
    resp = client.post("/api/liabilities", headers=auth_headers,
                       json={"name": "Test loan", "amount": 5000, "category": "personal_loan"})
    assert resp.status_code == 201, resp.text
    client.get("/api/dashboard", headers=auth_headers)
    [only] = snapshots(client, auth_headers)
    assert only["total_assets"] == 0
    assert only["total_liabilities"] == 5000
    assert only["liabilities_by_category"] == {"personal_loan": 5000}


def test_the_dashboard_serializes_a_snapshot_without_a_breakdown(client, auth_headers, frozen_today):
    user_id = db.get_user_by_username(USERNAME)["id"]
    db.create_snapshot(user_id, 10, 0, timestamp="2025-01-01T00:00:00")
    resp = client.get("/api/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    [old] = resp.json()["net_worth_history"]
    assert old["total_assets"] == 10
    assert old.get("assets_by_class") is None
    assert old.get("assets_by_category") is None
    assert old.get("liabilities_by_category") is None


def test_a_new_calendar_month_gets_its_own_snapshot_across_new_year(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    frozen_today["date"] = date(2026, 12, 31)
    client.get("/api/dashboard", headers=auth_headers)
    assert [s["timestamp"] for s in snapshots(client, auth_headers)] == ["2026-12-31T00:00:00"]
    frozen_today["date"] = date(2027, 1, 1)
    client.get("/api/dashboard", headers=auth_headers)
    assert sorted(s["timestamp"] for s in snapshots(client, auth_headers)) == ["2026-12-31T00:00:00", "2027-01-01T00:00:00"]


def test_demo_user_gets_six_months_of_history(client, monkeypatch, frozen_today):
    import asyncio

    import main
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())
    demo = db.get_user_by_username(settings.DEMO_USERNAME)
    history = sorted(db.get_snapshots_by_user(demo["id"], limit=None), key=lambda s: s["timestamp"])
    assert [s["timestamp"][:7] for s in history] == ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    assert all(s["assets_by_class"] and s["total_assets"] > s["total_liabilities"] for s in history)
    # Each month's classes add up to that month's assets
    assert all(abs(sum(s["assets_by_class"].values()) - s["total_assets"]) <= 1 for s in history)

    # The newest synthetic month sits close to what the dashboard shows today (read before that visit adds its own snapshot)
    headers = {"Authorization": f"Bearer {main._access_token_for(demo).access_token}"}
    live = client.get("/api/dashboard", headers=headers).json()
    newest = history[-1]
    assert abs(newest["net_worth"] - live["net_worth"]) <= 0.1 * live["net_worth"]
    assert history[0]["net_worth"] < newest["net_worth"]
    # ...and the classes keep the live mix
    for name, value in live["assets_by_class"].items():
        assert abs(newest["assets_by_class"][name] / newest["total_assets"] - value / live["total_assets"]) < 0.01
