import json
from datetime import date

import pytest

import exchange_service

pytestmark = pytest.mark.usefixtures("offline_markets")


def post(client, headers, path, body):
    resp = client.post(path, headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


CAR = {"name": "Test car", "value": 1_200_000, "category": "vehicles", "annual_change_rate": -15}
LOAN = {"name": "Test loan", "amount": 1_000_000, "category": "personal_loan", "interest_rate": 12}
FD = {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "fd", "balance": 100_000,
      "interest_rate": 7, "start_date": "2025-10-14", "maturity_date": "2026-11-13"}


def test_revalued_asset_gets_todays_date_and_a_current_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, "/api/assets", CAR)
    assert asset["valuation_date"] == "2026-10-14"
    assert asset["current_value"] == 1_200_000

    frozen_today["date"] = date(2030, 10, 14)  # 1461 days later
    [listed] = client.get("/api/assets", headers=auth_headers).json()
    assert listed["current_value"] == pytest.approx(626_407.50, abs=0.01)


def test_tenure_fills_the_emi_and_the_balance_date(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 1, 15)
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12})
    assert loan["emi"] == 88_848.79
    assert loan["balance_date"] == "2026-01-15"
    assert loan["amortized"] is True and loan["months_remaining"] == 12

    frozen_today["date"] = date(2026, 2, 15)
    got = client.get(f"/api/liabilities/{loan['id']}", headers=auth_headers).json()
    assert got["outstanding"] == pytest.approx(921_151.21, abs=0.01)
    assert got["payoff_date"] == "2027-01-15"


def test_an_explicit_emi_wins_over_the_tenure(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12, "emi": 90_000})
    assert loan["emi"] == 90_000


def test_updating_the_tenure_recomputes_the_emi(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", LOAN)
    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers, json={"tenure_months": 12})
    assert resp.json()["emi"] == 88_848.79
    assert resp.json()["balance_date"] == "2026-10-14"


def test_clearing_the_emi_makes_the_loan_manual_again(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 20_000})
    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers, json={"emi": None})
    assert resp.json()["amortized"] is False
    assert resp.json()["outstanding"] == 1_000_000


def test_a_rate_change_from_the_last_emi_date_keeps_todays_outstanding(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities",
                {"name": "Test home loan", "amount": 5_000_000, "category": "mortgage", "interest_rate": 8.5,
                 "emi": 52_000, "balance_date": "2020-10-14"})
    outstanding, last_emi_date, payoff_date = loan["outstanding"], loan["last_emi_date"], loan["payoff_date"]
    assert last_emi_date == "2026-10-14"

    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers,
                      json={"amount": outstanding, "balance_date": last_emi_date, "interest_rate": 9})

    assert resp.status_code == 200, resp.text
    assert resp.json()["outstanding"] == pytest.approx(outstanding, abs=0.01)
    assert resp.json()["payoff_date"] > payoff_date


def test_a_tenure_that_gives_a_zero_emi_is_rejected_before_anything_is_saved(client, auth_headers, frozen_today):
    resp = client.post("/api/liabilities", headers=auth_headers, json={**LOAN, "amount": 0, "tenure_months": 12})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "The EMI worked out from the tenure is out of range"
    assert client.get("/api/liabilities", headers=auth_headers).json() == []


def test_a_tenure_that_gives_an_oversized_emi_is_rejected(client, auth_headers, frozen_today):
    resp = client.post("/api/liabilities", headers=auth_headers,
                       json={**LOAN, "amount": 1e15, "interest_rate": 12, "tenure_months": 1})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "The EMI worked out from the tenure is out of range"
    assert client.get("/api/liabilities", headers=auth_headers).json() == []


def test_an_out_of_range_emi_from_a_tenure_update_changes_nothing(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "amount": 1e15})

    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers, json={"tenure_months": 1})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "The EMI worked out from the tenure is out of range"
    got = client.get(f"/api/liabilities/{loan['id']}", headers=auth_headers).json()
    assert got["tenure_months"] is None and got["emi"] is None


