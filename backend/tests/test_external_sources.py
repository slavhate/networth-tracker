"""Outbound lookups (Yahoo Finance prices, mfapi.in search): authentication, URL encoding, price checks, bounded
caches, and keeping blocking lookups off the event loop. Nothing here reaches the network."""
import asyncio
import json
import math
import threading
from collections import OrderedDict

import httpx
import pytest

import database as db
import main
import nav_service
import nps_service
import stock_service

EQUITY = {"symbol": "TESTCO", "market": "NSE", "quantity": 10, "avg_buy_price": 100}


# ---------- Yahoo Finance ----------

class FakeResponse:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def chart(price, closes=()):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price},
                                  "indicators": {"quote": [{"close": list(closes)}]}}]}}


@pytest.fixture
def yahoo(monkeypatch):
    """requests.get answered with state["body"]; every URL asked for lands in state["urls"]."""
    state = {"body": chart(123.5), "urls": []}

    def get(url, **kwargs):
        state["urls"].append(url)
        return FakeResponse(state["body"])

    monkeypatch.setattr(stock_service.requests, "get", get)
    monkeypatch.setattr(stock_service.random, "uniform", lambda a, b: 0)  # no politeness delay in tests
    monkeypatch.setattr(stock_service, "_price_cache", {})
    return state


@pytest.mark.parametrize("symbol, segment", [
    ("M&M", "M%26M.NS"),
    ("A/B?x=1#y", "A%2FB%3FX%3D1%23Y.NS"),
])
def test_the_symbol_is_one_encoded_path_segment(yahoo, symbol, segment):
    stock_service.fetch_stock_price(symbol, "NSE")
    assert yahoo["urls"] == [f"https://query1.finance.yahoo.com/v8/finance/chart/{segment}"]


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -5e20, 0, 2e15, True, "12"])
def test_an_unusable_price_falls_back_to_the_last_usable_close(yahoo, price):
    yahoo["body"] = chart(price, closes=[90.0, float("nan"), None])
    assert stock_service.fetch_stock_price("TESTCO", "NSE")["current_price"] == 90.0


def test_no_usable_price_at_all_is_unavailable(yahoo):
    yahoo["body"] = chart(float("nan"), closes=[float("nan"), -1])
    assert stock_service.fetch_stock_price("TESTCO", "NSE") is None


@pytest.fixture
def price_feed(monkeypatch):
    """fetch_stock_price answers {"current_price": state["price"]}."""
    state = {"price": 150.0}
    monkeypatch.setattr(stock_service, "fetch_stock_price",
                        lambda symbol, market: {"symbol": symbol, "market": market, "current_price": state["price"],
                                                "company_name": None, "currency": "INR"})
    return state


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -5e20, 0, 1e15])
def test_a_bad_price_from_the_feed_is_never_stored(client, auth_headers, price_feed, price):
    price_feed["price"] = price  # 1e15 is a valid price, but 10 shares of it pass the amount limit

    resp = client.post("/api/equities", headers=auth_headers, json=EQUITY)

    assert resp.status_code == 201
    assert resp.json()["current_price"] == 100  # the buy price, as when the feed is down
    assert "x-warnings" in resp.headers
    equity = resp.json()
    for refresh in (lambda: client.post(f"/api/equities/{equity['id']}/refresh-price", headers=auth_headers),
                    lambda: client.get("/api/equities?refresh_prices=true", headers=auth_headers)):
        assert refresh().status_code == 200
    [stored] = db.load_data()["equities"]
    assert stored["current_price"] == 100 and math.isfinite(stored["current_value"])


def test_a_good_price_from_the_feed_is_stored(client, auth_headers, price_feed):
    resp = client.post("/api/equities", headers=auth_headers, json=EQUITY)
    assert resp.json()["current_price"] == 150 and resp.json()["current_value"] == 1500


