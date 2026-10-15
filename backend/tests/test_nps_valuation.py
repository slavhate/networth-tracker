"""NPS: contribution schedule, value with and without NAVs, pricing from NAV histories, asset classes."""
from datetime import date

import pytest

import valuation

E = "TEST PENSION FUND SCHEME E - TIER I"
C = "TEST PENSION FUND SCHEME C - TIER I"
G = "TEST PENSION FUND SCHEME G - TIER I"


def nps(**extra):
    return {"category": "nps", "value": 100000.0, "valuation_date": "2026-03-31", **extra}


def schemes(*rows):
    return [{"scheme_code": code, "scheme_name": name, "allocation_pct": pct, "units": units}
            for code, name, pct, units in rows]


HISTORIES = {
    "SM900001": [(date(2026, 3, 31), 20.0), (date(2026, 4, 1), 25.0), (date(2026, 5, 1), 40.0)],
    "SM900002": [(date(2026, 3, 30), 10.0), (date(2026, 4, 1), 10.0), (date(2026, 5, 1), 12.0)],
}
TWO = schemes(("SM900001", E, 50, None), ("SM900002", C, 50, None))


# ---------- contribution schedule ----------

def test_contributions_start_the_month_after_the_balance_date():
    asset = nps(monthly_contribution=5000)
    assert valuation.nps_contributions(asset, date(2026, 3, 31), date(2026, 6, 1)) == [
        (date(2026, 4, 1), 5000), (date(2026, 5, 1), 5000), (date(2026, 6, 1), 5000)]


def test_a_balance_dated_the_first_already_includes_that_months_contribution():
    asset = nps(monthly_contribution=5000)
    assert valuation.nps_contributions(asset, date(2026, 3, 1), date(2026, 4, 30)) == [(date(2026, 4, 1), 5000)]


def test_own_contribution_is_paid_in_march_unless_another_month_is_chosen():
    march = nps(yearly_contribution=50000)
    assert valuation.nps_contributions(march, date(2026, 1, 15), date(2027, 4, 1)) == [
        (date(2026, 3, 1), 50000), (date(2027, 3, 1), 50000)]
    december = nps(yearly_contribution=50000, yearly_contribution_month=12)
    assert valuation.nps_contributions(december, date(2026, 1, 15), date(2027, 4, 1)) == [(date(2026, 12, 1), 50000)]


def test_contributions_on_the_same_day_are_combined():
    asset = nps(monthly_contribution=5000, yearly_contribution=50000, yearly_contribution_month=4)
    assert valuation.nps_contributions(asset, date(2026, 3, 31), date(2026, 5, 1)) == [
        (date(2026, 4, 1), 55000), (date(2026, 5, 1), 5000)]


def test_no_contributions_when_the_period_is_empty():
    asset = nps(monthly_contribution=5000)
    assert valuation.nps_contributions(asset, date(2026, 6, 1), date(2026, 5, 1)) == []


# ---------- value without NAVs ----------

def test_value_without_navs_adds_contributions_at_cost():
    asset = nps(monthly_contribution=5000, yearly_contribution=50000)
    # 1 Apr … 1 Oct = 7 employer contributions; next March not reached
    assert valuation.asset_current_value(asset, date(2026, 10, 14)) == 135000


def test_value_without_navs_grows_everything_at_the_expected_return():
    asset = nps(value=100000.0, valuation_date="2026-01-01", annual_change_rate=10, monthly_contribution=1000)
    on = date(2026, 3, 1)
    grow = lambda amount, start: amount * 1.1 ** ((on - start).days / 365.25)
    expected = grow(100000, date(2026, 1, 1)) + grow(1000, date(2026, 2, 1)) + grow(1000, date(2026, 3, 1))
    assert valuation.asset_current_value(asset, on) == pytest.approx(expected)


def test_nps_without_contributions_behaves_as_before():
    assert valuation.asset_current_value(nps(), date(2026, 10, 14)) == 100000
    grown = nps(annual_change_rate=8)
    years = (date(2026, 10, 14) - date(2026, 3, 31)).days / 365.25
    assert valuation.asset_current_value(grown, date(2026, 10, 14)) == pytest.approx(100000 * 1.08 ** years)


# ---------- NAV lookup and pricing ----------

def test_nav_on_or_before():
    history = [(date(2026, 4, 1), 10.0), (date(2026, 4, 3), 12.0)]
    assert valuation.nav_on_or_before(history, date(2026, 4, 2)) == (date(2026, 4, 1), 10.0)
    assert valuation.nav_on_or_before(history, date(2026, 4, 3)) == (date(2026, 4, 3), 12.0)
    assert valuation.nav_on_or_before(history, date(2026, 3, 31)) is None
    assert valuation.nav_on_or_before([], date(2026, 4, 3)) is None


