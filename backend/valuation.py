"""What each holding is worth on a given day: revaluation, FD/RD interest, loan amortization, totals.

Pure functions over stored rows plus a date; nothing here reads or writes storage.
Endpoints call `today()` so tests can freeze the date.
"""
import bisect
import calendar
import math
import re
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import exchange_service
from models import MAX_AMOUNT, MAX_UNITS, USD_MARKETS


def today() -> date:
    return date.today()


def parse_date(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def add_months(d: date, n: int) -> date:
    """The same day-of-month n months later, clamped to the end of shorter months."""
    index = d.month - 1 + n
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def months_between(start: date, end: date) -> int:
    """How many monthly anniversaries of `start` fall on or before `end`."""
    if end <= start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if add_months(start, months) > end:
        months -= 1
    return months


# ---------- Assets ----------

# EPF and PPF: interest accrues monthly on the running balance and is credited every 31 March
PROVIDENT_FUNDS = ("epf", "ppf")


def _provident_fund_value(asset: Dict, on: date) -> float:
    """Balance on `on`: the anchor balance plus monthly contributions and interest (credited each March;
    interest earned since the last March is included)."""
    since = parse_date(asset.get("valuation_date"))
    if since is None or on <= since:
        return asset["value"]
    balance = asset["value"]
    contribution = asset.get("monthly_contribution") or 0
    monthly_rate = asset["interest_rate"] / 1200
    accrued = 0.0
    month = add_months(date(since.year, since.month, 1), 1)  # the anchor's own month is in its balance
    while month <= on:
        balance += contribution  # paid by the 5th, so it earns this month's interest
        if add_months(month, 1) - timedelta(days=1) <= on:  # the whole month has passed
            accrued += balance * monthly_rate
            if month.month == 3:  # end of the financial year: interest is credited
                balance += accrued
                accrued = 0.0
        month = add_months(month, 1)
    return balance + accrued


def asset_current_value(asset: Dict, on: date) -> float:
    if asset.get("category") == "nps":
        return _nps_value_from_navs(asset, on) if nps_priced(asset) else _nps_value_without_navs(asset, on)
    if asset.get("category") in PROVIDENT_FUNDS and asset.get("interest_rate") is not None:
        return _provident_fund_value(asset, on)
    rate = asset.get("annual_change_rate")
    since = parse_date(asset.get("valuation_date"))
    if rate is None or since is None:
        return asset["value"]
    years = (on - since).days / 365.25
    if years <= 0:
        return asset["value"]
    return asset["value"] * (1 + rate / 100) ** years


def asset_view(asset: Dict, on: date) -> Dict:
    view = {**asset, "current_value": round(asset_current_value(asset, on), 2)}
    if asset.get("category") == "nps" and nps_priced(asset):
        view["nps_schemes"] = [{**s, "current_units": round(_units_held(s), 4),
                                "current_value": round(_units_held(s) * s["nav"], 2)} for s in asset["nps_schemes"]]
    return view


# ---------- NPS ----------
# Contributions land on the 1st of the month: the employer's every month, the subscriber's own once a year.
# With investment options (schemes) and their NAV histories, the balance and contributions become units;
# without NAVs the value is the balance plus contributions, grown at the expected return when one is set.

NPS_DEFAULT_CONTRIBUTION_MONTH = 3  # March: when most subscribers top up for the financial year
NPS_SCHEME_INPUT_KEYS = ("scheme_code", "scheme_name", "allocation_pct", "units")

NavHistory = List[Tuple[date, float]]  # (date, NAV), oldest first


def nps_contributions(asset: Dict, after: date, through: date) -> List[Tuple[date, float]]:
    """Contributions dated in (after, through], oldest first; same-day amounts are combined."""
    monthly = asset.get("monthly_contribution") or 0
    yearly = asset.get("yearly_contribution") or 0
    yearly_month = asset.get("yearly_contribution_month") or NPS_DEFAULT_CONTRIBUTION_MONTH
    out = []
    first = add_months(date(after.year, after.month, 1), 1)  # the 1st of `after`'s own month is not after it
    while first <= through:
        amount = monthly + (yearly if first.month == yearly_month else 0)
        if amount > 0:
            out.append((first, amount))
        first = add_months(first, 1)
    return out


def _grown(amount: float, annual_rate: Optional[float], start: date, on: date) -> float:
    years = (on - start).days / 365.25
    if annual_rate is None or years <= 0:
        return amount
    return amount * (1 + annual_rate / 100) ** years


def _nps_value_without_navs(asset: Dict, on: date) -> float:
    since = parse_date(asset.get("valuation_date"))
    if since is None:
        return asset["value"]
    rate = asset.get("annual_change_rate")
    return _grown(asset["value"], rate, since, on) + sum(
        _grown(amount, rate, when, on) for when, amount in nps_contributions(asset, since, on))


def nps_scheme_inputs(schemes: List[Dict]) -> List[Dict]:
    """The schemes as the user entered them, without anything pricing added."""
    return [{key: scheme.get(key) for key in NPS_SCHEME_INPUT_KEYS} for scheme in schemes]


def nps_priced(asset: Dict) -> bool:
    schemes = asset.get("nps_schemes") or []
    return bool(schemes) and asset.get("nps_priced_through") is not None and all(
        s.get(key) is not None for s in schemes for key in ("nav", "base_units", "contribution_units"))


def _units_held(scheme: Dict) -> float:
    return scheme["base_units"] + scheme["contribution_units"]


def _nps_at_cost_after(asset: Dict) -> date:
    """Contributions after this date count at cost in a priced value: those up to the pricing are in the units, and
    those up to a balance date set after the pricing (a future one) are in the balance."""
    priced_through = parse_date(asset["nps_priced_through"])
    balance_date = parse_date(asset.get("valuation_date"))
    return max(priced_through, balance_date) if balance_date else priced_through


def _nps_value_from_navs(asset: Dict, on: date) -> float:
    held = sum(_units_held(s) * s["nav"] for s in asset["nps_schemes"])
    return held + sum(amount for _, amount in nps_contributions(asset, _nps_at_cost_after(asset), on))


def nav_on_or_before(history: NavHistory, day: date) -> Optional[Tuple[date, float]]:
    index = bisect.bisect_right(history, (day, math.inf)) - 1
    return history[index] if index >= 0 else None


def _day(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"  # 15 Jan 2009


def _nps_pricing(asset: Dict, histories: Dict[str, NavHistory], on: date) -> Tuple[Optional[Dict], Optional[str]]:
    """(pricing, None), or (None, why the histories given can't price the asset)."""
    schemes = asset.get("nps_schemes") or []
    since = parse_date(asset.get("valuation_date"))
    if not schemes or since is None:
        return None, "it has no investment options or no balance date"
    contributions = nps_contributions(asset, since, on)
    priced = []
    for scheme in schemes:
        name = scheme["scheme_name"]
        history = histories.get(scheme["scheme_code"]) or []
        if not history:
            return None, f"{name} has no NAV history"
        latest, at_balance = nav_on_or_before(history, on), nav_on_or_before(history, since)
        if at_balance is None:
            return None, f"{name} has no NAV on or before {_day(since)}; use a later balance date"
        if latest is None:
            return None, f"{name} has no NAV on or before {_day(on)}"
        if not latest[1] <= MAX_AMOUNT:
            return None, f"{name} has a NAV too large to use"
        share = scheme["allocation_pct"] / 100
        units = scheme.get("units")
        base_units = units if units is not None else asset["value"] * share / at_balance[1]
        contribution_units = 0.0
        for when, amount in contributions:
            bought_at = nav_on_or_before(history, when)
            if bought_at is None:
                return None, f"{name} has no NAV on or before {_day(when)}"
            contribution_units += amount * share / bought_at[1]
        held = base_units + contribution_units
        if not (held <= MAX_UNITS and held * latest[1] <= MAX_AMOUNT):
            return None, f"the units or value of {name} would be too large to store"
        priced.append({
            **nps_scheme_inputs([scheme])[0],
            "nav": round(latest[1], 4), "nav_date": latest[0].isoformat(),
            "base_units": round(base_units, 4), "contribution_units": round(contribution_units, 4),
        })
    return {"nps_schemes": priced, "nps_priced_through": on.isoformat()}, None


def nps_price(asset: Dict, histories: Dict[str, NavHistory], on: date) -> Optional[Dict]:
    """Units and NAVs for every scheme of an NPS asset, as of `on`; None when any scheme can't be priced
    (pricing is all or nothing, so a stored asset is either fully priced or not at all)."""
    return _nps_pricing(asset, histories, on)[0]


def nps_price_problem(asset: Dict, histories: Dict[str, NavHistory], on: date) -> Optional[str]:
    """Why nps_price can't price the asset from these histories (fetched fine, but unusable), or None when it can."""
    return _nps_pricing(asset, histories, on)[1]


# ---------- Mutual fund SIPs ----------
# A SIP adds an installment on a schedule; each buys units at the NAV on (or before) its date. Units and the
# invested amount are as of `holdings_date`; installments after it add to them.


def sip_active(fund: Dict) -> bool:
    return bool(fund.get("sip_amount")) and bool(fund.get("holdings_date")) and bool(fund.get("sip_start_date"))


def sip_installments(fund: Dict, after: date, through: date) -> List[Tuple[date, float]]:
    """Installments dated in (after, through], within the SIP's start and end dates, oldest first."""
    amount = fund.get("sip_amount") or 0
    start = parse_date(fund.get("sip_start_date"))
    if amount <= 0 or start is None:
        return []
    end = parse_date(fund.get("sip_end_date"))
    last = min(through, end) if end else through
    out = []
    if (fund.get("sip_frequency") or "monthly") == "weekly":
        day = start
        while day <= last:
            if day > after:
                out.append((day, amount))
            day += timedelta(days=7)
        return out
    step = 3 if fund.get("sip_frequency") == "quarterly" else 1
    sip_day = fund.get("sip_day") or start.day
    month = date(start.year, start.month, 1)
    while month <= last:
        day = date(month.year, month.month, min(sip_day, calendar.monthrange(month.year, month.month)[1]))
        if start <= day <= last and day > after:
            out.append((day, amount))
        month = add_months(month, step)
    return out


def sip_price(fund: Dict, history: NavHistory, on: date) -> Optional[Dict]:
    """Units bought by every installment since the holdings date, each at its own NAV, as of `on`; None when an
    installment (or `on`) has no NAV or the result is beyond the bounds."""
    since = parse_date(fund.get("holdings_date"))
    latest = nav_on_or_before(history, on)
    if since is None or latest is None:
        return None
    units = invested = 0.0
    for when, amount in sip_installments(fund, since, on):
        bought_at = nav_on_or_before(history, when)
        if bought_at is None:
            return None
        units += amount / bought_at[1]
        invested += amount
    held = (fund.get("units") or 0) + units
    value = held * latest[1]
    if not (held <= MAX_UNITS and value <= MAX_AMOUNT and invested <= MAX_AMOUNT and latest[1] <= MAX_AMOUNT):
        return None
    return {"sip_units": round(units, 4), "sip_invested": round(invested, 2), "sip_priced_through": on.isoformat(),
            "current_nav": round(latest[1], 4), "current_value": round(value, 2)}


def sip_priced(fund: Dict) -> bool:
    return bool(fund.get("sip_priced_through")) and fund.get("sip_units") is not None and bool(fund.get("current_nav"))


def fund_view(fund: Dict, on: date) -> Dict:
    """A mutual fund with its SIP counted: installments up to the last pricing at their NAV, later ones at cost."""
    units = fund.get("units") or 0
    invested = fund.get("invested_amount") or 0
    if not sip_active(fund):
        return {**fund, "total_units": units, "total_invested": invested}
    if sip_priced(fund):
        # Holdings dated after the pricing already include the installments before them
        counted_through = max(parse_date(fund["sip_priced_through"]), parse_date(fund["holdings_date"]))
        later = sum(amount for _, amount in sip_installments(fund, counted_through, on))
        total_units = units + fund["sip_units"]
        value = total_units * fund["current_nav"] + later
        total_invested = invested + (fund.get("sip_invested") or 0) + later
    else:
        later = sum(amount for _, amount in sip_installments(fund, parse_date(fund["holdings_date"]), on))
        total_units = units
        value = (fund.get("current_value") or 0) + later
        total_invested = invested + later
    return {**fund, "current_value": round(value, 2), "total_units": round(total_units, 4),
            "total_invested": round(total_invested, 2)}


# ---------- FDs and RDs ----------

def _growth(annual_rate: Optional[float], days: int) -> float:
    """Quarterly compounding, as Indian banks quote FD and RD rates."""
    if annual_rate is None or days <= 0:
        return 1.0
    return (1 + annual_rate / 400) ** (4 * days / 365)


def _deposit_value(account: Dict, on: date) -> Optional[float]:
    """Value of an FD or RD on `on` (the caller caps `on` at maturity); None when it isn't computed."""
    start = parse_date(account.get("start_date"))
    if start is None:
        return None
    rate = account.get("interest_rate")
    if account.get("account_type") == "fd" and rate is not None:
        return account["balance"] * _growth(rate, (on - start).days)
    if account.get("account_type") == "rd" and account.get("monthly_deposit"):
        if on < start:
            return 0.0
        installments = months_between(start, on) + 1
        maturity = parse_date(account.get("maturity_date"))
        if maturity is not None:
            installments = min(installments, months_between(start, maturity))
        return sum(account["monthly_deposit"] * _growth(rate, (on - add_months(start, i)).days)
                   for i in range(installments))
    return None


def deposit_status(account: Dict, on: date) -> Dict:
    is_deposit = account.get("account_type") in ("fd", "rd")
    maturity = parse_date(account.get("maturity_date")) if is_deposit else None
    current = _deposit_value(account, min(on, maturity) if maturity else on) if is_deposit else None
    maturity_value = _deposit_value(account, maturity) if maturity else None
    return {
        "current_value": round(current if current is not None else account["balance"], 2),
        "maturity_value": round(maturity_value, 2) if maturity_value is not None else None,
        "matured": maturity is not None and maturity <= on,
        "days_to_maturity": (maturity - on).days if maturity else None,
    }


def bank_account_view(account: Dict, on: date) -> Dict:
    return {**account, **deposit_status(account, on)}


def upcoming_maturities(bank_accounts: List[Dict], on: date, within_days: int = 30) -> List[Dict]:
    """FDs/RDs maturing within `within_days`, plus any already matured, oldest first."""
    due = []
    for account in bank_accounts:
        status = deposit_status(account, on)
        if status["days_to_maturity"] is not None and status["days_to_maturity"] <= within_days:
            due.append({
                "id": account["id"],
                "bank_name": account["bank_name"],
                "account_type": account["account_type"],
                "maturity_date": account["maturity_date"],
                "days_to_maturity": status["days_to_maturity"],
                "maturity_value": status["maturity_value"],
            })
    return sorted(due, key=lambda m: m["days_to_maturity"])


# ---------- Loans ----------
# A loan is amortized when it has an EMI and a balance date: `amount` was the balance on `balance_date`
# and one EMI is paid on every monthly anniversary of that date.

PAID_OFF = 0.005            # a balance at or below half a paisa counts as cleared
MAX_SCHEDULE_MONTHS = 1200  # don't project payoffs more than 100 years out

_NOT_AMORTIZED = {
    "amortized": False, "months_remaining": None, "payoff_date": None, "interest_remaining": None,
    "next_emi_interest": None, "next_emi_principal": None, "emi_too_low": False, "last_emi_date": None,
}


def _round_up_to_paisa(amount: float) -> float:
    # The inner round strips float noise, so an exact 10000.0 stays 10000.0 rather than becoming 10000.01.
    return math.ceil(round(amount * 100, 6)) / 100


def emi_for_tenure(principal: float, annual_rate: float, months: int) -> float:
    """The EMI that clears `principal` in `months` payments, rounded up to the paisa so the loan is paid off
    on its last anniversary instead of leaving a stub payment."""
    r = annual_rate / 1200
    if r == 0:
        return _round_up_to_paisa(principal / months)
    growth_minus_one = math.expm1(months * math.log1p(r))  # (1 + r) ** months - 1, exact even for tiny r
    return _round_up_to_paisa(principal * r * (growth_minus_one + 1) / growth_minus_one)


def _remaining_payments(balance: float, r: float, emi: float, anchor: date, paid: int) -> Optional[List[Dict]]:
    """Monthly payments from `balance`, owed after `paid` anniversaries of `anchor`, until cleared; None past
    MAX_SCHEDULE_MONTHS. Payment k falls on anniversary `paid + k` of the balance date, so a month-end anchor
    returns to its day after a short month. The caller guarantees the EMI exceeds the first month's interest."""
    payments: List[Dict] = []
    while balance > PAID_OFF:
        if len(payments) == MAX_SCHEDULE_MONTHS:
            return None
        interest = balance * r
        payment = min(emi, balance + interest)
        balance -= payment - interest
        payments.append({"date": add_months(anchor, paid + len(payments) + 1), "payment": payment,
                         "interest": interest, "principal": payment - interest, "balance": max(balance, 0.0)})
    return payments


def _loan_projection(liability: Dict, on: date):
    """(status, remaining payments or None) for `liability` as of `on`."""
    emi = liability.get("emi")
    anchor = parse_date(liability.get("balance_date"))
    if not emi or anchor is None:
        return {"outstanding": liability["amount"], **_NOT_AMORTIZED}, None

    r = (liability.get("interest_rate") or 0) / 1200
    paid = months_between(anchor, on)
    # Where a rate or EMI change starts from: the outstanding on this date is the balance to re-anchor at.
    last_emi_date = add_months(anchor, paid).isoformat()
    balance = liability["amount"]
    cleared_on = anchor if balance <= PAID_OFF else None
    for k in range(1, paid + 1):
        if cleared_on:
            break
        balance = balance * (1 + r) - emi
        if balance <= PAID_OFF:
            cleared_on = add_months(anchor, k)

    if cleared_on:
        return {"outstanding": 0.0, "amortized": True, "months_remaining": 0, "payoff_date": cleared_on.isoformat(),
                "interest_remaining": 0.0, "next_emi_interest": None, "next_emi_principal": None,
                "emi_too_low": False, "last_emi_date": last_emi_date}, []

    status = {"outstanding": round(balance, 2), "amortized": True, "months_remaining": None, "payoff_date": None,
              "interest_remaining": None, "next_emi_interest": None, "next_emi_principal": None,
              "emi_too_low": emi <= balance * r, "last_emi_date": last_emi_date}
    if status["emi_too_low"]:
        return status, None

    status["next_emi_interest"] = round(balance * r, 2)
    status["next_emi_principal"] = round(min(emi, balance * (1 + r)) - balance * r, 2)
    payments = _remaining_payments(balance, r, emi, anchor, paid)
    if payments is not None:
        status["months_remaining"] = len(payments)
        status["payoff_date"] = payments[-1]["date"].isoformat()
        status["interest_remaining"] = round(sum(p["interest"] for p in payments), 2)
    return status, payments


def loan_status(liability: Dict, on: date) -> Dict:
    return _loan_projection(liability, on)[0]


def loan_schedule(liability: Dict, on: date) -> List[Dict]:
    """The remaining payments grouped by calendar year."""
    payments = _loan_projection(liability, on)[1] or []
    years: Dict[int, Dict] = {}
    for p in payments:
        year = years.setdefault(p["date"].year, {"year": p["date"].year, "paid": 0.0, "interest": 0.0,
                                                 "principal": 0.0, "closing_balance": 0.0})
        year["paid"] += p["payment"]
        year["interest"] += p["interest"]
        year["principal"] += p["principal"]
        year["closing_balance"] = p["balance"]
    return [{key: round(value, 2) if isinstance(value, float) else value for key, value in year.items()}
            for year in years.values()]


def liability_view(liability: Dict, on: date) -> Dict:
    return {**liability, **loan_status(liability, on)}


# ---------- Asset classes ----------
# Allocation by what a holding is (equity, debt, …), not where it sits. Each map gives a holding's share per class.

ASSET_CLASSES = ("equity", "debt", "gold", "real_estate", "cash", "other")

_OTHER = {"other": 1}
_HALF_EQUITY_HALF_DEBT = {"equity": 0.5, "debt": 0.5}  # NPS and hybrid funds: their real mix varies

ASSET_CATEGORY_CLASSES = {
    "cash": {"cash": 1}, "real_estate": {"real_estate": 1},
    "epf": {"debt": 1}, "ppf": {"debt": 1}, "bonds": {"debt": 1}, "retirement": {"debt": 1},
    "gold": {"gold": 1}, "sgb": {"gold": 1}, "esop_rsu": {"equity": 1}, "nps": _HALF_EQUITY_HALF_DEBT,
    "investments": _OTHER, "vehicles": _OTHER, "crypto": _OTHER, "other": _OTHER,
}
BANK_ACCOUNT_CLASSES = {"savings": {"cash": 1}, "current": {"cash": 1}, "salary": {"cash": 1},
                        "fd": {"debt": 1}, "rd": {"debt": 1}}
MUTUAL_FUND_CLASSES = {"equity": {"equity": 1}, "elss": {"equity": 1}, "index": {"equity": 1},
                       "debt": {"debt": 1}, "liquid": {"debt": 1}, "hybrid": _HALF_EQUITY_HALF_DEBT, "other": _OTHER}


def _add_to_classes(totals: Dict[str, float], shares: Dict[str, float], value: float) -> None:
    for asset_class, share in shares.items():
        totals[asset_class] = totals.get(asset_class, 0) + value * share


# An NPS scheme's class is in its name: "SCHEME E" equity, "SCHEME C"/"SCHEME G" debt, "SCHEME A" alternatives.
_NPS_SCHEME_LETTER = re.compile(r"\bSCHEME\s+([ECGA])\b", re.IGNORECASE)
_NPS_LETTER_CLASSES = {"E": {"equity": 1}, "C": {"debt": 1}, "G": {"debt": 1}, "A": _OTHER}


def nps_scheme_classes(name: str) -> Dict[str, float]:
    """Government, Lite, Vatsalya and other mixed schemes keep the even equity/debt split."""
    match = _NPS_SCHEME_LETTER.search(name or "")
    return _NPS_LETTER_CLASSES[match.group(1).upper()] if match else _HALF_EQUITY_HALF_DEBT


def asset_class_shares(asset: Dict, on: date) -> Dict[str, float]:
    """How an asset's value splits across asset classes; the shares add up to 1."""
    schemes = asset.get("nps_schemes") if asset.get("category") == "nps" else None
    if schemes:
        weights: Dict[str, float] = {}
        if nps_priced(asset):
            at_cost = sum(amount for _, amount in nps_contributions(asset, _nps_at_cost_after(asset), on))
            for s in schemes:
                weight = _units_held(s) * s["nav"] + at_cost * s["allocation_pct"] / 100
                _add_to_classes(weights, nps_scheme_classes(s["scheme_name"]), weight)
        else:
            for s in schemes:
                _add_to_classes(weights, nps_scheme_classes(s["scheme_name"]), s["allocation_pct"])
        total = sum(weights.values())
        if total > 0:
            return {asset_class: weight / total for asset_class, weight in weights.items()}
    return ASSET_CATEGORY_CLASSES.get(asset["category"], _OTHER)


# ---------- Totals ----------

def equity_value_inr(equity: Dict, usd_to_inr: Optional[float]) -> float:
    value = equity.get("current_value") or 0
    return value * usd_to_inr if equity.get("market") in USD_MARKETS else value


async def usd_rate_if_needed(equities: List[Dict]) -> Optional[float]:
    """The live USD→INR rate, fetched only when some holding is priced in USD."""
    if any(e.get("market") in USD_MARKETS for e in equities):
        return await exchange_service.fetch_usd_to_inr()
    return None


def portfolio_totals(assets: List[Dict], liabilities: List[Dict], bank_accounts: List[Dict],
                     mutual_funds: List[Dict], equities: List[Dict], usd_to_inr: Optional[float],
                     on: date) -> Dict:
    assets_by_category: Dict[str, float] = {}
    by_class: Dict[str, float] = {}
    for asset in assets:
        value = asset_current_value(asset, on)
        assets_by_category[asset["category"]] = assets_by_category.get(asset["category"], 0) + value
        _add_to_classes(by_class, asset_class_shares(asset, on), value)

    buckets = {"equities": 0.0, "bank_accounts": 0.0, "mutual_funds": 0.0}
    for equity in equities:
        value = equity_value_inr(equity, usd_to_inr)
        buckets["equities"] += value
        _add_to_classes(by_class, {"equity": 1}, value)
    for account in bank_accounts:
        value = deposit_status(account, on)["current_value"]
        buckets["bank_accounts"] += value
        _add_to_classes(by_class, BANK_ACCOUNT_CLASSES.get(account.get("account_type"), _OTHER), value)
    for fund in mutual_funds:
        value = fund_view(fund, on).get("current_value") or 0
        buckets["mutual_funds"] += value
        _add_to_classes(by_class, MUTUAL_FUND_CLASSES.get(fund.get("category"), _OTHER), value)
    for name, total in buckets.items():
        if total > 0:
            assets_by_category[name] = total

    liabilities_by_category: Dict[str, float] = {}
    for liability in liabilities:
        liabilities_by_category[liability["category"]] = (
            liabilities_by_category.get(liability["category"], 0) + loan_status(liability, on)["outstanding"])

    total_assets = sum(assets_by_category.values())
    total_liabilities = sum(liabilities_by_category.values())
    return {
        "total_assets": round(total_assets, 2),
        "total_liabilities": round(total_liabilities, 2),
        "net_worth": round(total_assets - total_liabilities, 2),
        "assets_by_category": {name: round(total, 2) for name, total in assets_by_category.items()},
        "assets_by_class": {c: round(by_class[c], 2) for c in ASSET_CLASSES if by_class.get(c, 0) > 0},
        "liabilities_by_category": {name: round(total, 2) for name, total in liabilities_by_category.items()},
        "asset_count": len(assets) + len(equities) + len(bank_accounts) + len(mutual_funds),
        "liability_count": len(liabilities),
    }


# ---------- Automatic snapshots ----------
# Weekly and every-2-weeks count days from the latest snapshot; monthly and quarterly follow the calendar.

SNAPSHOT_FREQUENCIES = ("weekly", "fortnightly", "monthly", "quarterly")
DEFAULT_SNAPSHOT_FREQUENCY = "monthly"
_SNAPSHOT_EVERY_DAYS = {"weekly": 7, "fortnightly": 14}


def next_snapshot_date(frequency: str, timestamps: List[str], on: date) -> date:
    """The first day on or after `on` when an automatic snapshot is due; manual snapshots count, future ones don't."""
    taken = [d for d in (date.fromisoformat(t[:10]) for t in timestamps) if d <= on]
    if frequency in _SNAPSHOT_EVERY_DAYS:
        latest = max(taken, default=None)
        return on if latest is None else max(on, latest + timedelta(days=_SNAPSHOT_EVERY_DAYS[frequency]))
    months = 3 if frequency == "quarterly" else 1
    period_start = date(on.year, (on.month - 1) // months * months + 1, 1)
    return add_months(period_start, months) if any(d >= period_start for d in taken) else on


def snapshot_due(frequency: str, timestamps: List[str], on: date) -> bool:
    return next_snapshot_date(frequency, timestamps, on) <= on
