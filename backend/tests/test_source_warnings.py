"""A failed price or NAV source is reported to the UI in the X-Warnings response header."""
import json
from datetime import date

import pytest

import exchange_service
import nav_service
import nps_service
import stock_service

E = "TEST PENSION FUND SCHEME E - TIER I"


def warnings_of(resp):
    raw = resp.headers.get("x-warnings")
    return json.loads(raw) if raw else []


def fund(name, **extra):
    return {"fund_name": name, "amc": "Test AMC", "category": "equity", "units": 10, "invested_amount": 1000, **extra}


@pytest.fixture
def sources_down(monkeypatch):
    async def none(*args, **kwargs):
        return None

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", none)
    monkeypatch.setattr(nav_service, "fetch_history", none)
    monkeypatch.setattr(nps_service, "fetch_history", none)
    monkeypatch.setattr(nps_service, "list_schemes", none)
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)


def test_no_header_when_nothing_went_wrong(client, auth_headers):
    resp = client.get("/api/assets", headers=auth_headers)
    assert resp.status_code == 200 and "x-warnings" not in resp.headers


def test_mutual_fund_nav_unavailable_on_save(client, auth_headers, sources_down):
    resp = client.post("/api/mutual-funds", json=fund("Test Fund"), headers=auth_headers)
    assert resp.status_code == 201
    assert any("Test Fund" in w and "mfapi.in" in w for w in warnings_of(resp))


def test_mutual_fund_list_refresh_names_the_funds_it_missed(client, auth_headers, sources_down):
    for name in ("Fund One", "Fund Two"):
        client.post("/api/mutual-funds", json=fund(name, current_nav=100), headers=auth_headers)
    found = warnings_of(client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers))
    assert len(found) == 1 and "Fund One" in found[0] and "Fund Two" in found[0]


def test_single_fund_refresh_failure_warns(client, auth_headers, sources_down):
    created = client.post("/api/mutual-funds", json=fund("Test Fund", current_nav=100), headers=auth_headers).json()
    resp = client.post(f"/api/mutual-funds/{created['id']}/refresh-nav", headers=auth_headers)
    assert any("Test Fund" in w for w in warnings_of(resp))


def test_sip_installments_unpriced_warns(client, auth_headers, sources_down, frozen_today):
    frozen_today["date"] = date(2026, 6, 10)
    resp = client.post("/api/mutual-funds", json=fund(
        "Sip Fund", current_nav=100, sip_amount=1000, sip_frequency="monthly", sip_day=5,
        sip_start_date="2026-04-05", holdings_date="2026-04-01"), headers=auth_headers)
    assert any("SIP" in w and "Sip Fund" in w for w in warnings_of(resp))