def test_pricing_splits_the_balance_and_buys_units_with_each_contribution():
    asset = nps(monthly_contribution=6000, nps_schemes=TWO)
    priced = valuation.nps_price(asset, HISTORIES, date(2026, 5, 10))
    assert priced["nps_priced_through"] == "2026-05-10"
    e, c = priced["nps_schemes"]
    # E: 50,000 at 20 → 2,500 units; 3,000 at 25 (1 Apr) → 120; 3,000 at 40 (1 May) → 75
    assert (e["base_units"], e["contribution_units"], e["nav"], e["nav_date"]) == (2500, 195, 40, "2026-05-01")
    # C: 50,000 at 10 (the NAV on or before 31 Mar is 30 Mar's) → 5,000; 3,000 at 10 → 300; 3,000 at 12 → 250
    assert (c["base_units"], c["contribution_units"], c["nav"]) == (5000, 550, 12)
    assert e["scheme_code"] == "SM900001" and e["allocation_pct"] == 50 and e["units"] is None


def test_statement_units_are_used_as_they_are():
    asset = nps(nps_schemes=schemes(("SM900001", E, 50, 3000.0), ("SM900002", C, 50, 4000.0)))
    e, c = valuation.nps_price(asset, HISTORIES, date(2026, 5, 10))["nps_schemes"]
    assert (e["base_units"], c["base_units"]) == (3000, 4000)


def test_pricing_is_all_or_nothing():
    late_start = {**HISTORIES, "SM900002": [(date(2026, 4, 1), 10.0)]}  # no NAV on or before the balance date
    asset = nps(nps_schemes=TWO)
    assert valuation.nps_price(asset, late_start, date(2026, 5, 10)) is None
    assert valuation.nps_price(asset, {"SM900001": HISTORIES["SM900001"]}, date(2026, 5, 10)) is None
    assert valuation.nps_price(nps(), HISTORIES, date(2026, 5, 10)) is None  # no schemes
    assert valuation.nps_price(nps(valuation_date=None, nps_schemes=TWO), HISTORIES, date(2026, 5, 10)) is None


def test_pricing_beyond_the_bounds_leaves_the_asset_unpriced():
    tiny = {"SM900001": [(date(2026, 3, 1), 0.0001)]}
    asset = nps(value=1e15, nps_schemes=schemes(("SM900001", E, 100, None)))
    assert valuation.nps_price(asset, tiny, date(2026, 5, 10)) is None


def test_a_latest_nav_beyond_the_bound_leaves_the_asset_unpriced():
    # 0.25 units at a NAV of 2e15 are worth less than the cap, but the NAV itself can't be stored (restore bounds it)
    asset = nps(nps_schemes=schemes(("SM900001", E, 100, 0.25)))
    histories = {"SM900001": [(date(2026, 3, 31), 20.0), (date(2026, 5, 1), 2e15)]}
    assert valuation.nps_price(asset, histories, date(2026, 5, 10)) is None
    assert valuation.nps_price_problem(asset, histories, date(2026, 5, 10)) == f"{E} has a NAV too large to use"


def test_the_pricing_problem_names_the_scheme_and_the_date_it_has_no_nav_for():
    late_start = {**HISTORIES, "SM900002": [(date(2026, 4, 1), 10.0)]}
    asset = nps(nps_schemes=TWO)
    assert valuation.nps_price_problem(asset, late_start, date(2026, 5, 10)) == (
        f"{C} has no NAV on or before 31 Mar 2026; use a later balance date")
    assert valuation.nps_price_problem(asset, HISTORIES, date(2026, 5, 10)) is None


def test_a_future_balance_date_keeps_the_contributions_before_it_out_of_the_value():
    # Priced on 10 May with a balance dated 15 Jul: that balance already holds the 1 Jun and 1 Jul contributions
    asset = nps(valuation_date="2026-07-15", monthly_contribution=6000, nps_schemes=TWO)
    asset.update(valuation.nps_price(asset, HISTORIES, date(2026, 5, 10)))
    priced = valuation.asset_current_value(asset, date(2026, 5, 10))
    assert valuation.asset_current_value(asset, date(2026, 7, 31)) == pytest.approx(priced)
    assert valuation.asset_current_value(asset, date(2026, 8, 1)) == pytest.approx(priced + 6000)


