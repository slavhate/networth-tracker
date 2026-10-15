"""Mutual fund SIPs through the API: pricing on save and refresh, stopping a SIP, summary, restore."""
import asyncio
import io
import json
from datetime import date

import pytest

import nav_service

HISTORY = [(date(2026, 4, 1), 10.0), (date(2026, 4, 5), 10.0), (date(2026, 5, 5), 12.5), (date(2026, 6, 5), 20.0)]


def payload(**extra):
    return {"fund_name": "Test Index Fund", "amc": "Test AMC", "category": "index", "units": 100,
            "invested_amount": 1000, "current_value": None, "current_nav": None, "folio_number": None,
            "sip_amount": 1000, "sip_frequency": "monthly", "sip_day": 5, "sip_start_date": "2026-04-05",
            "sip_end_date": None, "holdings_date": "2026-04-01", **extra}


@pytest.fixture
def feed(monkeypatch, frozen_today):
    """mfapi for one made-up fund; set state["up"] = False to make it unavailable, or state["lookup_up"] /
    state["history_up"] = False to take down only the name lookup (latest NAV) or only the NAV history."""
    frozen_today["date"] = date(2026, 6, 10)
    state = {"up": True, "lookup_up": True, "history_up": True, "history": list(HISTORY), "history_calls": 0,
             "today": frozen_today}

    async def fetch_nav_by_fund_name(name):
        if not (state["up"] and state["lookup_up"]):
            return None
        when, nav = state["history"][-1]
        return {"nav": nav, "date": when.strftime("%d-%m-%Y"), "scheme_name": name, "scheme_code": "100001"}

    async def fetch_history(code):
        state["history_calls"] += 1
        return state["history"] if state["up"] and state["history_up"] and code == "100001" else None

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", fetch_nav_by_fund_name)
    monkeypatch.setattr(nav_service, "fetch_history", fetch_history)
    return state


def create(client, headers, **extra):
    resp = client.post("/api/mutual-funds", json=payload(**extra), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_prices_the_sip(client, auth_headers, feed):
    fund = create(client, auth_headers)
    assert (fund["sip_units"], fund["sip_invested"], fund["sip_priced_through"]) == (230, 3000, "2026-06-10")
    assert (fund["current_value"], fund["total_units"], fund["total_invested"]) == (6600, 330, 4000)


def test_create_while_navs_unavailable_counts_installments_at_cost(client, auth_headers, feed):
    feed["up"] = False
    fund = create(client, auth_headers)
    assert fund["sip_priced_through"] is None
    assert (fund["total_invested"], fund["total_units"]) == (4000, 100)
    assert fund["current_value"] == 4000  # 1,000 stored (units × average NAV) + 3 installments at cost


def test_sip_defaults(client, auth_headers, feed):
    fund = create(client, auth_headers, sip_frequency=None, sip_day=None, sip_start_date=None, holdings_date=None)
    assert (fund["holdings_date"], fund["sip_start_date"], fund["sip_frequency"], fund["sip_day"]) == (
        "2026-06-10", "2026-06-10", "monthly", 10)


def test_name_only_update_keeps_sip_pricing_without_fetching(client, auth_headers, feed):
    fund = create(client, auth_headers)
    calls = feed["history_calls"]
    resp = client.put(f"/api/mutual-funds/{fund['id']}", json={"folio_number": "F-1"}, headers=auth_headers)
    assert resp.status_code == 200
    assert feed["history_calls"] == calls
    assert resp.json()["sip_units"] == 230


# ---------- changing a SIP: its amount, frequency or day apply from today; its dates are corrections ----------

FORM_FIELDS = ("fund_name", "amc", "category", "invested_amount", "units", "current_nav", "folio_number",
               "sip_amount", "sip_frequency", "sip_day", "sip_start_date", "sip_end_date", "holdings_date")
STOP = {"sip_amount": None, "sip_frequency": None, "sip_day": None, "sip_start_date": None, "sip_end_date": None,
        "holdings_date": None}


def form(fund, **changes):
    """What the edit form sends for a fund: its fields as stored, without the current value (left untouched)."""
    return {**{key: fund.get(key) for key in FORM_FIELDS}, **changes}


def put(client, headers, fund, **changes):
    return client.put(f"/api/mutual-funds/{fund['id']}", json=form(fund, **changes), headers=headers)


@pytest.mark.parametrize("change", [{"sip_amount": 2000}, {"sip_frequency": "weekly", "sip_day": None},
                                    {"sip_day": 20}])
def test_a_schedule_change_folds_the_installments_so_far_into_the_holding(client, auth_headers, feed, change):
    fund = create(client, auth_headers)  # priced 10 Jun: 100 units + 230 SIP units (3 × 1,000) at 20
    resp = put(client, auth_headers, fund, **change)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["units"], body["invested_amount"], body["holdings_date"]) == (330, 4000, "2026-06-10")
    assert (body["sip_units"], body["sip_invested"], body["sip_priced_through"]) == (0, 0, "2026-06-10")
    assert (body["current_value"], body["total_units"], body["total_invested"]) == (6600, 330, 4000)