def test_nps_save_without_navs_warns(client, auth_headers, sources_down):
    resp = client.post("/api/assets", json={
        "name": "My NPS", "category": "nps", "value": 1000, "valuation_date": "2026-03-31",
        "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100}]}, headers=auth_headers)
    assert resp.status_code == 201
    assert any("npsnav.in" in w and "My NPS" in w for w in warnings_of(resp))


def test_nps_refresh_failure_warns_with_the_502(client, auth_headers, sources_down):
    asset = client.post("/api/assets", json={
        "name": "My NPS", "category": "nps", "value": 1000, "valuation_date": "2026-03-31",
        "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100}]},
        headers=auth_headers).json()
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 502 and any("npsnav.in" in w for w in warnings_of(resp))


def test_nps_scheme_list_failure_warns(client, auth_headers, sources_down):
    resp = client.get("/api/nps/schemes", headers=auth_headers)
    assert resp.status_code == 502 and any("scheme list" in w for w in warnings_of(resp))


def test_stock_price_unavailable_warns(client, auth_headers, sources_down):
    # Use the real equity create payload (see EquityCreate): a symbol, market and quantity are needed.
    resp = client.post("/api/equities", json={"symbol": "TESTCO", "market": "NSE", "quantity": 5,
                                              "avg_buy_price": 100}, headers=auth_headers)
    assert any("TESTCO" in w for w in warnings_of(resp))


def test_usd_rate_unavailable_warns(client, auth_headers, monkeypatch):
    async def none():
        return None

    for name in ("_try_exchange_rate_api", "_try_frankfurter_api", "_try_fawazahmed_api"):
        monkeypatch.setattr(exchange_service, name, none)
    monkeypatch.setattr(exchange_service, "_cached_rate", None)
    monkeypatch.setattr(exchange_service, "_cache_timestamp", 0)
    monkeypatch.setattr(exchange_service, "_last_live", True)  # restored afterwards: the real fetch below clears it
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)
    client.post("/api/equities", json={"symbol": "TESTUS", "market": "NASDAQ", "quantity": 1, "avg_buy_price": 10},
                headers=auth_headers)
    resp = client.get("/api/dashboard", headers=auth_headers)
    assert any("USD" in w for w in warnings_of(resp))


def test_sip_fund_refresh_warns_about_the_nav_and_the_sip(client, auth_headers, sources_down, frozen_today):
    frozen_today["date"] = date(2026, 6, 10)
    created = client.post("/api/mutual-funds", json=fund(
        "Sip Fund", current_nav=100, sip_amount=1000, sip_frequency="monthly", sip_day=5,
        sip_start_date="2026-04-05", holdings_date="2026-04-01"), headers=auth_headers).json()
    found = warnings_of(client.post(f"/api/mutual-funds/{created['id']}/refresh-nav", headers=auth_headers))
    assert any("latest NAV" in w and "Sip Fund" in w for w in found)
    assert any("SIP" in w and "Sip Fund" in w for w in found)
    # The list refresh names the fund once: its NAV message covers the SIP that couldn't be priced either
    listed = warnings_of(client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers))
    assert len(listed) == 1 and "refresh the NAV" in listed[0] and "Sip Fund" in listed[0]


def sip_fund(name):
    return fund(name, current_nav=100, sip_amount=1000, sip_frequency="monthly", sip_day=5,
                sip_start_date="2026-04-05", holdings_date="2026-04-01")


THIRTY = [f"Test Flexi Cap Fund Direct Plan Growth Option {number:02d}" for number in range(30)]


@pytest.fixture
def thirty_sip_funds(client, auth_headers, sources_down, frozen_today):
    frozen_today["date"] = date(2026, 6, 10)
    for name in THIRTY:
        assert client.post("/api/mutual-funds", json=sip_fund(name), headers=auth_headers).status_code == 201


def test_a_list_refresh_of_many_failing_sip_funds_sends_one_short_warning(client, auth_headers, thirty_sip_funds):
    resp = client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers)
    assert len(resp.headers["x-warnings"]) <= 2000
    (message,) = warnings_of(resp)  # no SIP message per fund: the NAV message already names them
    assert "30 funds" in message and THIRTY[0] in message and "and 25 more" in message and THIRTY[29] not in message


def test_a_list_refresh_names_the_sips_it_couldnt_price_in_one_warning(client, auth_headers, thirty_sip_funds,
                                                                       monkeypatch):
    async def found(fund_name):  # the latest NAV is found; the NAV history isn't
        return {"nav": 50.0, "date": "05-06-2026", "scheme_code": "100001"}

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", found)
    resp = client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers)
    assert len(resp.headers["x-warnings"]) <= 2000
    (message,) = warnings_of(resp)
    assert message.startswith("Couldn't price the SIP installments of 30 funds with NAVs from mfapi.in: ")
    assert THIRTY[0] in message and "and 25 more" in message and THIRTY[29] not in message


