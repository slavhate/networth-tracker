import asyncio
from datetime import date

import pytest

import exchange_service
import models
import valuation as v

D = date.fromisoformat


@pytest.mark.parametrize("start, end, expected", [
    ("2026-01-15", "2026-01-15", 0),
    ("2026-01-15", "2026-02-14", 0),
    ("2026-01-15", "2026-02-15", 1),
    ("2026-01-31", "2026-02-28", 1),
    ("2026-01-31", "2026-03-30", 1),
    ("2024-02-29", "2025-02-28", 12),
    ("2026-03-10", "2026-01-10", 0),
    ("2020-06-01", "2026-10-14", 76),
])
def test_months_between(start, end, expected):
    assert v.months_between(D(start), D(end)) == expected


@pytest.mark.parametrize("start, n, expected", [
    ("2026-01-31", 1, "2026-02-28"),
    ("2024-01-31", 1, "2024-02-29"),
    ("2026-11-15", 3, "2027-02-15"),
    ("2026-03-31", -1, "2026-02-28"),
])
def test_add_months(start, n, expected):
    assert v.add_months(D(start), n) == D(expected)


def test_asset_without_a_rate_keeps_its_value():
    assert v.asset_current_value({"value": 100, "annual_change_rate": None, "valuation_date": None}, D("2030-01-01")) == 100


def test_asset_appreciates_at_its_yearly_rate():
    asset = {"value": 1_000_000, "annual_change_rate": 5, "valuation_date": "2022-10-14"}
    assert v.asset_current_value(asset, D("2026-10-14")) == pytest.approx(1_215_506.25, abs=0.01)  # 1461 days = 4 years


def test_vehicle_depreciates():
    asset = {"value": 1_200_000, "annual_change_rate": -15, "valuation_date": "2022-10-14"}
    assert v.asset_current_value(asset, D("2026-10-14")) == pytest.approx(626_407.50, abs=0.01)


def test_asset_valued_in_the_future_keeps_its_value():
    asset = {"value": 500, "annual_change_rate": 10, "valuation_date": "2027-01-01"}
    assert v.asset_current_value(asset, D("2026-10-14")) == 500


def fd(**fields):
    return {"account_type": "fd", "balance": 100_000, "interest_rate": 7, "start_date": "2025-10-14",
            "maturity_date": None, "monthly_deposit": None, **fields}


def test_fd_compounds_quarterly():
    assert v.deposit_status(fd(), D("2026-10-14"))["current_value"] == pytest.approx(107_185.90, abs=0.01)


def test_fd_before_its_start_is_worth_its_principal():
    assert v.deposit_status(fd(start_date="2026-11-01"), D("2026-10-14"))["current_value"] == 100_000


def test_matured_fd_stops_growing():
    status = v.deposit_status(fd(maturity_date="2026-04-14"), D("2026-10-14"))
    expected = 100_000 * (1 + 7 / 400) ** (4 * 182 / 365)
    assert status["matured"] is True
    assert status["days_to_maturity"] == -183
    assert status["current_value"] == pytest.approx(expected, abs=0.01)
    assert status["maturity_value"] == pytest.approx(expected, abs=0.01)


def test_fd_without_a_rate_still_counts_down_to_maturity():
    status = v.deposit_status(fd(interest_rate=None, maturity_date="2026-11-13"), D("2026-10-14"))
    assert status == {"current_value": 100_000, "maturity_value": None, "matured": False, "days_to_maturity": 30}


def rd(**fields):
    return {"account_type": "rd", "balance": 0, "interest_rate": 7, "start_date": "2025-10-14",
            "maturity_date": "2026-10-14", "monthly_deposit": 1000, **fields}


def test_rd_matches_the_standard_indian_rd_formula():
    q = 7 / 400
    closed_form = 1000 * ((1 + q) ** (12 / 3) - 1) / (1 - (1 + q) ** (-1 / 3))
    status = v.deposit_status(rd(), D("2026-10-14"))
    assert status["maturity_value"] == pytest.approx(closed_form, rel=1e-3)
    assert status["current_value"] == status["maturity_value"]


def test_rd_without_a_rate_is_the_deposits_so_far():
    status = v.deposit_status(rd(interest_rate=None, start_date="2026-01-14", maturity_date=None), D("2026-10-14"))
    assert status["current_value"] == 10_000  # installments on Jan 14 … Oct 14


