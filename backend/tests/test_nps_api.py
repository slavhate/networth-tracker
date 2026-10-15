"""NPS through the API: pricing on save, refresh, scheme list, restore, dashboard classes, demo data."""
import asyncio
import io
import json
from datetime import date

import pytest

import nps_service

E = "TEST PENSION FUND SCHEME E - TIER I"
C = "TEST PENSION FUND SCHEME C - TIER I"
HISTORIES = {
    "SM900001": [(date(2026, 3, 31), 20.0), (date(2026, 4, 1), 25.0), (date(2026, 5, 1), 40.0)],
    "SM900002": [(date(2026, 3, 30), 10.0), (date(2026, 4, 1), 10.0), (date(2026, 5, 1), 12.0)],
}
SCHEMES = [{"scheme_code": "SM900001", "scheme_name": E, "pfm_name": "Test", "nav": 40.0, "nav_date": "2026-05-01"},
           {"scheme_code": "SM900002", "scheme_name": C, "pfm_name": "Test", "nav": 12.0, "nav_date": "2026-05-01"}]


def nps_payload(**extra):
    return {"name": "NPS Tier I", "category": "nps", "value": 100000, "valuation_date": "2026-03-31",
            "monthly_contribution": 6000, "description": None,
            "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 50},
                            {"scheme_code": "SM900002", "scheme_name": C, "allocation_pct": 50}], **extra}


@pytest.fixture
def navs(monkeypatch, frozen_today):
    """NAV feed for the made-up schemes; set state["up"] = False to make it unavailable."""
    frozen_today["date"] = date(2026, 5, 10)
    state = {"up": True, "histories": dict(HISTORIES), "calls": 0}

    async def fetch_history(code):
        state["calls"] += 1
        return state["histories"].get(code) if state["up"] else None

    async def list_schemes():
        return SCHEMES if state["up"] else None

    monkeypatch.setattr(nps_service, "fetch_history", fetch_history)
    monkeypatch.setattr(nps_service, "list_schemes", list_schemes)
    state["today"] = frozen_today
    return state