def test_a_null_for_a_required_field_is_ignored_when_working_out_the_emi(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", LOAN)

    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers,
                      json={"amount": None, "tenure_months": 12})

    assert resp.status_code == 200, resp.text
    assert resp.json()["emi"] == 88_848.79
    assert resp.json()["amount"] == 1_000_000


def test_updating_an_unknown_liability_is_404(client, auth_headers, frozen_today):
    resp = client.put("/api/liabilities/nope", headers=auth_headers, json={"name": "Renamed"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Liability not found"


def test_updating_an_unknown_bank_account_is_404(client, auth_headers, frozen_today):
    resp = client.put("/api/bank-accounts/nope", headers=auth_headers, json={"bank_name": "Renamed"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Bank account not found"


def test_schedule_endpoint(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 1, 15)
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12})
    frozen_today["date"] = date(2026, 2, 15)

    body = client.get(f"/api/liabilities/{loan['id']}/schedule", headers=auth_headers).json()

    assert [r["year"] for r in body["rows"]] == [2026, 2027]
    assert body["months_remaining"] == 11 and body["payoff_date"] == "2027-01-15"


def test_schedule_of_a_manual_liability_is_400(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", LOAN)
    resp = client.get(f"/api/liabilities/{loan['id']}/schedule", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This liability has no EMI set"


def test_schedule_of_an_unknown_liability_is_404(client, auth_headers, frozen_today):
    resp = client.get("/api/liabilities/nope/schedule", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Liability not found"


def test_fd_value_and_countdown(client, auth_headers, frozen_today):
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    assert fd["current_value"] == pytest.approx(107_185.90, abs=0.01)
    assert fd["days_to_maturity"] == 30 and fd["matured"] is False
    assert fd["maturity_value"] > fd["current_value"]


def test_maturity_before_start_is_rejected_on_create(client, auth_headers, frozen_today):
    resp = client.post("/api/bank-accounts", headers=auth_headers,
                       json={**FD, "start_date": "2026-01-01", "maturity_date": "2025-12-31"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Maturity date must be after the start date"


def test_maturity_before_start_is_rejected_on_update(client, auth_headers, frozen_today):
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    resp = client.put(f"/api/bank-accounts/{fd['id']}", headers=auth_headers, json={"maturity_date": "2025-01-01"})
    assert resp.status_code == 400
    assert client.get(f"/api/bank-accounts/{fd['id']}", headers=auth_headers).json()["maturity_date"] == "2026-11-13"


def test_dashboard_uses_computed_values_and_lists_maturities(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2022, 10, 14)
    post(client, auth_headers, "/api/assets", CAR)
    frozen_today["date"] = date(2026, 10, 14)
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 88_848.79, "balance_date": "2026-09-14"})

    metrics = client.get("/api/dashboard", headers=auth_headers).json()

    assert metrics["total_assets"] == pytest.approx(626_407.50 + 107_185.90, abs=0.02)
    assert metrics["total_liabilities"] == pytest.approx(921_151.21, abs=0.01)
    assert [m["id"] for m in metrics["maturities"]] == [fd["id"]]
    assert metrics["maturities"][0]["days_to_maturity"] == 30


def test_dashboard_ratio_is_zero_when_the_assets_are_negligible(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/assets", {"name": "Test dust", "value": 1e-300, "category": "other"})
    post(client, auth_headers, "/api/liabilities", {"name": "Test debt", "amount": 1e15, "category": "other"})

    resp = client.get("/api/dashboard", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.json()["debt_to_asset_ratio"] == 0


def test_snapshot_matches_the_dashboard(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/bank-accounts", FD)
    post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 88_848.79, "balance_date": "2026-09-14"})

    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    snapshot = client.post("/api/snapshot", headers=auth_headers).json()

    assert snapshot["total_assets"] == pytest.approx(metrics["total_assets"])
    assert snapshot["total_liabilities"] == pytest.approx(metrics["total_liabilities"])


def test_bank_summary_uses_current_values(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/bank-accounts", FD)
    summary = client.get("/api/bank-accounts-summary", headers=auth_headers).json()
    assert summary["total_balance"] == 107_185.9


def test_bank_summary_total_carries_no_float_noise(client, auth_headers, frozen_today):
    for number, balance in (("00001234", 0.1), ("00005678", 0.2)):
        post(client, auth_headers, "/api/bank-accounts",
             {"bank_name": "Test Bank", "account_number": number, "account_type": "savings", "balance": balance})

    summary = client.get("/api/bank-accounts-summary", headers=auth_headers).json()

    assert summary["total_balance"] == 0.3  # a plain sum of 0.1 and 0.2 is 0.30000000000000004


def test_export_holds_inputs_only_and_restores_them(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/assets", CAR)
    backup = client.get("/api/export", headers=auth_headers).json()
    assert "current_value" not in backup["assets"][0]
    assert backup["assets"][0]["annual_change_rate"] == -15

    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})

    assert resp.status_code == 200
    [asset] = client.get("/api/assets", headers=auth_headers).json()
    assert (asset["annual_change_rate"], asset["valuation_date"]) == (-15, "2026-10-14")


def test_no_rate_fetch_without_us_holdings(client, auth_headers, frozen_today, monkeypatch):
    post(client, auth_headers, "/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 10})

    async def must_not_be_called():
        raise AssertionError("rate fetched without US holdings")

    monkeypatch.setattr(exchange_service, "fetch_usd_to_inr", must_not_be_called)

    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200
    assert client.get("/api/equities-summary", headers=auth_headers).status_code == 200
    assert client.post("/api/snapshot", headers=auth_headers).status_code == 201


def test_a_malformed_date_is_a_422_that_says_invalid_date(client, auth_headers, frozen_today):
    resp = client.post("/api/assets", headers=auth_headers, json={**CAR, "valuation_date": "soon"})

    assert resp.status_code == 422
    assert "Invalid date" in [error["msg"] for error in resp.json()["detail"]]


def test_demo_data_shows_off_the_new_features(client, monkeypatch, frozen_today):
    import asyncio

    import database as db
    import main
    import valuation
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())

    demo_id = db.get_user_by_username(settings.DEMO_USERNAME)["id"]
    on = valuation.today()
    loans = [valuation.loan_status(l, on) for l in db.get_liabilities_by_user(demo_id)]
    amortized = [s for s in loans if s["amortized"]]
    assert len(amortized) == 2
    assert not any(s["emi_too_low"] for s in amortized)
    assert all(s["payoff_date"] for s in amortized)
    assert [m["days_to_maturity"] for m in valuation.upcoming_maturities(db.get_bank_accounts_by_user(demo_id), on)] == [20]
    revalued = [a for a in db.get_assets_by_user(demo_id) if a.get("annual_change_rate") is not None]
    assert [(a["name"], a["annual_change_rate"]) for a in revalued] == [("Honda City", -15)]


def test_demo_assets_use_the_indian_categories(client, monkeypatch, frozen_today):
    import asyncio

    import database as db
    import main
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())

    demo_id = db.get_user_by_username(settings.DEMO_USERNAME)["id"]
    by_name = {a["name"]: a for a in db.get_assets_by_user(demo_id)}
    assert (by_name["EPF Balance"]["category"], by_name["EPF Balance"]["interest_rate"]) == ("epf", 8.25)
    assert (by_name["PPF Account"]["category"], by_name["PPF Account"]["interest_rate"]) == ("ppf", 7.1)
    assert (by_name["EPF Balance"]["monthly_contribution"], by_name["PPF Account"]["monthly_contribution"]) == (3600, 12_500)
    assert by_name["EPF Balance"]["valuation_date"] and by_name["PPF Account"]["valuation_date"]
    assert by_name["NPS Account"]["category"] == "nps"
    gold = by_name["Gold Jewelry"]
    assert (gold["category"], gold["quantity"], gold["unit_price"], gold["value"]) == ("gold", 50, 10_000, 500_000)
