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


@pytest.mark.parametrize("path, body, field, limit", [
    ("/api/assets", {"name": "Test flat", "value": 1, "category": "real_estate"}, "description", 2000),
    ("/api/liabilities", {"name": "Test loan", "amount": 1, "category": "other"}, "description", 2000),
    ("/api/bank-accounts", {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "savings",
                            "balance": 1}, "branch", 100),
    ("/api/insurances", {"policy_name": "Test term", "provider": "Test Insurer", "insurance_type": "term",
                         "sum_assured": 1, "premium": 1}, "notes", 2000),
    ("/api/insurances", {"policy_name": "Test term", "provider": "Test Insurer", "insurance_type": "term",
                         "sum_assured": 1, "premium": 1}, "nominee", 100),
    ("/api/mutual-funds", {"fund_name": "Test index", "amc": "Test AMC", "category": "index",
                           "invested_amount": 1}, "folio_number", 100),
    ("/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1}, "notes", 2000),
    ("/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1}, "company_name", 150),
    ("/api/goal", {"target_amount": 1}, "name", 100),
])
def test_free_text_has_a_length_limit(client, auth_headers, path, body, field, limit):
    """One request can't bloat the data file that every later request reads."""
    too_long = client.post(path, headers=auth_headers, json={**body, field: "x" * (limit + 1)})
    assert too_long.status_code == 422

    at_limit = client.post(path, headers=auth_headers, json={**body, field: "x" * limit})
    assert at_limit.status_code in (200, 201), at_limit.text


def test_updates_have_the_same_text_limits(client, auth_headers):
    asset = client.post("/api/assets", headers=auth_headers,
                        json={"name": "Test flat", "value": 100, "category": "real_estate"}).json()

    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"description": "x" * 2001})

    assert resp.status_code == 422


LEGACY_TEXT = "x" * 5000  # longer than any cap: what a version without the caps could have stored

# (collection, row as created through the API, field set to LEGACY_TEXT, list endpoint)
LEGACY_ROWS = [
    ("assets", ("/api/assets", {"name": "Test flat", "value": 1, "category": "real_estate"}), "description",
     "/api/assets"),
    ("liabilities", ("/api/liabilities", {"name": "Test loan", "amount": 1, "category": "other"}), "description",
     "/api/liabilities"),
    ("bank_accounts", ("/api/bank-accounts", {"bank_name": "Test Bank", "account_number": "00001234",
                                              "account_type": "savings", "balance": 1}), "branch",
     "/api/bank-accounts"),
    ("insurances", ("/api/insurances", {"policy_name": "Test term", "provider": "Test Insurer",
                                        "insurance_type": "term", "sum_assured": 1, "premium": 1}), "notes",
     "/api/insurances"),
    ("mutual_funds", ("/api/mutual-funds", {"fund_name": "Test index", "amc": "Test AMC", "category": "index",
                                            "invested_amount": 1}), "folio_number", "/api/mutual-funds"),
    ("equities", ("/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1}),
     "company_name", "/api/equities"),
]


def _store_legacy_text(client, auth_headers):
    """Every kind of row, then over-long text written straight into the data file, as an older version allowed."""
    import database as db

    for _, (path, body), _, _ in LEGACY_ROWS:
        assert client.post(path, headers=auth_headers, json=body).status_code == 201
    client.post("/api/goal", headers=auth_headers, json={"target_amount": 1})
    data = db.load_data()
    for collection, _, field, _ in LEGACY_ROWS:
        data[collection][0][field] = LEGACY_TEXT
    data["goals"][0]["name"] = LEGACY_TEXT
    db.save_data(data)


def test_text_saved_before_the_caps_still_reads(client, auth_headers):
    _store_legacy_text(client, auth_headers)

    for _, _, field, list_path in LEGACY_ROWS:
        resp = client.get(list_path, headers=auth_headers)
        assert resp.status_code == 200, list_path
        assert resp.json()[0][field] == LEGACY_TEXT
    goal = client.get("/api/goal", headers=auth_headers)
    assert goal.status_code == 200 and goal.json()["name"] == LEGACY_TEXT
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200


def test_a_backup_with_text_saved_before_the_caps_round_trips(client, auth_headers):
    _store_legacy_text(client, auth_headers)
    backup = client.get("/api/export", headers=auth_headers).json()

    resp = _restore(client, auth_headers, backup)

    assert resp.status_code == 200, resp.text
    for _, _, field, list_path in LEGACY_ROWS:
        assert client.get(list_path, headers=auth_headers).json()[0][field] == LEGACY_TEXT
    assert client.get("/api/goal", headers=auth_headers).json()["name"] == LEGACY_TEXT


def test_new_input_is_still_capped_when_older_rows_are_not(client, auth_headers):
    _store_legacy_text(client, auth_headers)
    [asset] = client.get("/api/assets", headers=auth_headers).json()

    assert client.put(f"/api/assets/{asset['id']}", headers=auth_headers,
                      json={"description": LEGACY_TEXT}).status_code == 422
    assert client.put("/api/goal", headers=auth_headers, json={"name": LEGACY_TEXT}).status_code == 422
    # An edit that leaves the old text alone still works
    assert client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"value": 2}).status_code == 200
