import json

import pytest

import database as db
from credentials import OTHER_EMAIL, OTHER_USERNAME, PASSWORD, USERNAME

pytestmark = pytest.mark.usefixtures("offline_markets")

CONTENT_SECTIONS = ("assets", "liabilities", "bank_accounts", "insurances", "mutual_funds", "equities", "snapshots")
SERVER_FIELDS = {"id", "user_id", "created_at", "updated_at"}


def restore(client, headers, backup):
    body = backup if isinstance(backup, bytes) else json.dumps(backup).encode("utf-8")
    return client.post("/api/restore", headers=headers, files={"file": ("backup.json", body, "application/json")})


def export(client, headers):
    resp = client.get("/api/export", headers=headers)
    assert resp.status_code == 200
    return resp.json()


def content(backup):
    """Section contents without server-assigned fields, in a stable order, for comparing two exports."""
    def strip(row):
        return {k: v for k, v in row.items() if k not in SERVER_FIELDS}

    out = {section: sorted((strip(r) for r in backup[section]), key=json.dumps) for section in CONTENT_SECTIONS}
    out["goal"] = strip(backup["goal"]) if backup["goal"] else None
    return out


def seed(client, headers):
    for path, body in [
        ("/api/assets", {"name": "Flat", "value": 5000000, "category": "real_estate"}),
        ("/api/liabilities", {"name": "Home loan", "amount": 2000000, "category": "mortgage", "interest_rate": 8.5}),
        ("/api/bank-accounts", {"bank_name": "HDFC", "account_number": "12345678", "account_type": "savings", "balance": 50000}),
        ("/api/insurances", {"policy_name": "Term", "provider": "HDFC Life", "insurance_type": "term",
                             "sum_assured": 10000000, "premium": 12000}),
        ("/api/mutual-funds", {"fund_name": "Index", "amc": "UTI", "category": "index", "invested_amount": 80000,
                               "units": 650, "current_nav": 141.5}),
        ("/api/equities", {"symbol": "KO", "market": "NYSE", "quantity": 10, "avg_buy_price": 60}),
        ("/api/snapshot", None),
        ("/api/goal", {"target_amount": 100000000, "name": "10 Cr"}),
    ]:
        resp = client.post(path, headers=headers, json=body)
        assert resp.status_code in (200, 201), (path, resp.text)


def login_as_other(client):
    client.post("/api/auth/register", json={"username": OTHER_USERNAME, "password": PASSWORD, "email": OTHER_EMAIL})
    token = client.post("/api/auth/login", data={"username": OTHER_USERNAME, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_restoring_your_own_export_round_trips(client, auth_headers):
    seed(client, auth_headers)
    before = export(client, auth_headers)

    resp = restore(client, auth_headers, before)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "success", "restored": {
        "assets": 1, "liabilities": 1, "bank_accounts": 1, "insurances": 1,
        "mutual_funds": 1, "equities": 1, "snapshots": 1, "goal": True,
    }}
    after = export(client, auth_headers)
    assert content(after) == content(before)
    assert {a["id"] for a in after["assets"]}.isdisjoint({a["id"] for a in before["assets"]})


def test_restoring_twice_does_not_duplicate(client, auth_headers):
    seed(client, auth_headers)
    backup = export(client, auth_headers)

    assert restore(client, auth_headers, backup).status_code == 200
    assert restore(client, auth_headers, backup).status_code == 200

    after = export(client, auth_headers)
    assert len(after["assets"]) == 1
    assert len(after["snapshots"]) == 1


def test_export_and_restore_keep_more_than_30_snapshots(client, auth_headers):
    user_id = db.get_user_by_username(USERNAME)["id"]
    for day in range(1, 36):
        db.create_snapshot(user_id, day, 0)
    backup = export(client, auth_headers)
    assert len(backup["snapshots"]) == 35

    resp = restore(client, auth_headers, backup)

    assert resp.status_code == 200, resp.text
    assert resp.json()["restored"]["snapshots"] == 35
    assert len(export(client, auth_headers)["snapshots"]) == 35


def test_goal_null_removes_the_goal(client, auth_headers):
    seed(client, auth_headers)

    resp = restore(client, auth_headers, {"assets": [], "goal": None})

    assert resp.status_code == 200
    assert export(client, auth_headers)["goal"] is None


def test_restore_leaves_other_users_alone(client, auth_headers):
    other = login_as_other(client)
    seed(client, other)
    before = export(client, other)

    assert restore(client, auth_headers, {"assets": []}).status_code == 200

    assert content(export(client, other)) == content(before)


def test_rejected_backup_changes_nothing(client, auth_headers):
    seed(client, auth_headers)
    before = export(client, auth_headers)

    resp = restore(client, auth_headers, {"assets": [
        {"name": "ok", "value": 1, "category": "cash"},
        {"name": "bad", "value": "lots", "category": "cash"},
    ]})

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("assets[1].value: ")
    assert content(export(client, auth_headers)) == content(before)


def test_restore_requires_login(client):
    assert restore(client, {}, {"assets": []}).status_code == 401


def test_old_import_endpoint_is_gone(client, auth_headers):
    resp = client.post("/api/import", headers=auth_headers, files={"file": ("b.json", b"{}", "application/json")})

    assert resp.status_code in (404, 405)


def test_export_date_carries_a_timezone(client, auth_headers):
    from datetime import datetime

    assert datetime.fromisoformat(export(client, auth_headers)["export_date"]).tzinfo is not None