def test_a_future_balance_date_keeps_the_contributions_before_it_out_of_the_classes():
    asset = nps(valuation_date="2026-07-15", monthly_contribution=6000,
                nps_schemes=schemes(("SM900001", E, 100, 1000.0), ("SM900002", C, 0, 1000.0)))
    asset.update(valuation.nps_price(asset, HISTORIES, date(2026, 5, 10)))
    # E: 1,000 × 40 + 1 Aug's 6,000 at cost (all new money goes to E); C: 1,000 × 12
    assert valuation.asset_class_shares(asset, date(2026, 8, 1)) == pytest.approx(
        {"equity": 46000 / 58000, "debt": 12000 / 58000})


def test_priced_value_uses_navs_and_counts_later_contributions_at_cost():
    asset = nps(monthly_contribution=6000, nps_schemes=TWO)
    asset.update(valuation.nps_price(asset, HISTORIES, date(2026, 5, 10)))
    assert valuation.nps_priced(asset)
    assert valuation.asset_current_value(asset, date(2026, 5, 10)) == pytest.approx(2695 * 40 + 5550 * 12)
    # 1 Jun's contribution came after pricing: at cost until the next refresh
    assert valuation.asset_current_value(asset, date(2026, 6, 2)) == pytest.approx(2695 * 40 + 5550 * 12 + 6000)


def test_asset_view_shows_units_and_value_per_scheme_when_priced():
    asset = nps(monthly_contribution=6000, nps_schemes=TWO)
    unpriced = valuation.asset_view(asset, date(2026, 5, 10))
    assert "current_units" not in unpriced["nps_schemes"][0]
    asset.update(valuation.nps_price(asset, HISTORIES, date(2026, 5, 10)))
    e, c = valuation.asset_view(asset, date(2026, 5, 10))["nps_schemes"]
    assert (e["current_units"], e["current_value"]) == (2695, 107800)
    assert (c["current_units"], c["current_value"]) == (5550, 66600)


def test_scheme_inputs_drop_priced_fields():
    priced = [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100, "units": None, "nav": 1.0,
               "nav_date": "2026-04-01", "base_units": 1.0, "contribution_units": 0.0}]
    assert valuation.nps_scheme_inputs(priced) == [
        {"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100, "units": None}]


# ---------- asset classes ----------

@pytest.mark.parametrize("name, classes", [
    (E, {"equity": 1}), (C, {"debt": 1}), (G, {"debt": 1}),
    ("TEST PENSION FUND SCHEME A - TIER I", {"other": 1}),
    ("TEST PENSION FUND  SCHEME C - TIER II", {"debt": 1}),
    ("TEST PENSION FUND SCHEME - CENTRAL GOVT", {"equity": 0.5, "debt": 0.5}),
    ("TEST PENSION FUND - NPS LITE SCHEME GOVT. PATTERN", {"equity": 0.5, "debt": 0.5}),
    ("TEST PENSION FUND SCHEME TAX SAVER TIER II", {"equity": 0.5, "debt": 0.5}),
])
def test_scheme_classes_come_from_the_name(name, classes):
    assert valuation.nps_scheme_classes(name) == classes


def test_unpriced_classes_follow_the_allocation():
    asset = nps(nps_schemes=schemes(("SM900001", E, 75, None), ("SM900002", C, 15, None), ("SM900003", G, 10, None)))
    assert valuation.asset_class_shares(asset, date(2026, 5, 10)) == pytest.approx({"equity": 0.75, "debt": 0.25})


def test_priced_classes_follow_each_schemes_value():
    asset = nps(monthly_contribution=6000, nps_schemes=TWO)
    asset.update(valuation.nps_price(asset, HISTORIES, date(2026, 5, 10)))
    total = 107800 + 66600
    assert valuation.asset_class_shares(asset, date(2026, 5, 10)) == pytest.approx(
        {"equity": 107800 / total, "debt": 66600 / total})


def test_nps_without_schemes_keeps_the_even_split():
    assert valuation.asset_class_shares(nps(), date(2026, 5, 10)) == {"equity": 0.5, "debt": 0.5}


def test_dashboard_classes_use_the_schemes():
    asset = {**nps(nps_schemes=schemes(("SM900001", E, 75, None), ("SM900002", G, 25, None))), "id": "a1"}
    totals = valuation.portfolio_totals([asset], [], [], [], [], None, date(2026, 5, 10))
    assert totals["assets_by_class"] == {"equity": 75000, "debt": 25000}
