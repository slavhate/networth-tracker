"""Mutual fund SIPs: fields, installment schedule, pricing at each installment's NAV, the fund's view."""
from datetime import date

import pytest
from pydantic import ValidationError

import valuation
from models import MutualFundCreate, MutualFundRestore

HISTORY = [(date(2026, 4, 1), 10.0), (date(2026, 4, 5), 10.0), (date(2026, 5, 5), 12.5), (date(2026, 6, 5), 20.0)]


def fund(**extra):
    row = {"fund_name": "Test Index Fund", "amc": "Test AMC", "category": "index", "units": 100.0,
           "invested_amount": 1000.0, "current_value": 1000.0, "current_nav": 10.0,
           "sip_amount": 1000.0, "sip_frequency": "monthly", "sip_day": 5,
           "sip_start_date": "2026-04-05", "holdings_date": "2026-04-01"}
    row.update(extra)
    return row


# ---------- fields ----------

def test_sip_fields_are_accepted():
    created = MutualFundCreate(**fund())
    assert (created.sip_frequency, created.sip_day, created.holdings_date) == ("monthly", 5, "2026-04-01")


@pytest.mark.parametrize("bad", [{"sip_frequency": "daily"}, {"sip_day": 0}, {"sip_day": 32},
                                 {"sip_start_date": "2026-02-30"}])
def test_sip_field_bounds(bad):
    with pytest.raises(ValidationError):
        MutualFundCreate(**fund(**bad))


def test_sip_end_date_must_not_be_before_the_start():
    with pytest.raises(ValidationError) as exc:
        MutualFundCreate(**fund(sip_end_date="2026-04-01"))
    assert "SIP end date must be on or after its start date" in str(exc.value)


def test_restore_keeps_sip_pricing_within_bounds():
    restored = MutualFundRestore(**fund(sip_units=230.0, sip_invested=3000.0, sip_priced_through="2026-06-10"))
    assert (restored.sip_units, restored.sip_priced_through) == (230.0, "2026-06-10")
    with pytest.raises(ValidationError):
        MutualFundRestore(**fund(sip_units=-1))


# ---------- schedule ----------

def test_monthly_installments_on_the_sip_day():
    assert valuation.sip_installments(fund(), date(2026, 4, 1), date(2026, 6, 10)) == [
        (date(2026, 4, 5), 1000), (date(2026, 5, 5), 1000), (date(2026, 6, 5), 1000)]


def test_the_sip_day_is_clamped_to_short_months():
    row = fund(sip_day=31, sip_start_date="2026-01-31")
    assert [d for d, _ in valuation.sip_installments(row, date(2026, 1, 1), date(2026, 3, 31))] == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]


def test_quarterly_installments_every_third_month_from_the_start():
    row = fund(sip_frequency="quarterly", sip_day=15, sip_start_date="2026-01-15")
    assert [d for d, _ in valuation.sip_installments(row, date(2026, 1, 1), date(2026, 8, 1))] == [
        date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15)]


def test_weekly_installments_every_seven_days_from_the_start():
    row = fund(sip_frequency="weekly", sip_day=None, sip_start_date="2026-04-01")
    assert [d for d, _ in valuation.sip_installments(row, date(2026, 3, 31), date(2026, 4, 20))] == [
        date(2026, 4, 1), date(2026, 4, 8), date(2026, 4, 15)]


def test_installments_respect_the_start_end_and_after_dates():
    row = fund(sip_day=1, sip_start_date="2026-04-10", sip_end_date="2026-07-01")
    assert [d for d, _ in valuation.sip_installments(row, date(2026, 5, 1), date(2026, 9, 1))] == [
        date(2026, 6, 1), date(2026, 7, 1)]  # 1 Apr is before the start, 1 May is not after `after`


@pytest.mark.parametrize("extra", [{"sip_amount": None}, {"sip_amount": 0}, {"sip_start_date": None}])
def test_no_installments_without_a_sip(extra):
    assert valuation.sip_installments(fund(**extra), date(2026, 1, 1), date(2026, 12, 31)) == []


# ---------- pricing ----------

def test_each_installment_buys_units_at_its_nav():
    priced = valuation.sip_price(fund(), HISTORY, date(2026, 6, 10))
    # 1,000 at 10 (5 Apr) → 100; at 12.5 (5 May) → 80; at 20 (5 Jun) → 50
    assert priced == {"sip_units": 230, "sip_invested": 3000, "sip_priced_through": "2026-06-10",
                      "current_nav": 20, "current_value": 6600}


def test_pricing_is_all_or_nothing():
    late = [(date(2026, 4, 6), 10.0), (date(2026, 6, 5), 20.0)]  # no NAV on or before 5 Apr
    assert valuation.sip_price(fund(), late, date(2026, 6, 10)) is None
    assert valuation.sip_price(fund(), [], date(2026, 6, 10)) is None
    assert valuation.sip_price(fund(holdings_date=None), HISTORY, date(2026, 6, 10)) is None


# ---------- view ----------

def test_priced_view_counts_later_installments_at_cost():
    row = fund(**valuation.sip_price(fund(), HISTORY, date(2026, 6, 10)))
    assert valuation.sip_priced(row)
    view = valuation.fund_view(row, date(2026, 6, 10))
    assert (view["current_value"], view["total_units"], view["total_invested"]) == (6600, 330, 4000)
    later = valuation.fund_view(row, date(2026, 7, 6))  # 5 Jul came after pricing
    assert (later["current_value"], later["total_units"], later["total_invested"]) == (7600, 330, 5000)


def test_unpriced_view_counts_installments_at_cost():
    view = valuation.fund_view(fund(), date(2026, 6, 10))
    assert (view["current_value"], view["total_units"], view["total_invested"]) == (4000, 100, 4000)


def test_view_without_a_sip_is_the_stored_fund():
    view = valuation.fund_view(fund(sip_amount=None), date(2026, 6, 10))
    assert (view["current_value"], view["total_units"], view["total_invested"]) == (1000, 100, 1000)


def test_dashboard_totals_include_sip_units():
    row = {**fund(**valuation.sip_price(fund(), HISTORY, date(2026, 6, 10))), "id": "f1"}
    totals = valuation.portfolio_totals([], [], [], [row], [], None, date(2026, 6, 10))
    assert totals["assets_by_category"]["mutual_funds"] == 6600
    assert totals["assets_by_class"] == {"equity": 6600}


def test_priced_view_does_not_count_installments_the_holdings_already_include():
    # Holdings are dated 20 Jun but the SIP was priced on 10 Jun: the 15 Jun installment is in the holdings
    row = fund(sip_day=15, sip_start_date="2026-04-15", holdings_date="2026-06-20")
    row.update(valuation.sip_price(row, HISTORY, date(2026, 6, 10)))
    assert (row["sip_units"], row["sip_invested"]) == (0, 0)
    view = valuation.fund_view(row, date(2026, 7, 20))  # only 15 Jul comes after both dates
    assert (view["current_value"], view["total_units"], view["total_invested"]) == (100 * 20 + 1000, 100, 2000)


def test_a_fund_row_without_current_value_counts_as_zero():
    row = {key: value for key, value in fund(sip_amount=None).items() if key != "current_value"}
    assert valuation.fund_view(row, date(2026, 6, 10))["total_units"] == 100
    totals = valuation.portfolio_totals([], [], [], [row], [], None, date(2026, 6, 10))
    assert totals["total_assets"] == 0
    assert "mutual_funds" not in totals["assets_by_category"]