def create(client, headers, **extra):
    resp = client.post("/api/assets", json=nps_payload(**extra), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_prices_the_schemes(client, auth_headers, navs):
    asset = create(client, auth_headers)
    assert asset["nps_priced_through"] == "2026-05-10"
    e, c = asset["nps_schemes"]
    assert (e["base_units"], e["contribution_units"], e["nav"], e["current_units"]) == (2500, 195, 40, 2695)
    assert (c["base_units"], c["contribution_units"], c["nav"], c["current_value"]) == (5000, 550, 12, 66600)
    assert asset["current_value"] == 174400


def test_create_while_navs_unavailable_saves_unpriced(client, auth_headers, navs):
    navs["up"] = False
    asset = create(client, auth_headers)
    assert asset["nps_priced_through"] is None
    assert all(s["nav"] is None and s["base_units"] is None for s in asset["nps_schemes"])
    assert asset["current_value"] == 112000  # balance + 1 Apr and 1 May contributions at cost


def test_unpriced_create_stores_no_priced_through_key(client, auth_headers, navs):
    import database as db

    navs["up"] = False
    asset = create(client, auth_headers)
    stored = db.get_asset_by_id(asset["id"], asset["user_id"])
    assert "nps_priced_through" not in stored  # looks like a freshly created row, so a backup round trip is exact
    assert [s["nav"] for s in client.get("/api/assets", headers=auth_headers).json()[0]["nps_schemes"]] == [None, None]


def test_failed_reprice_stores_a_null_priced_through(client, auth_headers, navs):
    import database as db

    asset = create(client, auth_headers)
    assert db.get_asset_by_id(asset["id"], asset["user_id"])["nps_priced_through"] == "2026-05-10"
    navs["up"] = False
    client.put(f"/api/assets/{asset['id']}", json=nps_payload(value=200000), headers=auth_headers)
    stored = db.get_asset_by_id(asset["id"], asset["user_id"])
    assert "nps_priced_through" in stored and stored["nps_priced_through"] is None
    assert all("nav" not in s for s in stored["nps_schemes"])  # the schemes are back to what was entered


def test_name_only_update_keeps_pricing_without_fetching(client, auth_headers, navs):
    asset = create(client, auth_headers)
    calls = navs["calls"]
    resp = client.put(f"/api/assets/{asset['id']}", json=nps_payload(name="Renamed"), headers=auth_headers)
    assert resp.status_code == 200
    assert navs["calls"] == calls
    assert resp.json()["nps_schemes"] == asset["nps_schemes"]
    assert resp.json()["nps_priced_through"] == "2026-05-10"


def test_contribution_change_prices_again(client, auth_headers, navs):
    asset = create(client, auth_headers)
    resp = client.put(f"/api/assets/{asset['id']}", json=nps_payload(monthly_contribution=12000),
                      headers=auth_headers)
    e = resp.json()["nps_schemes"][0]
    assert e["contribution_units"] == 390  # twice the contribution, twice the units


def test_failed_pricing_on_update_clears_old_pricing(client, auth_headers, navs):
    asset = create(client, auth_headers)
    navs["up"] = False
    resp = client.put(f"/api/assets/{asset['id']}", json=nps_payload(value=200000), headers=auth_headers)
    body = resp.json()
    assert body["nps_priced_through"] is None and body["nps_schemes"][0]["nav"] is None
    assert body["current_value"] == 212000


def test_refresh_uses_the_latest_navs(client, auth_headers, navs):
    asset = create(client, auth_headers)
    navs["histories"]["SM900001"] = HISTORIES["SM900001"] + [(date(2026, 6, 1), 50.0)]
    navs["histories"]["SM900002"] = HISTORIES["SM900002"] + [(date(2026, 6, 1), 13.0)]
    navs["today"]["date"] = date(2026, 6, 2)
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["nps_priced_through"] == "2026-06-02"
    assert body["nps_schemes"][0]["nav"] == 50 and body["nps_schemes"][0]["nav_date"] == "2026-06-01"


def test_refresh_failure_keeps_stored_data(client, auth_headers, navs):
    asset = create(client, auth_headers)
    navs["up"] = False
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Couldn't fetch NPS NAVs right now"
    again = client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()
    assert again["nps_schemes"] == asset["nps_schemes"]


def test_refresh_keeps_an_edit_made_while_fetching(client, auth_headers, navs, monkeypatch):
    import database as db

    asset = create(client, auth_headers)
    before = db.get_asset_by_id(asset["id"], asset["user_id"])
    navs["histories"]["SM900001"] = HISTORIES["SM900001"] + [(date(2026, 6, 1), 50.0)]
    navs["histories"]["SM900002"] = HISTORIES["SM900002"] + [(date(2026, 6, 1), 13.0)]
    navs["today"]["date"] = date(2026, 6, 2)
    edits = []

    async def fetch_history(code):
        if not edits:  # the owner saves a new contribution while the first NAV is on its way
            edits.append(db.update_asset(asset["id"], asset["user_id"], {"monthly_contribution": 9000}))
        return navs["histories"][code]

    monkeypatch.setattr(nps_service, "fetch_history", fetch_history)
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 200
    stored = db.get_asset_by_id(asset["id"], asset["user_id"])
    for row in (resp.json(), stored):
        assert row["monthly_contribution"] == 9000
        assert row["nps_priced_through"] == "2026-05-10"  # the pricing from before stays; it was not overwritten
    assert [{k: s[k] for k in ("scheme_code", "allocation_pct", "nav", "base_units")} for s in stored["nps_schemes"]] \
        == [{k: s[k] for k in ("scheme_code", "allocation_pct", "nav", "base_units")} for s in before["nps_schemes"]]


def test_refresh_of_an_asset_deleted_while_fetching_is_not_found(client, auth_headers, navs, monkeypatch):
    import database as db

    asset = create(client, auth_headers)

    async def fetch_history(code):
        db.delete_asset(asset["id"], asset["user_id"])
        return navs["histories"][code]

    monkeypatch.setattr(nps_service, "fetch_history", fetch_history)
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 404 and resp.json()["detail"] == "Asset not found"
    assert client.get("/api/assets", headers=auth_headers).json() == []


def test_an_update_of_an_asset_deleted_while_fetching_is_not_found(client, auth_headers, navs, monkeypatch):
    import database as db

    asset = create(client, auth_headers)

    async def fetch_history(code):
        db.delete_asset(asset["id"], asset["user_id"])
        return navs["histories"][code]

    monkeypatch.setattr(nps_service, "fetch_history", fetch_history)
    resp = client.put(f"/api/assets/{asset['id']}", json=nps_payload(value=200000), headers=auth_headers)
    assert resp.status_code == 404 and resp.json()["detail"] == "Asset not found"
    assert client.get("/api/assets", headers=auth_headers).json() == []


# ---------- NAVs that were fetched but can't price the asset: not the source's fault ----------

LATE = f"{C} has no NAV on or before 31 Mar 2026; use a later balance date"


def navs_start_after_the_balance_date(navs):
    navs["histories"]["SM900002"] = [(date(2026, 4, 1), 10.0), (date(2026, 5, 1), 12.0)]


def test_create_with_navs_that_start_after_the_balance_date_saves_unpriced_and_says_why(client, auth_headers, navs):
    navs_start_after_the_balance_date(navs)
    resp = client.post("/api/assets", json=nps_payload(), headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["nps_priced_through"] is None
    assert json.loads(resp.headers["x-warnings"]) == [f"Couldn't price NPS Tier I: {LATE}."]


def test_refresh_with_navs_that_start_after_the_balance_date_is_unprocessable(client, auth_headers, navs):
    navs_start_after_the_balance_date(navs)
    asset = create(client, auth_headers)
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["detail"] == LATE
    assert "npsnav.in" not in resp.headers.get("x-warnings", "")  # the source answered: no "source down" warning


def test_refresh_needs_an_nps_asset_with_schemes(client, auth_headers, navs):
    cash = client.post("/api/assets", json={"name": "Cash", "category": "cash", "value": 10},
                       headers=auth_headers).json()
    plain = client.post("/api/assets", json={"name": "NPS", "category": "nps", "value": 10},
                        headers=auth_headers).json()
    for asset in (cash, plain):
        assert client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers).status_code == 400
    assert client.post("/api/assets/missing/refresh-nav", headers=auth_headers).status_code == 404


def test_scheme_list(client, auth_headers, navs):
    resp = client.get("/api/nps/schemes", headers=auth_headers)
    assert resp.status_code == 200 and resp.json() == SCHEMES
    navs["up"] = False
    assert client.get("/api/nps/schemes", headers=auth_headers).status_code == 502
    assert client.get("/api/nps/schemes").status_code == 401


def test_invalid_allocation_is_rejected(client, auth_headers, navs):
    payload = nps_payload()
    payload["nps_schemes"][0]["allocation_pct"] = 40
    resp = client.post("/api/assets", json=payload, headers=auth_headers)
    assert resp.status_code == 422
    assert "Allocations must add up to 100%" in resp.text


def test_dashboard_classes_follow_the_schemes(client, auth_headers, navs):
    create(client, auth_headers)
    classes = client.get("/api/dashboard", headers=auth_headers).json()["assets_by_class"]
    assert classes == {"equity": 107800, "debt": 66600}


def _restore(client, headers, backup):
    files = {"file": ("backup.json", io.BytesIO(json.dumps(backup).encode()), "application/json")}
    return client.post("/api/restore", files=files, headers=headers)


def test_restore_round_trip_keeps_nps_pricing(client, auth_headers, navs):
    asset = create(client, auth_headers)
    backup = client.get("/api/export", headers=auth_headers).json()
    navs["up"] = False  # restore must not need the network
    assert _restore(client, auth_headers, backup).status_code == 200
    restored = client.get("/api/assets", headers=auth_headers).json()[0]
    assert restored["nps_schemes"] == asset["nps_schemes"]
    assert restored["nps_priced_through"] == "2026-05-10"


def test_restore_accepts_assets_without_nps_fields(client, auth_headers, navs):
    backup = client.get("/api/export", headers=auth_headers).json()
    backup["assets"] = [{"name": "Old NPS", "category": "nps", "value": 5000}]
    assert _restore(client, auth_headers, backup).status_code == 200
    assert client.get("/api/assets", headers=auth_headers).json()[0]["current_value"] == 5000


def test_demo_nps_asset_has_contributions_and_unpriced_schemes(client, monkeypatch, frozen_today):
    import main
    from config import settings
    import database as db

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())
    demo = db.get_user_by_username(settings.DEMO_USERNAME)
    nps = next(a for a in db.get_assets_by_user(demo["id"]) if a["category"] == "nps")
    assert nps["monthly_contribution"] and nps["yearly_contribution"] and nps["valuation_date"]
    assert len(nps["nps_schemes"]) == 3 and sum(s["allocation_pct"] for s in nps["nps_schemes"]) == 100
    assert not nps.get("nps_priced_through")
