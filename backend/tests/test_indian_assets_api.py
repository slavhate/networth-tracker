import json
from datetime import date

import pytest

pytestmark = pytest.mark.usefixtures("offline_markets")


def post(client, headers, body):
    resp = client.post("/api/assets", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


GOLD = {"name": "Test gold", "category": "gold", "value": 0, "quantity": 50, "unit_price": 10_000}
PPF = {"name": "Test PPF", "category": "ppf", "value": 0, "monthly_contribution": 10_000, "interest_rate": 7.1,
       "valuation_date": "2025-03-31"}


@pytest.mark.parametrize("category", ["epf", "ppf", "nps", "gold", "sgb", "bonds", "esop_rsu"])
def test_new_categories_are_accepted(client, auth_headers, frozen_today, category):
    asset = post(client, auth_headers, {"name": "Test asset", "category": category, "value": 1_000})
    assert asset["category"] == category and asset["current_value"] == 1_000


def test_quantity_times_price_becomes_the_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    assert asset["value"] == 500_000 and asset["current_value"] == 500_000


def test_a_sent_value_is_overridden_by_quantity_times_price(client, auth_headers, frozen_today):
    assert post(client, auth_headers, {**GOLD, "value": 1})["value"] == 500_000


def test_updating_the_price_recomputes_the_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"unit_price": 11_000})
    assert resp.status_code == 200 and resp.json()["value"] == 550_000


def test_quantity_times_price_above_the_maximum_is_rejected(client, auth_headers, frozen_today):
    resp = client.post("/api/assets", headers=auth_headers, json={**GOLD, "quantity": 1e12, "unit_price": 1e15})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Quantity × price is above the allowed maximum"
    assert client.get("/api/assets", headers=auth_headers).json() == []


def test_an_update_above_the_maximum_is_rejected_and_nothing_changes(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"quantity": 1e12, "unit_price": 1e15})
    assert resp.status_code == 422
    assert client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()["value"] == 500_000


def test_new_fields_can_be_cleared(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, PPF)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers,
                      json={"monthly_contribution": None, "interest_rate": None, "category": "cash"})
    body = resp.json()
    assert (body["monthly_contribution"], body["interest_rate"], body["category"]) == (None, None, "cash")


def test_a_provident_fund_gets_todays_date(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, {**PPF, "valuation_date": None})
    assert asset["valuation_date"] == "2026-10-14"


def test_list_and_dashboard_use_the_provident_fund_value(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 3, 31)
    post(client, auth_headers, PPF)
    [listed] = client.get("/api/assets", headers=auth_headers).json()
    assert listed["current_value"] == pytest.approx(124_615.00, abs=0.01)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert metrics["assets_by_category"]["ppf"] == pytest.approx(124_615.00, abs=0.01)


def test_old_categories_still_work(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, {"name": "Test fund", "category": "retirement", "value": 7_000})
    assert asset["current_value"] == 7_000


def test_export_and_restore_keep_the_new_fields(client, auth_headers, frozen_today):
    post(client, auth_headers, GOLD)
    post(client, auth_headers, PPF)
    backup = client.get("/api/export", headers=auth_headers).json()
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    by_name = {a["name"]: a for a in client.get("/api/assets", headers=auth_headers).json()}
    assert (by_name["Test gold"]["quantity"], by_name["Test gold"]["unit_price"]) == (50, 10_000)
    assert (by_name["Test PPF"]["monthly_contribution"], by_name["Test PPF"]["interest_rate"]) == (10_000, 7.1)


def restore(client, headers, backup):
    return client.post("/api/restore", headers=headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})


def test_restore_recomputes_a_quantity_holding_value(client, auth_headers, frozen_today):
    resp = restore(client, auth_headers, {"assets": [{**GOLD, "value": 1}]})
    assert resp.status_code == 200, resp.text
    [asset] = client.get("/api/assets", headers=auth_headers).json()
    assert asset["value"] == 500_000 and asset["current_value"] == 500_000


def test_restore_dates_an_undated_provident_fund(client, auth_headers, frozen_today):
    resp = restore(client, auth_headers, {"assets": [{**PPF, "valuation_date": None}]})
    assert resp.status_code == 200, resp.text
    [asset] = client.get("/api/assets", headers=auth_headers).json()
    assert asset["valuation_date"] == "2026-10-14"


def test_restore_above_the_maximum_is_rejected_and_nothing_changes(client, auth_headers, frozen_today):
    post(client, auth_headers, GOLD)
    before = client.get("/api/assets", headers=auth_headers).json()
    backup = {"assets": [{"name": "Test cash", "category": "cash", "value": 5},
                         {**GOLD, "quantity": 1e12, "unit_price": 1e15}]}

    resp = restore(client, auth_headers, backup)

    assert resp.status_code == 400
    assert resp.json()["detail"] == "assets[1]: Quantity × price is above the allowed maximum"
    assert client.get("/api/assets", headers=auth_headers).json() == before


def test_a_partial_update_above_the_maximum_changes_nothing(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    before = client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()

    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"unit_price": 1e15})

    assert resp.status_code == 422
    assert client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json() == before