def test_after_an_amount_change_only_new_installments_use_the_new_amount(client, auth_headers, feed):
    fund = create(client, auth_headers)
    # Before the fold, the new amount replayed every installment since 1 Apr: 460 SIP units, ₹11,200 never invested
    body = put(client, auth_headers, fund, sip_amount=2000).json()
    assert body["current_value"] == 6600
    a_new_nav_on_5_july(feed)
    assert stored(client, auth_headers, fund["id"])["current_value"] == 6600 + 2000  # 5 Jul at cost until priced
    later = refresh(client, auth_headers, fund["id"], "post")["fund"]
    assert (later["sip_units"], later["sip_invested"]) == (80, 2000)  # 2,000 at 25
    assert (later["current_value"], later["total_units"], later["total_invested"]) == (410 * 25, 410, 6000)


def test_an_amount_change_on_a_sip_saved_while_navs_were_down_keeps_every_installment(client, auth_headers, feed):
    feed["up"] = False
    fund = create(client, auth_headers)  # unpriced: 100 units at cost (₹1,000) + 3 installments at cost
    assert (fund["total_units"], fund["current_value"]) == (100, 4000)
    feed["up"] = True
    body = put(client, auth_headers, fund, sip_amount=2000).json()
    # The client re-anchor sent today's total units (100, without the installments) and lost them; 330 at 20 is right
    assert (body["units"], body["invested_amount"], body["holdings_date"]) == (330, 4000, "2026-06-10")
    assert (body["current_value"], body["total_units"], body["total_invested"]) == (6600, 330, 4000)
    assert body["scheme_code"] == "100001"


@pytest.mark.parametrize("stop", [STOP, {"sip_amount": None}, {"sip_amount": 0}], ids=["form", "api", "zero"])
def test_stopping_the_sip_folds_it_and_keeps_the_value(client, auth_headers, feed, stop):
    fund = create(client, auth_headers)
    body = client.put(f"/api/mutual-funds/{fund['id']}", headers=auth_headers,
                      json=form(fund, **stop) if stop is STOP else stop).json()
    assert not body["sip_amount"] and body["sip_units"] is None and body["sip_priced_through"] is None
    assert (body["units"], body["invested_amount"]) == (330, 4000)
    assert (body["current_value"], body["total_units"], body["total_invested"]) == (6600, 330, 4000)


def test_a_schedule_change_that_cant_fetch_navs_is_refused_and_nothing_is_stored(client, auth_headers, feed):
    import database as db

    fund = create(client, auth_headers)
    before = db.get_mutual_fund_by_id(fund["id"], fund["user_id"])
    feed["up"] = False
    resp = put(client, auth_headers, fund, sip_amount=2000, folio_number="F-9")
    assert resp.status_code == 409
    assert resp.json()["detail"] == ("Couldn't fetch NAVs to apply the SIP change from today; "
                                     "try again when NAVs are available")
    assert any("SIP" in w and "Test Index Fund" in w for w in json.loads(resp.headers["x-warnings"]))
    assert db.get_mutual_fund_by_id(fund["id"], fund["user_id"]) == before