def test_the_header_keeps_to_its_budget_and_counts_what_it_left_out(client, auth_headers, sources_down, monkeypatch):
    import main
    import user_warnings

    many = [f"Warning {number:03d}: " + "x" * 80 for number in range(60)]
    monkeypatch.setattr(main, "_warn_stock_prices", lambda symbols: [user_warnings.warn(m) for m in many])
    client.post("/api/equities", json={"symbol": "AAA", "market": "NSE", "quantity": 1, "avg_buy_price": 10},
                headers=auth_headers)
    raw = client.get("/api/equities?refresh_prices=true", headers=auth_headers).headers["x-warnings"]
    assert raw.isascii() and len(raw) <= 2000
    found = json.loads(raw)
    kept = len(found) - 1
    assert kept > 0 and found[:kept] == many[:kept]  # in order, while they fit
    assert found[-1] == f"…and {60 - kept} more warnings"


def test_header_value_within_and_beyond_the_budget():
    import user_warnings

    assert json.loads(user_warnings.header_value(["one", "two"])) == ["one", "two"]
    short = user_warnings.header_value(["a" * 10, "b" * 10, "c" * 10], budget=50)
    assert len(short) <= 50 and json.loads(short) == ["a" * 10, "…and 2 more warnings"]
    alone = user_warnings.header_value(["x" * 100], budget=50)  # even the first doesn't fit
    assert len(alone) <= 50 and json.loads(alone) == ["…and 1 more warning"]


def test_no_warning_when_the_nav_is_found(client, auth_headers, monkeypatch):
    async def found(fund_name):
        return {"nav": 50.0, "date": "01-01-2026", "scheme_code": "100001"}

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", found)
    resp = client.post("/api/mutual-funds", json=fund("Test Fund"), headers=auth_headers)
    assert resp.status_code == 201 and "x-warnings" not in resp.headers


def test_stock_list_refresh_names_the_symbols_in_one_warning(client, auth_headers, sources_down):
    for symbol in ("AAA", "BBB"):
        client.post("/api/equities", json={"symbol": symbol, "market": "NSE", "quantity": 1, "avg_buy_price": 10},
                    headers=auth_headers)
    found = warnings_of(client.get("/api/equities?refresh_prices=true", headers=auth_headers))
    assert len(found) == 1 and "AAA" in found[0] and "BBB" in found[0]


def test_single_stock_refresh_and_price_lookup_warn(client, auth_headers, sources_down):
    created = client.post("/api/equities", json={"symbol": "TESTCO", "market": "NSE", "quantity": 5,
                                                 "avg_buy_price": 100}, headers=auth_headers).json()
    refreshed = client.post(f"/api/equities/{created['id']}/refresh-price", headers=auth_headers)
    assert any("TESTCO" in w for w in warnings_of(refreshed))
    lookup = client.get("/api/stock-price/NSE/TESTCO", headers=auth_headers)
    assert lookup.status_code == 404 and any("TESTCO" in w for w in warnings_of(lookup))


def test_a_price_lookup_warns_without_holding_wording_and_cuts_a_long_symbol(client, auth_headers, sources_down):
    symbol = "A" * 20 + "B" * 30  # the path takes any symbol; only 20 characters of it are echoed
    resp = client.get(f"/api/stock-price/NSE/{symbol}", headers=auth_headers)
    assert resp.status_code == 404
    assert warnings_of(resp) == [f"Couldn't fetch the price of {'A' * 20} right now."]
    # A holding's message keeps saying what its value uses
    created = client.post("/api/equities", json={"symbol": "TESTCO", "market": "NSE", "quantity": 5,
                                                 "avg_buy_price": 100}, headers=auth_headers).json()
    refreshed = client.post(f"/api/equities/{created['id']}/refresh-price", headers=auth_headers)
    assert warnings_of(refreshed) == ["Couldn't fetch the price of TESTCO; its value uses the last known price."]


