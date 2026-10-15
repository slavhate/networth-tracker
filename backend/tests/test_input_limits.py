import json

import pytest

pytestmark = pytest.mark.usefixtures("offline_markets")


@pytest.mark.parametrize("path, body", [
    ("/api/assets", {"name": "Test flat", "value": "inf", "category": "real_estate"}),
    ("/api/assets", {"name": "Test flat", "value": 2e15, "category": "real_estate"}),
    ("/api/liabilities", {"name": "Test loan", "amount": "NaN", "category": "mortgage"}),
    ("/api/bank-accounts", {"bank_name": "Test Bank", "account_number": "00001234",
                            "account_type": "savings", "balance": "-Infinity"}),
    ("/api/insurances", {"policy_name": "Test term", "provider": "Test Insurer", "insurance_type": "term",
                         "sum_assured": 2e15, "premium": 1}),
    ("/api/mutual-funds", {"fund_name": "Test index", "amc": "Test AMC", "category": "index",
                           "invested_amount": 1, "units": 2e12}),
    ("/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 2_000_000_000, "avg_buy_price": 1}),
    ("/api/goal", {"target_amount": "inf"}),
])
def test_writes_reject_non_finite_and_out_of_range_numbers(client, auth_headers, path, body):
    assert client.post(path, headers=auth_headers, json=body).status_code == 422


def test_updates_reject_non_finite_numbers_and_keep_the_row(client, auth_headers):
    asset = client.post("/api/assets", headers=auth_headers,
                        json={"name": "Test flat", "value": 100, "category": "real_estate"}).json()

    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"value": "inf"})

    assert resp.status_code == 422
    assert client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()["value"] == 100


