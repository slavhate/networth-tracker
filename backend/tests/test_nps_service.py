"""NPS NAV service: parsing the npsnav.in responses, caching, the configurable base URL."""
import asyncio
from datetime import date

import pytest

import nps_service
from config import settings


@pytest.fixture(autouse=True)
def empty_cache():
    nps_service._cache.clear()
    yield
    nps_service._cache.clear()


@pytest.fixture
def feed(monkeypatch):
    """Serve canned JSON by URL and record every request."""
    state = {"responses": {}, "calls": []}

    async def fake_get_json(url):
        state["calls"].append(url)
        return state["responses"].get(url)

    monkeypatch.setattr(nps_service, "_get_json", fake_get_json)
    monkeypatch.setattr(settings, "NPS_NAV_API_URL", "http://stub.test/api/")
    return state


def test_history_in_the_documented_format():
    payload = {"data": [{"date": "02-04-2026", "nav": 10.5}, {"date": "01-04-2026", "nav": "10.25"}],
               "metadata": {"currency": "INR"}}
    assert nps_service.parse_history(payload) == [(date(2026, 4, 1), 10.25), (date(2026, 4, 2), 10.5)]


def test_history_accepts_iso_dates_and_skips_rows_it_cannot_use():
    payload = {"data": [
        {"date": "2026-04-01", "nav": 10},
        {"date": "not a date", "nav": 11}, {"date": "02-04-2026", "nav": "abc"}, {"date": "03-04-2026", "nav": 0},
        {"date": "04-04-2026", "nav": -5}, {"date": "05-04-2026", "nav": "NaN"}, {"nav": 12}, "junk",
    ]}
    assert nps_service.parse_history(payload) == [(date(2026, 4, 1), 10.0)]


@pytest.mark.parametrize("payload", [None, [], "text", {"data": "x"}, {"rows": []}])
def test_history_of_an_unexpected_shape_is_empty(payload):
    assert nps_service.parse_history(payload) == []


def test_a_nav_too_large_for_a_float_skips_only_that_row():
    payload = {"data": [{"date": "01-04-2026", "nav": int("9" * 400)}, {"date": "02-04-2026", "nav": 10}]}
    assert nps_service.parse_history(payload) == [(date(2026, 4, 2), 10.0)]


def test_scheme_list_in_the_documented_format():
    payload = {"data": [
        {"PFM Code": "PFM900", "PFM Name": "Test Pension Fund Ltd.", "Scheme Code": "SM900002",
         "Scheme Name": "TEST PENSION FUND  SCHEME G - TIER I", "NAV": "12.5", "Last Updated": "13-10-2026"},
        {"PFM Code": "PFM900", "PFM Name": "Test Pension Fund Ltd.", "Scheme Code": "SM900001",
         "Scheme Name": "TEST PENSION FUND SCHEME E - TIER I", "NAV": 40, "Last Updated": "13-10-2026"},
        {"Scheme Code": "BAD", "Scheme Name": "skipped"},
        {"Scheme Code": "SM900003", "Scheme Name": ""},
    ]}
    assert nps_service.parse_latest(payload) == [
        {"scheme_code": "SM900001", "scheme_name": "TEST PENSION FUND SCHEME E - TIER I",
         "pfm_name": "Test Pension Fund Ltd.", "nav": 40.0, "nav_date": "2026-10-13"},
        {"scheme_code": "SM900002", "scheme_name": "TEST PENSION FUND SCHEME G - TIER I",
         "pfm_name": "Test Pension Fund Ltd.", "nav": 12.5, "nav_date": "2026-10-13"},
    ]


def test_scheme_code_skips_non_ascii_digits():
    payload = {"data": [
        {"Scheme Code": "SM٠١٢٣٤٥", "Scheme Name": "TEST PENSION FUND SCHEME X - TIER I", "NAV": "1"},
        {"Scheme Code": "SM900004", "Scheme Name": "TEST PENSION FUND SCHEME D - TIER I", "NAV": "1"},
    ]}
    assert [scheme["scheme_code"] for scheme in nps_service.parse_latest(payload)] == ["SM900004"]


def test_history_is_fetched_from_the_configured_base_url_and_cached(feed):
    feed["responses"]["http://stub.test/api/historical/SM900001"] = {"data": [{"date": "01-04-2026", "nav": 10}]}
    first = asyncio.run(nps_service.fetch_history("SM900001"))
    second = asyncio.run(nps_service.fetch_history("SM900001"))
    assert first == second == [(date(2026, 4, 1), 10.0)]
    assert feed["calls"] == ["http://stub.test/api/historical/SM900001"]


def test_a_failed_fetch_is_not_cached(feed):
    assert asyncio.run(nps_service.fetch_history("SM900001")) is None
    feed["responses"]["http://stub.test/api/historical/SM900001"] = {"data": [{"date": "01-04-2026", "nav": 10}]}
    assert asyncio.run(nps_service.fetch_history("SM900001")) == [(date(2026, 4, 1), 10.0)]
    assert len(feed["calls"]) == 2


@pytest.mark.parametrize("code", ["../latest", "SM12345", "SM٠١٢٣٤٥"])
def test_an_invalid_code_is_never_requested(feed, code):
    assert asyncio.run(nps_service.fetch_history(code)) is None
    assert feed["calls"] == []


def test_scheme_list_is_fetched_and_cached(feed):
    feed["responses"]["http://stub.test/api/latest"] = {"data": [
        {"PFM Name": "Test", "Scheme Code": "SM900001", "Scheme Name": "TEST SCHEME E - TIER I", "NAV": "1",
         "Last Updated": "13-10-2026"}]}
    assert asyncio.run(nps_service.list_schemes())[0]["scheme_code"] == "SM900001"
    asyncio.run(nps_service.list_schemes())
    assert feed["calls"] == ["http://stub.test/api/latest"]


def test_scheme_list_unavailable(feed):
    assert asyncio.run(nps_service.list_schemes()) is None


def test_a_malformed_base_url_returns_none_instead_of_raising(monkeypatch):
    monkeypatch.setattr(settings, "NPS_NAV_API_URL", "https://x:notaport/api")
    assert asyncio.run(nps_service.list_schemes()) is None
    assert asyncio.run(nps_service.fetch_history("SM900001")) is None


def test_a_caller_mutating_the_result_does_not_change_the_cache(feed):
    feed["responses"]["http://stub.test/api/latest"] = {"data": [
        {"PFM Name": "Test", "Scheme Code": "SM900001", "Scheme Name": "TEST SCHEME E - TIER I", "NAV": "1",
         "Last Updated": "13-10-2026"}]}
    first = asyncio.run(nps_service.list_schemes())
    first.clear()
    second = asyncio.run(nps_service.list_schemes())
    assert [scheme["scheme_code"] for scheme in second] == ["SM900001"]
    assert feed["calls"] == ["http://stub.test/api/latest"]