def test_a_nan_stored_before_prices_were_checked_does_not_break_reads(client, auth_headers, offline_markets):
    equity = client.post("/api/equities", headers=auth_headers, json=EQUITY).json()
    data = db.load_data()
    nan = float("nan")
    data["equities"][0].update({"current_price": nan, "current_value": nan, "gain_loss": nan,
                                "gain_loss_percent": nan})
    db.save_data(data)

    listed = client.get("/api/equities", headers=auth_headers)
    assert listed.status_code == 200
    assert (listed.json()[0]["current_price"], listed.json()[0]["current_value"]) == (100, 1000)
    for path in ("/api/equities/" + equity["id"], "/api/equities-summary", "/api/dashboard", "/api/export"):
        assert client.get(path, headers=auth_headers).status_code == 200, path
    updated = client.put(f"/api/equities/{equity['id']}", headers=auth_headers, json={"notes": "fixed"})
    assert updated.status_code == 200 and updated.json()["current_value"] == 1000
    assert db.load_data()["equities"][0]["current_price"] == 100  # the edit stored a finite price again


def test_the_stock_price_lookup_needs_a_login(client, price_feed):
    assert client.get("/api/stock-price/NSE/TESTCO").status_code == 401


def test_the_stock_price_lookup_takes_known_markets_and_bounded_symbols(client, auth_headers, price_feed):
    assert client.get("/api/stock-price/NSE/TESTCO", headers=auth_headers).json()["current_price"] == 150
    assert client.get("/api/stock-price/LSE/TESTCO", headers=auth_headers).status_code == 422
    assert client.get("/api/stock-price/NSE/" + "X" * 101, headers=auth_headers).status_code == 422


def test_the_stock_price_lookup_turns_away_a_bad_price(client, auth_headers, price_feed):
    price_feed["price"] = float("nan")
    assert client.get("/api/stock-price/NSE/TESTCO", headers=auth_headers).status_code == 404


def test_a_price_lookup_does_not_hold_up_other_requests(client, auth_headers, monkeypatch):
    """The health check answers while a price lookup is still waiting on Yahoo: the lookup is in a worker thread."""
    health_answered = threading.Event()

    def slow_lookup(symbol, market):
        answered = health_answered.wait(timeout=5)  # only set if this lookup isn't blocking the event loop
        return {"current_price": 150.0 if answered else 1.0, "company_name": None}

    monkeypatch.setattr(stock_service, "fetch_stock_price", slow_lookup)

    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            async def health():
                resp = await ac.get("/api/health")
                health_answered.set()
                return resp

            return await asyncio.gather(ac.get("/api/stock-price/NSE/TESTCO", headers=auth_headers), health())

    looked_up, healthy = asyncio.run(run())

    assert healthy.status_code == 200
    assert looked_up.json()["current_price"] == 150


# ---------- mfapi.in ----------