def test_rd_before_its_start_is_worth_nothing_yet():
    assert v.deposit_status(rd(start_date="2026-12-01", maturity_date="2027-12-01"), D("2026-10-14"))["current_value"] == 0


def test_savings_account_ignores_deposit_fields():
    account = {"account_type": "savings", "balance": 500, "interest_rate": 7, "start_date": "2025-01-01",
               "maturity_date": "2026-01-01", "monthly_deposit": None}
    assert v.deposit_status(account, D("2026-10-14")) == {
        "current_value": 500, "maturity_value": None, "matured": False, "days_to_maturity": None}


def test_upcoming_maturities_lists_due_and_matured_deposits_oldest_first():
    accounts = [
        {**fd(maturity_date="2026-10-24"), "id": "a", "bank_name": "Test Bank A"},
        {**rd(maturity_date="2026-10-09"), "id": "b", "bank_name": "Test Bank B"},
        {**fd(maturity_date="2027-01-12"), "id": "c", "bank_name": "Test Bank C"},
        {"id": "d", "bank_name": "Test Bank D", "account_type": "savings", "balance": 1, "maturity_date": None},
    ]
    due = v.upcoming_maturities(accounts, D("2026-10-14"))
    assert [(m["id"], m["days_to_maturity"]) for m in due] == [("b", -5), ("a", 10)]


def test_portfolio_totals_use_computed_values():
    totals = v.portfolio_totals(
        assets=[{"category": "vehicles", "value": 1_200_000, "annual_change_rate": -15, "valuation_date": "2022-10-14"}],
        liabilities=[{"category": "credit_card", "amount": 1_000}],
        bank_accounts=[fd()],
        mutual_funds=[{"current_value": 500}, {"current_value": None}],
        equities=[{"market": "NYSE", "current_value": 10}, {"market": "NSE", "current_value": 100}],
        usd_to_inr=80,
        on=D("2026-10-14"),
    )
    assert totals["assets_by_category"] == pytest.approx(
        {"vehicles": 626_407.50, "equities": 900, "bank_accounts": 107_185.90, "mutual_funds": 500}, abs=0.01)
    assert totals["total_assets"] == pytest.approx(626_407.50 + 900 + 107_185.90 + 500, abs=0.02)
    assert totals["total_liabilities"] == 1_000
    assert totals["net_worth"] == pytest.approx(totals["total_assets"] - 1_000)
    assert totals["liabilities_by_category"] == {"credit_card": 1_000}
    assert (totals["asset_count"], totals["liability_count"]) == (6, 1)


def test_usd_rate_is_only_fetched_for_us_holdings(monkeypatch):
    async def must_not_be_called():
        raise AssertionError("rate fetched without US holdings")

    monkeypatch.setattr(exchange_service, "fetch_usd_to_inr", must_not_be_called)

    assert asyncio.run(v.usd_rate_if_needed([{"market": "NSE"}, {"market": "BSE"}])) is None


LOAN = {"amount": 1_000_000, "interest_rate": 12, "emi": 88_848.79, "balance_date": "2026-01-15"}


def test_emi_for_tenure_matches_the_standard_formula():
    assert v.emi_for_tenure(1_000_000, 12, 12) == 88_848.79


def test_emi_for_tenure_without_interest_splits_evenly():
    assert v.emi_for_tenure(120_000, 0, 12) == 10_000


def test_outstanding_after_one_emi():
    status = v.loan_status(LOAN, D("2026-02-15"))
    assert status["amortized"] is True
    assert status["outstanding"] == pytest.approx(921_151.21, abs=0.01)
    assert status["months_remaining"] == 11
    assert status["payoff_date"] == "2027-01-15"
    assert status["next_emi_interest"] == pytest.approx(9_211.51, abs=0.01)
    assert status["next_emi_principal"] == pytest.approx(79_637.28, abs=0.01)
    assert status["interest_remaining"] == pytest.approx(56_185.48, abs=0.5)
    assert status["emi_too_low"] is False


def test_before_the_first_anniversary_nothing_is_paid_yet():
    status = v.loan_status(LOAN, D("2026-02-14"))
    assert status["outstanding"] == 1_000_000
    assert status["months_remaining"] == 12