def test_a_sip_with_no_installments_yet_changes_without_navs(client, auth_headers, feed):
    feed["up"] = False
    fund = create(client, auth_headers, sip_start_date="2026-07-05", holdings_date="2026-06-10")
    resp = put(client, auth_headers, fund, sip_amount=2000)
    assert resp.status_code == 200
    assert (resp.json()["units"], resp.json()["sip_amount"], resp.json()["holdings_date"]) == (100, 2000, "2026-06-10")


def test_a_schedule_change_keeps_a_holdings_date_after_today(client, auth_headers, feed):
    fund = create(client, auth_headers, holdings_date="2026-07-01")  # units as of 1 Jul hold its installments
    body = put(client, auth_headers, fund, sip_amount=2000).json()
    assert (body["units"], body["holdings_date"]) == (100, "2026-07-01")


def test_an_end_date_correction_reprices_from_the_holdings_date(client, auth_headers, feed):
    fund = create(client, auth_headers)
    body = put(client, auth_headers, fund, sip_end_date="2026-05-10").json()
    assert (body["units"], body["invested_amount"], body["holdings_date"]) == (100, 1000, "2026-04-01")  # no fold
    assert (body["sip_units"], body["sip_invested"]) == (180, 2000)  # 5 Jun's installment is after the new end
    assert (body["current_value"], body["total_invested"]) == (280 * 20, 3000)


def test_a_change_that_restates_the_holding_is_taken_as_given(client, auth_headers, feed):
    fund = create(client, auth_headers)
    body = put(client, auth_headers, fund, sip_amount=2000, units=150).json()
    assert (body["units"], body["invested_amount"], body["holdings_date"]) == (150, 1000, "2026-04-01")  # no fold
    assert body["sip_units"] == 460  # the installments since 1 Apr at the new amount, as the user stated


def test_a_failed_repricing_does_not_count_the_old_pricing_twice(client, auth_headers, feed):
    fund = create(client, auth_headers)
    feed["up"] = False
    body = put(client, auth_headers, fund, sip_end_date="2026-05-10").json()  # a correction: saved unpriced
    assert body["sip_units"] is None
    # 100 units at the last NAV of 20, plus the 2 installments up to the end date at cost
    assert (body["current_value"], body["total_units"], body["total_invested"]) == (2000 + 2000, 100, 1000 + 2000)


def test_an_edit_without_a_current_value_keeps_the_one_typed_before(client, auth_headers, feed):
    feed["up"] = False  # no NAV: the value the user typed is all the fund has
    fund = create(client, auth_headers, current_value=5000)
    assert fund["current_value"] == 5000 + 3000  # + 3 installments at cost
    body = put(client, auth_headers, fund, folio_number="F-1").json()
    assert body["current_value"] == 5000 + 3000


def test_end_date_before_start_is_rejected(client, auth_headers, feed):
    resp = client.post("/api/mutual-funds", json=payload(sip_end_date="2026-04-01"), headers=auth_headers)
    assert resp.status_code == 422
    fund = create(client, auth_headers)
    resp = client.put(f"/api/mutual-funds/{fund['id']}", json={"sip_end_date": "2026-01-01"}, headers=auth_headers)
    assert resp.status_code == 422
    assert "SIP end date must be on or after its start date" in resp.text


def test_refresh_prices_the_sip_up_to_today(client, auth_headers, feed):
    fund = create(client, auth_headers)
    feed["history"] = HISTORY + [(date(2026, 7, 5), 25.0)]
    feed["today"]["date"] = date(2026, 7, 6)
    resp = client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=auth_headers)
    body = resp.json()
    assert body["status"] == "success"
    assert body["fund"]["sip_units"] == 270  # + 1,000 at 25
    listed = client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers).json()[0]
    assert listed["sip_priced_through"] == "2026-07-06"
    assert listed["current_value"] == 370 * 25


def test_refresh_failure_keeps_sip_pricing(client, auth_headers, feed):
    fund = create(client, auth_headers)
    feed["up"] = False
    client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=auth_headers)
    again = client.get(f"/api/mutual-funds/{fund['id']}", headers=auth_headers).json()
    assert (again["sip_units"], again["sip_priced_through"]) == (230, "2026-06-10")