def test_a_tiny_invested_amount_gives_zero_percent_instead_of_infinity(client, auth_headers):
    resp = client.post("/api/equities", headers=auth_headers,
                       json={"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1e-300})
    assert resp.status_code == 201
    equity = resp.json()

    resp = client.put(f"/api/equities/{equity['id']}", headers=auth_headers, json={"current_price": 1e15})

    assert resp.status_code == 200
    assert resp.json()["gain_loss_percent"] == 0
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200


def test_the_equities_summary_gives_zero_percent_for_a_tiny_total_invested(client, auth_headers):
    equity = client.post("/api/equities", headers=auth_headers,
                         json={"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1e-300}).json()
    client.put(f"/api/equities/{equity['id']}", headers=auth_headers, json={"current_price": 1e15})

    resp = client.get("/api/equities-summary", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["gain_percent"] == 0


def _restore(client, headers, backup):
    body = json.dumps(backup).encode("utf-8")
    return client.post("/api/restore", headers=headers, files={"file": ("backup.json", body, "application/json")})


@pytest.mark.parametrize("backup", [
    {"equities": [{"symbol": "TEST", "market": "NSE", "quantity": 10**9 + 1, "avg_buy_price": 1}]},
    {"snapshots": [{"total_assets": 2e300, "total_liabilities": 0, "timestamp": "2026-01-01T00:00:00"}]},
])
def test_restore_rejects_out_of_range_numbers_and_writes_nothing(client, auth_headers, backup):
    def stored_data():
        return {key: value for key, value in client.get("/api/export", headers=auth_headers).json().items()
                if key != "export_date"}

    client.post("/api/assets", headers=auth_headers, json={"name": "Test flat", "value": 100, "category": "real_estate"})
    before = stored_data()

    resp = _restore(client, auth_headers, backup)

    assert resp.status_code == 400
    assert stored_data() == before


def test_restore_keeps_a_tiny_invested_equity_at_zero_percent(client, auth_headers):
    backup = {"equities": [{"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1e-300,
                            "current_price": 1e15}]}

    resp = _restore(client, auth_headers, backup)

    assert resp.status_code == 200, resp.text
    [equity] = client.get("/api/equities", headers=auth_headers).json()
    assert equity["gain_loss_percent"] == 0
    assert client.get("/api/equities-summary", headers=auth_headers).json()["gain_percent"] == 0
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200


# Mutual funds: avg_nav and current_value are computed from inputs that are each within bounds

FUND = {"fund_name": "Test index", "amc": "Test AMC", "category": "index"}
TOO_LARGE = "The fund's computed value is too large"


@pytest.mark.parametrize("numbers", [
    {"units": 1e12, "current_nav": 1e15, "invested_amount": 1000},      # units * nav is 1e27
    {"units": 0.000001, "current_nav": 100, "invested_amount": 1e15},   # invested / units is 1e21
])
def test_a_mutual_fund_whose_computed_value_is_too_large_is_rejected_and_not_stored(client, auth_headers, numbers):
    resp = client.post("/api/mutual-funds", headers=auth_headers, json={**FUND, **numbers})

    assert resp.status_code == 422
    assert resp.json()["detail"] == TOO_LARGE
    listed = client.get("/api/mutual-funds", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json() == []


def test_a_fetched_nan_nav_is_rejected_and_not_stored(client, auth_headers, monkeypatch):
    import nav_service

    async def nan_nav(fund_name):
        return {"nav": float("nan"), "scheme_code": "000000"}

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", nan_nav)

    resp = client.post("/api/mutual-funds", headers=auth_headers, json={**FUND, "units": 10, "invested_amount": 1000})

    assert resp.status_code == 422
    listed = client.get("/api/mutual-funds", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json() == []


@pytest.mark.parametrize("update", [
    {"invested_amount": 1e15, "units": 0.000001},                       # avg_nav becomes 1e21
    {"units": 1e12, "current_nav": 1e15, "current_value": 0},           # current_value is recomputed as 1e27
])
def test_updating_a_mutual_fund_past_the_limit_is_rejected_and_keeps_the_row(client, auth_headers, update):
    created = client.post("/api/mutual-funds", headers=auth_headers,
                          json={**FUND, "units": 10, "invested_amount": 1000, "current_nav": 100})
    assert created.status_code == 201
    path = f"/api/mutual-funds/{created.json()['id']}"
    before = client.get(path, headers=auth_headers).json()

    resp = client.put(path, headers=auth_headers, json=update)

    assert resp.status_code == 422
    assert resp.json()["detail"] == TOO_LARGE
    assert client.get(path, headers=auth_headers).json() == before


def refresh_with_get(client, headers, fund):
    return client.get("/api/mutual-funds?refresh_nav=true", headers=headers)


def refresh_with_post(client, headers, fund):
    return client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=headers)


def fund_priced_at_100(client, headers):
    resp = client.post("/api/mutual-funds", headers=headers,
                       json={**FUND, "units": 10, "invested_amount": 1000, "current_nav": 100})
    assert resp.status_code == 201
    return resp.json()


def offer_nav(monkeypatch, nav):
    import nav_service

    async def fixed_nav(fund_name):
        return {"nav": nav, "date": "01-01-2026", "scheme_code": "000000"}

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", fixed_nav)


@pytest.mark.parametrize("refresh", [refresh_with_get, refresh_with_post])
def test_a_nav_refresh_that_would_exceed_the_limit_leaves_the_fund_unchanged(client, auth_headers, monkeypatch, refresh):
    fund = fund_priced_at_100(client, auth_headers)
    offer_nav(monkeypatch, 1e15)  # 10 units * 1e15 is above the limit

    resp = refresh(client, auth_headers, fund)

    assert resp.status_code == 200
    listed = client.get("/api/mutual-funds", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json() == [fund]


@pytest.mark.parametrize("refresh", [refresh_with_get, refresh_with_post])
def test_a_normal_nav_refresh_still_updates_the_fund(client, auth_headers, monkeypatch, refresh):
    fund = fund_priced_at_100(client, auth_headers)
    offer_nav(monkeypatch, 120)

    assert refresh(client, auth_headers, fund).status_code == 200

    [stored] = client.get("/api/mutual-funds", headers=auth_headers).json()
    assert stored["current_nav"] == 120
    assert stored["current_value"] == 1200
    assert stored["scheme_code"] == "000000"