def test_a_balance_date_in_the_future_leaves_the_balance_alone():
    status = v.loan_status({**LOAN, "balance_date": "2026-12-01"}, D("2026-10-14"))
    assert status["outstanding"] == 1_000_000
    assert status["months_remaining"] == 12


def test_paid_off_loan():
    status = v.loan_status({**LOAN, "balance_date": "2025-01-15"}, D("2026-02-01"))
    assert status == {
        "outstanding": 0.0, "amortized": True, "months_remaining": 0, "payoff_date": "2026-01-15",
        "interest_remaining": 0.0, "next_emi_interest": None, "next_emi_principal": None, "emi_too_low": False,
        "last_emi_date": "2026-01-15",
    }


def test_zero_rate_loan():
    status = v.loan_status({"amount": 120_000, "interest_rate": None, "emi": 10_000, "balance_date": "2026-01-15"},
                           D("2026-03-15"))
    assert status["outstanding"] == 100_000
    assert status["months_remaining"] == 10
    assert status["payoff_date"] == "2027-01-15"
    assert status["interest_remaining"] == 0


def test_emi_that_does_not_cover_the_interest():
    status = v.loan_status({**LOAN, "emi": 5_000}, D("2026-04-15"))
    assert status["emi_too_low"] is True
    assert status["outstanding"] == pytest.approx(1_015_150.50, abs=0.01)  # grows: 3 months of 1% interest minus 5,000
    assert (status["months_remaining"], status["payoff_date"], status["interest_remaining"]) == (None, None, None)
    assert (status["next_emi_interest"], status["next_emi_principal"]) == (None, None)


def test_a_payoff_beyond_100_years_is_not_projected():
    status = v.loan_status({**LOAN, "emi": 10_000.01}, D("2026-01-15"))
    assert status["emi_too_low"] is False
    assert (status["months_remaining"], status["payoff_date"], status["interest_remaining"]) == (None, None, None)
    assert status["next_emi_interest"] == 10_000


def test_liability_without_an_emi_is_not_amortized():
    status = v.loan_status({"amount": 50_000}, D("2026-10-14"))
    assert status["amortized"] is False
    assert status["outstanding"] == 50_000
    assert status["payoff_date"] is None
    assert status["last_emi_date"] is None


@pytest.mark.parametrize("on, expected", [
    ("2026-01-15", "2026-01-15"),  # the balance date itself: nothing paid yet
    ("2026-02-14", "2026-01-15"),  # before the first anniversary
    ("2026-02-15", "2026-02-15"),  # on an anniversary
    ("2026-05-20", "2026-05-15"),  # between anniversaries
])
def test_last_emi_date_is_the_last_anniversary_on_or_before_today(on, expected):
    assert v.loan_status(LOAN, D(on))["last_emi_date"] == expected


def test_last_emi_date_of_a_month_end_anchor_follows_short_months():
    loan = {**LOAN, "balance_date": "2026-01-31"}
    assert v.loan_status(loan, D("2026-02-28"))["last_emi_date"] == "2026-02-28"
    assert v.loan_status(loan, D("2026-03-30"))["last_emi_date"] == "2026-02-28"
    assert v.loan_status(loan, D("2026-03-31"))["last_emi_date"] == "2026-03-31"


def test_last_emi_date_is_set_for_a_loan_whose_emi_is_too_low():
    status = v.loan_status({**LOAN, "emi": 5_000}, D("2026-04-20"))
    assert status["emi_too_low"] is True
    assert status["last_emi_date"] == "2026-04-15"


def test_yearly_schedule():
    rows = v.loan_schedule(LOAN, D("2026-02-15"))
    assert [r["year"] for r in rows] == [2026, 2027]
    assert rows[0]["paid"] == pytest.approx(10 * 88_848.79, abs=0.01)  # Mar … Dec
    assert sum(r["principal"] for r in rows) == pytest.approx(921_151.21, abs=0.05)
    assert rows[-1]["closing_balance"] == 0


def test_schedule_of_a_manual_liability_is_empty():
    assert v.loan_schedule({"amount": 50_000}, D("2026-10-14")) == []