def test_summary_and_dashboard_include_installments(client, auth_headers, feed):
    create(client, auth_headers)
    summary = client.get("/api/mutual-funds-summary", headers=auth_headers).json()
    assert (summary["total_invested"], summary["total_current_value"]) == (4000, 6600)
    dashboard = client.get("/api/dashboard", headers=auth_headers).json()
    assert dashboard["assets_by_category"]["mutual_funds"] == 6600


def _restore(client, headers, backup):
    files = {"file": ("backup.json", io.BytesIO(json.dumps(backup).encode()), "application/json")}
    return client.post("/api/restore", files=files, headers=headers)


def test_restore_round_trip_keeps_the_sip(client, auth_headers, feed):
    create(client, auth_headers)
    backup = client.get("/api/export", headers=auth_headers).json()
    feed["up"] = False
    assert _restore(client, auth_headers, backup).status_code == 200
    fund = client.get("/api/mutual-funds", headers=auth_headers).json()[0]
    assert (fund["sip_units"], fund["sip_day"], fund["total_invested"]) == (230, 5, 4000)


def test_an_end_date_before_the_defaulted_start_is_rejected_on_create(client, auth_headers, feed):
    # No start or holdings date: both default to today (10 Jun), which is after this end date
    resp = client.post("/api/mutual-funds", headers=auth_headers, json=payload(
        sip_start_date=None, holdings_date=None, sip_end_date="2026-05-01"))
    assert resp.status_code == 422
    assert "SIP end date must be on or after its start date" in resp.text
    assert client.get("/api/mutual-funds", headers=auth_headers).json() == []


# ---------- refreshing a SIP: priced from the NAV history, whether or not the latest-NAV lookup works ----------

REFRESH_PATHS = ["post", "list"]


def refresh(client, headers, fund_id, how):
    """Refresh one fund through either refresh path; returns the fund as that path reports it."""
    if how == "post":
        body = client.post(f"/api/mutual-funds/{fund_id}/refresh-nav", headers=headers).json()
        return body
    funds = client.get("/api/mutual-funds?refresh_nav=true", headers=headers).json()
    return {"status": "success", "fund": next(f for f in funds if f["id"] == fund_id)}


def stored(client, headers, fund_id):
    return client.get(f"/api/mutual-funds/{fund_id}", headers=headers).json()


def a_new_nav_on_5_july(feed):
    feed["history"] = HISTORY + [(date(2026, 7, 5), 25.0)]
    feed["today"]["date"] = date(2026, 7, 6)


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_refresh_prices_the_sip_from_the_history_when_the_nav_lookup_is_down(client, auth_headers, feed, how):
    fund = create(client, auth_headers)  # stores scheme_code 100001
    a_new_nav_on_5_july(feed)
    feed["lookup_up"] = False
    body = refresh(client, auth_headers, fund["id"], how)
    assert body["status"] == "success"
    assert (body["fund"]["sip_units"], body["fund"]["sip_priced_through"]) == (270, "2026-07-06")
    again = stored(client, auth_headers, fund["id"])
    assert (again["sip_units"], again["sip_priced_through"], again["current_value"]) == (270, "2026-07-06", 370 * 25)


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_refresh_keeps_the_sip_pricing_when_the_history_is_down(client, auth_headers, feed, how):
    fund = create(client, auth_headers)
    a_new_nav_on_5_july(feed)
    feed["history_up"] = False  # the latest NAV is found, the history isn't
    body = refresh(client, auth_headers, fund["id"], how)
    assert body["status"] == "success"
    for seen in (body["fund"], stored(client, auth_headers, fund["id"])):
        assert (seen["sip_units"], seen["sip_invested"], seen["sip_priced_through"]) == (230, 3000, "2026-06-10")


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_refresh_prices_a_sip_that_was_saved_while_the_navs_were_down(client, auth_headers, feed, how):
    feed["up"] = False
    fund = create(client, auth_headers)
    assert fund["sip_priced_through"] is None
    feed["up"] = True
    body = refresh(client, auth_headers, fund["id"], how)
    assert body["status"] == "success"
    again = stored(client, auth_headers, fund["id"])
    assert (again["sip_units"], again["sip_priced_through"], again["current_value"]) == (230, "2026-06-10", 6600)


