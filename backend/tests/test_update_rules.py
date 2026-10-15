import json

import pytest

pytestmark = pytest.mark.usefixtures("offline_markets")

CREATE = {
    "assets": {"name": "Flat", "value": 100, "category": "real_estate"},
    "liabilities": {"name": "Loan", "amount": 50, "category": "personal_loan", "interest_rate": 9},
    "bank-accounts": {"bank_name": "HDFC", "account_number": "12345678", "account_type": "savings", "balance": 10},
    "equities": {"symbol": "KO", "market": "NYSE", "quantity": 5, "avg_buy_price": 60},
}


@pytest.mark.parametrize("resource, bad_update", [
    ("assets", {"name": ""}),
    ("liabilities", {"interest_rate": 150}),
    ("bank-accounts", {"account_number": "123"}),
    ("equities", {"quantity": 0}),
])
def test_update_enforces_the_same_rules_as_create(client, auth_headers, resource, bad_update):
    created = client.post(f"/api/{resource}", headers=auth_headers, json=CREATE[resource])
    assert created.status_code == 201, created.text
    path = f"/api/{resource}/{created.json()['id']}"
    before = client.get(path, headers=auth_headers).json()

    resp = client.put(path, headers=auth_headers, json=bad_update)

    assert resp.status_code == 422
    assert client.get(path, headers=auth_headers).json() == before


def test_a_valid_edit_survives_export_and_restore(client, auth_headers):
    asset = client.post("/api/assets", headers=auth_headers, json=CREATE["assets"]).json()
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"name": "Bigger flat", "value": 250})
    assert resp.status_code == 200, resp.text
    before = client.get("/api/export", headers=auth_headers).json()

    restored = client.post("/api/restore", headers=auth_headers,
                           files={"file": ("backup.json", json.dumps(before).encode("utf-8"), "application/json")})

    assert restored.status_code == 200, restored.text
    after = client.get("/api/export", headers=auth_headers).json()
    assert [(a["name"], a["value"]) for a in after["assets"]] == [("Bigger flat", 250)]
    assert [(a["name"], a["value"]) for a in before["assets"]] == [("Bigger flat", 250)]