def test_liability_view_adds_the_status():
    view = v.liability_view({**LOAN, "id": "x"}, D("2026-02-15"))
    assert view["id"] == "x" and view["amortized"] is True and view["amount"] == 1_000_000


def test_portfolio_totals_with_one_asset_and_one_manual_liability_only():
    totals = v.portfolio_totals(
        assets=[{"category": "vehicles", "value": 500_000, "annual_change_rate": None, "valuation_date": None}],
        liabilities=[{"category": "personal_loan", "amount": 2_000.5}],
        bank_accounts=[],
        mutual_funds=[],
        equities=[],
        usd_to_inr=None,
        on=D("2026-10-14"),
    )
    assert totals["assets_by_category"] == {"vehicles": 500_000}
    assert totals["liabilities_by_category"] == {"personal_loan": 2_000.5}
    assert (totals["total_assets"], totals["total_liabilities"], totals["net_worth"]) == (500_000, 2_000.5, 497_999.5)
    assert (totals["asset_count"], totals["liability_count"]) == (1, 1)


def test_month_end_anchor_keeps_its_day_in_every_view():
    loan = {"amount": 1_000_000, "interest_rate": 12, "emi": v.emi_for_tenure(1_000_000, 12, 12),
            "balance_date": "2026-01-31"}
    early = v.loan_status(loan, D("2026-02-28"))
    late = v.loan_status(loan, D("2026-03-31"))
    assert early["payoff_date"] == late["payoff_date"] == "2027-01-31"
    assert [r["year"] for r in v.loan_schedule(loan, D("2026-02-28"))] == [2026, 2027]
    assert [r["year"] for r in v.loan_schedule(loan, D("2026-03-31"))] == [2026, 2027]


@pytest.mark.parametrize("tenure", [60, 240, 360])
@pytest.mark.parametrize("rate", [8.5, 9.75, 14])
@pytest.mark.parametrize("amount", [2_500_000, 750_000, 1_234_567])
def test_tenure_emi_clears_exactly_on_its_last_anniversary(amount, rate, tenure):
    loan = {"amount": amount, "interest_rate": rate, "emi": v.emi_for_tenure(amount, rate, tenure),
            "balance_date": "2026-01-15"}
    last = v.add_months(D("2026-01-15"), tenure)
    status = v.loan_status(loan, last)
    assert status["outstanding"] == 0
    assert status["payoff_date"] == last.isoformat()


def test_a_tiny_positive_rate_does_not_divide_by_zero():
    assert v.emi_for_tenure(120_000, 1e-14, 12) == pytest.approx(10_000, abs=0.01)


def test_paid_off_loan_stays_cleared_months_later():
    status = v.loan_status({**LOAN, "balance_date": "2025-01-15"}, D("2026-08-01"))
    assert status["outstanding"] == 0.0
    assert status["months_remaining"] == 0
    assert status["payoff_date"] == "2026-01-15"


def test_category_totals_are_rounded_once_from_the_unrounded_sum():
    cash = {"category": "cash", "value": 100.004, "annual_change_rate": None, "valuation_date": None}
    totals = v.portfolio_totals(assets=[cash, dict(cash)], liabilities=[], bank_accounts=[], mutual_funds=[],
                                equities=[], usd_to_inr=None, on=D("2026-10-14"))
    assert totals["assets_by_category"] == {"cash": 200.01}
    assert totals["total_assets"] == 200.01


def test_a_loan_already_below_half_a_paisa_is_cleared_on_its_balance_date():
    status = v.loan_status({"amount": 0.004, "interest_rate": 12, "emi": 100, "balance_date": "2026-01-15"},
                           D("2026-03-01"))
    assert status["outstanding"] == 0.0
    assert status["months_remaining"] == 0
    assert status["payoff_date"] == "2026-01-15"


def pf(**fields):
    return {"category": "ppf", "value": 0, "monthly_contribution": 10_000, "interest_rate": 7.1,
            "valuation_date": "2025-03-31", "annual_change_rate": None, **fields}


def test_ppf_contributions_for_a_year_earn_monthly_interest_credited_in_march():
    assert v.asset_current_value(pf(), D("2026-03-31")) == pytest.approx(124_615.00, abs=0.01)