@pytest.fixture
def mfapi(monkeypatch):
    """httpx calls from nav_service answered locally; every request lands in state["requests"]."""
    state = {"requests": [], "body": [{"schemeCode": 100001, "schemeName": "Test Banking & PSU Debt Fund"}]}

    def handler(request):
        state["requests"].append(request)
        return httpx.Response(200, json=state["body"])

    real_client = httpx.AsyncClient
    monkeypatch.setattr(nav_service.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(nav_service, "_search_cache", OrderedDict())
    monkeypatch.setattr(nav_service, "_nav_cache", {})
    return state


def test_a_fund_name_with_an_ampersand_is_searched_whole(mfapi):
    asyncio.run(nav_service.search_mutual_fund("Test Banking & PSU Debt Fund #2"))

    [request] = mfapi["requests"]
    assert request.url.path == "/mf/search"
    assert dict(request.url.params) == {"q": "Test Banking & PSU Debt Fund #2"}


def test_the_search_cache_keeps_only_the_most_recent_terms(mfapi, monkeypatch):
    monkeypatch.setattr(nav_service, "MAX_SEARCH_CACHE_ENTRIES", 3)
    for term in ("one", "two", "three", "four"):
        asyncio.run(nav_service.search_mutual_fund(term))
    asyncio.run(nav_service.search_mutual_fund("two"))  # a cache hit: becomes the most recent
    asyncio.run(nav_service.search_mutual_fund("five"))

    assert list(nav_service._search_cache) == ["four", "two", "five"]
    assert len(mfapi["requests"]) == 5


@pytest.mark.parametrize("code", ["1/../x", "12?a=b", "", None, "１２"])
def test_a_scheme_code_that_is_not_ascii_digits_is_never_fetched(mfapi, code):
    assert asyncio.run(nav_service.fetch_nav_by_scheme_code(code)) is None
    assert mfapi["requests"] == []


def test_the_nav_search_needs_a_login_and_a_short_query(client, auth_headers, mfapi):
    assert client.get("/api/nav/search?q=test").status_code == 401
    assert client.get("/api/nav/test").status_code == 401
    assert client.get("/api/nav/search?q=" + "x" * 151, headers=auth_headers).status_code == 422
    assert client.get("/api/nav/search?q=test", headers=auth_headers).json()[0]["schemeCode"] == 100001


# ---------- Edits landing while NAVs are fetched ----------

def test_a_fund_edit_does_not_overwrite_a_change_saved_while_it_fetched_navs(client, auth_headers, offline_markets,
                                                                              monkeypatch):
    fund = client.post("/api/mutual-funds", headers=auth_headers,
                       json={"fund_name": "Test Index Fund", "amc": "Test AMC", "category": "index", "units": 10,
                             "invested_amount": 1000}).json()
    assert fund["current_nav"] is None  # so an edit looks the NAV up again

    async def lookup_while_a_refresh_lands(name):
        db.update_mutual_fund(fund["id"], fund["user_id"], {"current_nav": 120.0, "current_value": 1200.0})
        return None

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", lookup_while_a_refresh_lands)

    resp = client.put(f"/api/mutual-funds/{fund['id']}", headers=auth_headers, json={"folio_number": "F-2"})

    assert resp.status_code == 409
    stored = db.get_mutual_fund_by_id(fund["id"], fund["user_id"])
    assert (stored["current_nav"], stored["current_value"], stored["folio_number"]) == (120.0, 1200.0, None)


def test_an_nps_edit_does_not_overwrite_a_change_saved_while_it_fetched_navs(client, auth_headers, offline_markets,
                                                                             monkeypatch):
    async def no_history(code):
        return None

    monkeypatch.setattr(nps_service, "fetch_history", no_history)
    asset = client.post("/api/assets", headers=auth_headers, json={
        "name": "Test NPS", "value": 100000, "category": "nps", "valuation_date": "2026-01-01",
        "nps_schemes": [{"scheme_code": "SM000001", "scheme_name": "Test Scheme E", "allocation_pct": 100}]}).json()

    async def history_while_an_edit_lands(code):
        db.update_asset(asset["id"], asset["user_id"], {"name": "Renamed meanwhile"})
        return None

    monkeypatch.setattr(nps_service, "fetch_history", history_while_an_edit_lands)

    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"value": 200000})

    assert resp.status_code == 409
    stored = db.get_asset_by_id(asset["id"], asset["user_id"])
    assert (stored["name"], stored["value"]) == ("Renamed meanwhile", 100000)


# ---------- Restore upload ----------

def test_a_restore_upload_is_read_only_up_to_the_limit():
    class EndlessUpload:
        def __init__(self):
            self.read_bytes = 0

        async def read(self, size=-1):
            assert 0 < size <= main.UPLOAD_CHUNK_BYTES  # never "everything"
            self.read_bytes += size
            return b"x" * size

    upload = EndlessUpload()
    data = asyncio.run(main._read_upload(upload, 1000))

    assert len(data) == 1001 and upload.read_bytes == 1001


def test_an_oversized_restore_is_refused(client, auth_headers, monkeypatch):
    import restore

    monkeypatch.setattr(restore, "MAX_BACKUP_BYTES", 100)
    body = json.dumps({"assets": [], "notes": "x" * 200}).encode()

    resp = client.post("/api/restore", headers=auth_headers, files={"file": ("backup.json", body, "application/json")})

    assert resp.status_code == 413