def test_a_long_list_of_names_is_cut_short(client, auth_headers, sources_down):
    for number in range(8):
        client.post("/api/equities", json={"symbol": f"SYM{number}", "market": "NSE", "quantity": 1,
                                           "avg_buy_price": 10}, headers=auth_headers)
    (message,) = warnings_of(client.get("/api/equities?refresh_prices=true", headers=auth_headers))
    assert "8 stocks" in message and "SYM0" in message and "and 3 more" in message and "SYM7" not in message


def test_header_stays_ascii_and_round_trips_the_message(client, auth_headers, sources_down):
    name = "NPS ₹ → fund"
    resp = client.post("/api/assets", json={
        "name": name, "category": "nps", "value": 1000, "valuation_date": "2026-03-31",
        "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100}]}, headers=auth_headers)
    assert resp.headers["x-warnings"].isascii()
    assert any(name in w for w in warnings_of(resp))


def test_a_live_rate_or_no_us_holding_does_not_warn(client, auth_headers, monkeypatch):
    async def live():
        return 85.0

    async def none():
        return None

    monkeypatch.setattr(exchange_service, "_try_exchange_rate_api", live)
    monkeypatch.setattr(exchange_service, "_try_frankfurter_api", none)
    monkeypatch.setattr(exchange_service, "_try_fawazahmed_api", none)
    monkeypatch.setattr(exchange_service, "_cached_rate", None)
    monkeypatch.setattr(exchange_service, "_cache_timestamp", 0)
    monkeypatch.setattr(exchange_service, "_last_live", False)  # left over from an earlier fallback
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)
    # No US holding: no rate is needed, so the stale flag must not warn
    assert "x-warnings" not in client.get("/api/dashboard", headers=auth_headers).headers
    client.post("/api/equities", json={"symbol": "TESTUS", "market": "NASDAQ", "quantity": 1, "avg_buy_price": 10},
                headers=auth_headers)
    resp = client.get("/api/dashboard", headers=auth_headers)
    assert not any("USD" in w for w in warnings_of(resp))


def test_exchange_service_reports_whether_the_rate_was_live(monkeypatch):
    import asyncio

    source = {"rate": 85.0}

    async def first():
        return source["rate"]

    async def none():
        return None

    monkeypatch.setattr(exchange_service, "_try_exchange_rate_api", first)
    monkeypatch.setattr(exchange_service, "_try_frankfurter_api", none)
    monkeypatch.setattr(exchange_service, "_try_fawazahmed_api", none)
    monkeypatch.setattr(exchange_service, "_cached_rate", None)
    monkeypatch.setattr(exchange_service, "_cache_timestamp", 0)
    monkeypatch.setattr(exchange_service, "_last_live", False)

    assert asyncio.run(exchange_service.fetch_usd_to_inr()) == 85.0 and exchange_service.last_rate_was_live()
    source["rate"] = None
    assert asyncio.run(exchange_service.fetch_usd_to_inr()) == 85.0 and exchange_service.last_rate_was_live()  # fresh cache
    monkeypatch.setattr(exchange_service, "_cache_timestamp", 0)  # the cache has expired
    assert asyncio.run(exchange_service.fetch_usd_to_inr()) == 85.0 and not exchange_service.last_rate_was_live()
    monkeypatch.setattr(exchange_service, "_cached_rate", None)
    assert asyncio.run(exchange_service.fetch_usd_to_inr()) == exchange_service.FALLBACK_RATE
    assert not exchange_service.last_rate_was_live()


def test_identical_warnings_are_sent_once():
    import user_warnings
    token = user_warnings.start()
    try:
        user_warnings.warn("same")
        user_warnings.warn("same")
        assert user_warnings.collected() == ["same"]
    finally:
        user_warnings.stop(token)


def test_warn_outside_a_request_is_ignored():
    import user_warnings
    user_warnings.warn("nobody is listening")  # must not raise


def test_header_is_exposed_to_browsers(client, auth_headers):
    resp = client.get("/api/assets", headers={**auth_headers, "Origin": "http://localhost:5173"})
    assert "x-warnings" in resp.headers.get("access-control-expose-headers", "").lower()