def test_provident_fund_interest_is_credited_once_a_year():
    plan = pf(value=100_000, monthly_contribution=0)
    assert v.asset_current_value(plan, D("2026-03-31")) == pytest.approx(107_100.00, abs=0.01)
    assert v.asset_current_value(plan, D("2027-03-31")) == pytest.approx(114_704.10, abs=0.01)


def test_mid_year_value_includes_interest_earned_so_far():
    # Apr … Sep contributions; Apr … Aug have fully passed and earned interest
    assert v.asset_current_value(pf(), D("2025-09-15")) == pytest.approx(60_887.50, abs=0.01)


def test_a_mid_month_anchor_starts_with_the_next_month():
    plan = pf(value=50_000, monthly_contribution=1_000, interest_rate=8.25, valuation_date="2025-06-20")
    assert v.asset_current_value(plan, D("2025-06-30")) == 50_000
    assert v.asset_current_value(plan, D("2025-07-31")) == pytest.approx(51_000 + 51_000 * 8.25 / 1200, abs=0.01)


def test_before_the_anchor_a_provident_fund_is_its_stored_value():
    assert v.asset_current_value(pf(value=5_000), D("2025-03-01")) == 5_000


def test_epf_follows_the_same_rules():
    plan = pf(category="epf", value=100_000, monthly_contribution=0, interest_rate=8.25)
    assert v.asset_current_value(plan, D("2026-03-31")) == pytest.approx(108_250.00, abs=0.01)


def test_a_provident_fund_without_a_rate_is_its_stored_value():
    assert v.asset_current_value(pf(value=5_000, interest_rate=None), D("2026-10-14")) == 5_000


def test_other_categories_ignore_the_interest_rate():
    assert v.asset_current_value(pf(category="cash", value=5_000), D("2026-10-14")) == 5_000


def test_assets_are_grouped_by_what_they_are():
    totals = v.portfolio_totals(
        assets=[
            {"category": "cash", "value": 100}, {"category": "epf", "value": 200},
            {"category": "nps", "value": 100}, {"category": "gold", "value": 50},
            {"category": "esop_rsu", "value": 30}, {"category": "vehicles", "value": 70},
        ],
        liabilities=[],
        bank_accounts=[{"account_type": "savings", "balance": 10}, {"account_type": "fd", "balance": 20}],
        mutual_funds=[{"category": "equity", "current_value": 40}, {"category": "hybrid", "current_value": 20},
                      {"category": "liquid", "current_value": 5}],
        equities=[{"market": "NSE", "current_value": 25}],
        usd_to_inr=None,
        on=D("2026-10-14"),
    )
    classes = totals["assets_by_class"]
    assert list(classes) == ["equity", "debt", "gold", "cash", "other"]
    assert classes == pytest.approx({"equity": 155, "debt": 285, "gold": 50, "cash": 110, "other": 70})
    assert sum(classes.values()) == pytest.approx(totals["total_assets"])


def test_unknown_categories_count_as_other():
    totals = v.portfolio_totals(assets=[{"category": "something-new", "value": 9}], liabilities=[], bank_accounts=[],
                                mutual_funds=[{"category": None, "current_value": 1}], equities=[],
                                usd_to_inr=None, on=D("2026-10-14"))
    assert totals["assets_by_class"] == {"other": 10}


def test_an_empty_portfolio_has_no_classes():
    totals = v.portfolio_totals(assets=[], liabilities=[], bank_accounts=[], mutual_funds=[], equities=[],
                                usd_to_inr=None, on=D("2026-10-14"))
    assert totals["assets_by_class"] == {}


def _class_map_cases():
    for enum, shares in ((models.AssetCategory, v.ASSET_CATEGORY_CLASSES),
                         (models.AccountType, v.BANK_ACCOUNT_CLASSES),
                         (models.MutualFundCategory, v.MUTUAL_FUND_CLASSES)):
        for member in enum:
            yield pytest.param(shares, member.value, id=f"{enum.__name__}.{member.name}")


@pytest.mark.parametrize("shares, value", list(_class_map_cases()))
def test_every_category_has_a_complete_class_mapping(shares, value):
    assert value in shares, "a category without a mapping silently counts as 'other'"
    assert sum(shares[value].values()) == pytest.approx(1)
    assert set(shares[value]) <= set(v.ASSET_CLASSES)
