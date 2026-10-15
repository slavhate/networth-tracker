import pytest

import stock_service

pytestmark = pytest.mark.usefixtures("offline_markets")


def add_equity(client, headers, symbol, market, quantity, price):
    resp = client.post("/api/equities", headers=headers, json={
        "symbol": symbol, "market": market, "quantity": quantity, "avg_buy_price": price,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_nyse_symbol_has_no_suffix():
    assert stock_service.get_yahoo_symbol("ko", "NYSE") == "KO"


def test_nyse_equity_can_be_added(client, auth_headers):
    equity = add_equity(client, auth_headers, "KO", "NYSE", 10, 60)

    assert equity["market"] == "NYSE"
    assert equity["current_value"] == 600


def test_dashboard_converts_us_markets_only(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)      # $600 -> ₹48,000
    add_equity(client, auth_headers, "AAPL", "NASDAQ", 1, 100)  # $100 -> ₹8,000
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)     # ₹2,000
    add_equity(client, auth_headers, "INFY", "BSE", 1, 500)     # ₹500

    metrics = client.get("/api/dashboard", headers=auth_headers).json()

    assert metrics["assets_by_category"]["equities"] == 58500
    assert metrics["total_assets"] == 58500


def test_snapshot_converts_us_markets(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)

    snapshot = client.post("/api/snapshot", headers=auth_headers).json()

    assert snapshot["total_assets"] == 50000


def test_equities_summary_converts_us_markets(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)

    summary = client.get("/api/equities-summary", headers=auth_headers).json()

    assert summary["total_invested"] == 50000
    assert summary["total_current_value"] == 50000
    assert summary["total_gain"] == 0