def during_fetch(monkeypatch, name, change):
    """Run `change` once while nav_service.<name> is on its way, as a save or delete landing mid-refresh would."""
    real = getattr(nav_service, name)
    done = []

    async def fetch(*args):
        if not done:
            done.append(change())
        return await real(*args)

    monkeypatch.setattr(nav_service, name, fetch)
    return done


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_a_refresh_keeps_a_sip_edit_made_while_it_fetched(client, auth_headers, feed, monkeypatch, how):
    import database as db

    fund = create(client, auth_headers)  # priced 10 Jun: 230 SIP units on 100 units
    a_new_nav_on_5_july(feed)
    rebased = {"units": 370.0, "invested_amount": 5000.0, "holdings_date": "2026-07-06", "sip_amount": 2000.0,
               "sip_units": 0.0, "sip_invested": 0.0, "sip_priced_through": "2026-07-06",
               "current_value": 370 * 25.0, "current_nav": 25.0}
    edited = during_fetch(monkeypatch, "fetch_history", lambda: db.update_mutual_fund(
        fund["id"], fund["user_id"], rebased))
    body = refresh(client, auth_headers, fund["id"], how)
    # Nothing worked out from the row read before the fetch is written over the edit (no stale 270 SIP units)
    assert db.get_mutual_fund_by_id(fund["id"], fund["user_id"]) == edited[0]
    assert (body["fund"]["units"], body["fund"]["total_units"], body["fund"]["current_value"]) == (370, 370, 370 * 25)


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_a_refresh_keeps_units_edited_while_it_fetched(client, auth_headers, feed, monkeypatch, how):
    import database as db

    fund = create(client, auth_headers, sip_amount=None)  # no SIP: only the latest NAV is fetched
    a_new_nav_on_5_july(feed)
    edited = during_fetch(monkeypatch, "fetch_nav_by_fund_name", lambda: db.update_mutual_fund(
        fund["id"], fund["user_id"], {"units": 150.0, "current_value": 3000.0}))
    body = refresh(client, auth_headers, fund["id"], how)
    # The value is not worked out again from the 100 units read before the fetch
    assert db.get_mutual_fund_by_id(fund["id"], fund["user_id"]) == edited[0]
    assert (body["fund"]["units"], body["fund"]["current_value"]) == (150, 3000)


def test_a_refresh_values_the_units_stored_when_it_writes(client, auth_headers, feed, monkeypatch):
    """An edit to something pricing doesn't depend on (the folio) is kept, and the refresh still lands."""
    import database as db

    fund = create(client, auth_headers, sip_amount=None)
    a_new_nav_on_5_july(feed)
    during_fetch(monkeypatch, "fetch_nav_by_fund_name", lambda: db.update_mutual_fund(
        fund["id"], fund["user_id"], {"folio_number": "F-2"}))
    body = refresh(client, auth_headers, fund["id"], "post")
    assert (body["fund"]["folio_number"], body["fund"]["current_nav"], body["fund"]["current_value"]) == (
        "F-2", 25, 100 * 25)


@pytest.mark.parametrize("how", REFRESH_PATHS)
def test_a_fund_deleted_while_refreshing_is_not_found(client, auth_headers, feed, monkeypatch, how):
    import database as db

    fund = create(client, auth_headers)
    other = create(client, auth_headers, fund_name="Other Index Fund")
    a_new_nav_on_5_july(feed)
    during_fetch(monkeypatch, "fetch_history", lambda: db.delete_mutual_fund(fund["id"], fund["user_id"]))
    if how == "post":
        resp = client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=auth_headers)
        assert resp.status_code == 404 and resp.json()["detail"] == "Mutual fund not found"
    else:
        listed = client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers).json()
        assert [f["id"] for f in listed] == [other["id"]]
        assert listed[0]["sip_priced_through"] == "2026-07-06"  # the other fund is refreshed as usual
    assert db.get_mutual_fund_by_id(fund["id"], fund["user_id"]) is None


def test_refresh_reports_an_error_when_nothing_can_be_fetched(client, auth_headers, feed):
    plain = create(client, auth_headers, sip_amount=None)
    sip = create(client, auth_headers)
    feed["up"] = False
    for fund in (plain, sip):
        body = client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=auth_headers).json()
        assert body["status"] == "error"


def test_a_failed_name_lookup_is_not_repeated_to_find_a_scheme_code(client, auth_headers, feed, monkeypatch):
    """A fund saved without a scheme code and a lookup that just failed: no second lookup before giving up."""
    feed["up"] = False
    fund = create(client, auth_headers)
    lookups = []

    async def failing_lookup(name):
        lookups.append(name)

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", failing_lookup)
    client.post(f"/api/mutual-funds/{fund['id']}/refresh-nav", headers=auth_headers)
    assert len(lookups) == 1


def test_a_new_fund_stores_sip_pricing_only_when_it_has_some(client, auth_headers, feed):
    """So an export holds what a restore keeps: restore omits pricing that was never set."""
    feed["up"] = False
    create(client, auth_headers)  # a SIP that couldn't be priced
    create(client, auth_headers, sip_amount=None)
    stored = client.get("/api/export", headers=auth_headers).json()["mutual_funds"]
    assert len(stored) == 2
    assert not any(key in fund for fund in stored for key in ("sip_units", "sip_invested", "sip_priced_through"))


def test_a_view_value_beyond_the_input_limit_is_still_returned(client, auth_headers, feed):
    """The view's numbers aren't stored, so the input cap on stored values must not turn a response into a 500."""
    feed["up"] = False  # unpriced: ten weekly installments of 1e15 at cost
    create(client, auth_headers, sip_amount=1e15, sip_frequency="weekly", sip_day=None)
    resp = client.get("/api/mutual-funds", headers=auth_headers)
    assert resp.status_code == 200
    fund = resp.json()[0]
    assert fund["current_value"] > 1e15 and fund["total_invested"] > 1e15
    assert client.get("/api/mutual-funds-summary", headers=auth_headers).status_code == 200


# ---------- NAV history from mfapi.in ----------

MFAPI = {"meta": {"scheme_name": "Test Index Fund"},
         "data": [{"date": "05-06-2026", "nav": "20.00000"}, {"date": "05-05-2026", "nav": "12.50000"},
                  {"date": "01-04-2026", "nav": "10.00000"}]}


@pytest.fixture
def mfapi(monkeypatch):
    """Serve canned mfapi.in documents by scheme code and record every request."""
    nav_service._history_cache.clear()
    state = {"documents": {}, "calls": []}

    async def get_history_json(code):
        state["calls"].append(code)
        return state["documents"].get(code)

    monkeypatch.setattr(nav_service, "_get_history_json", get_history_json)
    yield state
    nav_service._history_cache.clear()


def test_history_is_parsed_from_an_mfapi_payload(mfapi):
    mfapi["documents"]["100001"] = MFAPI
    assert asyncio.run(nav_service.fetch_history("100001")) == [
        (date(2026, 4, 1), 10.0), (date(2026, 5, 5), 12.5), (date(2026, 6, 5), 20.0)]


def test_history_is_cached(mfapi):
    mfapi["documents"]["100001"] = MFAPI
    first = asyncio.run(nav_service.fetch_history("100001"))
    first.clear()  # a caller changing its copy must not change the cache
    second = asyncio.run(nav_service.fetch_history("100001"))
    assert len(second) == 3
    assert mfapi["calls"] == ["100001"]


def test_a_failed_history_fetch_is_not_cached(mfapi):
    assert asyncio.run(nav_service.fetch_history("100001")) is None
    mfapi["documents"]["100001"] = MFAPI
    assert len(asyncio.run(nav_service.fetch_history("100001"))) == 3
    assert mfapi["calls"] == ["100001", "100001"]


def test_a_history_without_usable_rows_is_not_cached(mfapi):
    mfapi["documents"]["100001"] = {"data": [{"date": "not a date", "nav": "x"}]}
    assert asyncio.run(nav_service.fetch_history("100001")) is None
    assert nav_service._history_cache == {}


@pytest.mark.parametrize("code", ["", None, "abc", "../search", "100001/x", "١٢٣٤٥٦"])
def test_a_non_numeric_scheme_code_is_never_requested(mfapi, code):
    assert asyncio.run(nav_service.fetch_history(code)) is None
    assert mfapi["calls"] == []
