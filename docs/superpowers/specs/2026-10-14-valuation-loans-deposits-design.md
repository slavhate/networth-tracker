# Valuation, Loans, Deposits and Revaluation — Design Spec

**Date:** 2026-10-14
**Branch:** `feat/valuation-loans-fd` (from local `main` at `3835682`, which includes Round 1: safe restore + NYSE)
**Context:** Round 2 of 4 in the "close the gaps" work. Self-hosted FastAPI + React app; all data in one JSON file. Round 1 left four hardening follow-ups that this round also closes (§8).

The user asked for this round to be built end to end on the recommended options without check-ins; every choice below that would normally be a question is recorded as a **Decision**.

---

## 1. Goal

1. **One valuation module.** Every "what is this worth today" calculation lives in `backend/valuation.py`. The dashboard, snapshots and summaries stop duplicating totals code.
2. **Loans pay themselves down.** A loan with an EMI shows today's outstanding balance, payoff date, interest still to pay, the next EMI's interest/principal split, and a year-by-year schedule — without monthly manual edits.
3. **FDs and RDs earn interest and mature.** Deposits with a rate and dates show today's value, maturity value and a maturity countdown; the dashboard lists deposits maturing within 30 days or already matured.
4. **Assets revalue themselves.** An asset can carry a yearly change rate (vehicles depreciate, property appreciates); its value today is derived from the last known value and date.
5. **Round 1 hardening** (§8): finite, bounded numbers on every write path; readable 422 errors in the UI; temp-file permissions; timezone-aware export date; shared market constants; restore-dialog polish; no hardcoded test passwords.

**Out of scope:** loan prepayment tracking (re-anchor the balance instead, §3.2), payout (non-cumulative) FD interest, insurance renewal reminders (Tier 3 #12, not selected), Indian asset types (Round 3), asset-class allocation and automatic snapshots (Round 4).

---

## 2. Valuation Module (`backend/valuation.py`, new)

Pure functions over stored rows plus a `today: date` argument; no storage access. One async helper fetches the USD rate.

### 2.1 Dates

- `today() -> date` — `date.today()`. Endpoints call `valuation.today()`; tests monkeypatch it.
- `add_months(d: date, n: int) -> date` — same day-of-month `n` months later, clamped to the month's last day (Jan 31 + 1 → Feb 28/29).
- `months_between(start: date, end: date) -> int` — whole monthly anniversaries of `start` that fall on or before `end`; 0 when `end <= start`. Anniversary k is `add_months(start, k)`.
- `parse_date(s: Optional[str]) -> Optional[date]` — `date.fromisoformat`, None for None.

### 2.2 Assets — revaluation

`asset_current_value(asset, today) -> float`:
- If `annual_change_rate` or `valuation_date` is missing → `value`.
- `years = (today - valuation_date).days / 365.25`; if `years <= 0` → `value`.
- Else `value * (1 + annual_change_rate / 100) ** years`.

**Decision:** compound yearly-rate model with fractional years (smooth daily curve), not step changes on anniversaries.

### 2.3 Liabilities — amortization

A liability is **amortized** when it has `emi` and `balance_date`. `amount` is the balance on `balance_date` (the anchor). Monthly rate `r = (interest_rate or 0) / 1200`.

`loan_status(liability, today) -> dict`:
- Not amortized → `{"amortized": False, "outstanding": amount, ...all loan fields None, "emi_too_low": False}`.
- `n = months_between(balance_date, today)` EMIs paid since the anchor. Walk `n` months from `amount`: `bal = bal * (1 + r) - emi`; once `bal <= 0.005` it is 0 and stays 0.
- `outstanding = bal` (rounded to 2 decimals).
- Remaining schedule from the last anniversary `A = add_months(balance_date, n)`: month k (k = 1, 2, …) is dated `add_months(balance_date, n + k)` (anniversaries of the balance date, so month-end anchors return to their day); `interest = bal * r`; if `emi <= interest` on month 1 → never pays off (`emi_too_low = True`, payoff fields None); `payment = min(emi, bal + interest)`; `principal = payment - interest`; `bal -= principal`; stop when `bal <= 0.005`. More than 1200 months → payoff fields None (too long to project), `emi_too_low = False`.
- Fields: `outstanding`, `amortized: True`, `months_remaining`, `payoff_date` (date of the last payment, ISO), `interest_remaining` (sum of schedule interest), `next_emi_interest` (`outstanding * r`), `next_emi_principal` (`min(emi, outstanding*(1+r)) - outstanding*r`), `emi_too_low`. Both `next_emi_*` are None when the loan is paid off or `emi_too_low`. A paid-off loan has outstanding 0, months_remaining 0, payoff_date = the anniversary on which it reached 0, interest_remaining 0.
- `loan_schedule(liability, today) -> list[dict]` — the remaining schedule grouped by calendar year: `{"year", "paid", "interest", "principal", "closing_balance"}` (2-decimal rounding on output only).

`emi_for_tenure(principal, annual_rate, months) -> float` — `P*r*(1+r)^N / ((1+r)^N - 1)`, or `P/N` when `r == 0`; rounded up to the paisa (so the loan clears on its last tenure anniversary).

**Decision (anchor model):** a loan is "balance B on date D, EMI E, rate R". It covers both "I know my sanction letter" (B = principal, D = disbursal date, E from tenure) and "I know today's statement" (B = today's balance, D = today). Prepayments are handled by re-anchoring (edit balance + date). No separate principal/start/tenure model.

### 2.4 Bank accounts — FD and RD

Quarterly compounding (Indian bank standard): growth factor for `days` is `(1 + rate/400) ** (4 * days / 365)`.

`deposit_status(account, today) -> dict` with `current_value`, `maturity_value`, `matured`, `days_to_maturity`:
- **FD** (`account_type == "fd"`) with `interest_rate` and `start_date`: principal = `balance`; value on date d (capped at `maturity_date` if set; before `start_date` → principal) = `balance * growth(days(d - start))`; `maturity_value` = value at `maturity_date` (None without one).
- **RD** (`account_type == "rd"`) with `monthly_deposit` and `start_date`: installments are deposited on `add_months(start, i)`, i = 0..N-1 where `N = months_between(start, maturity_date)` (unbounded without a maturity date). Installments made by date d: `min(months_between(start, d) + 1, N)` (0 before start). Value on d (capped at maturity) = `Σ monthly_deposit * growth(days(d - deposit_i))`; without `interest_rate` the growth factor is 1 (value = deposits so far). `maturity_value` = value at maturity with all N installments.
- Any other case → `current_value = balance`, `maturity_value = None`.
- `matured` = `maturity_date <= today`; `days_to_maturity = (maturity_date - today).days` (negative once matured); both None/False without a maturity date. A matured deposit's `current_value` is its maturity value (no growth after maturity).
- `maturity_date` and `matured` work for FD/RD even without a rate (reminder only).

**Decision:** RD value ignores `balance` when `monthly_deposit` and `start_date` are set; `balance` stays a required field (the UI labels it "Deposited so far" for RDs).

### 2.5 Portfolio totals

- `equity_value_inr(equity, usd_to_inr) -> float` — `current_value`, × rate for `USD_MARKETS`.
- `async usd_rate_if_needed(equities) -> Optional[float]` — fetches `exchange_service.fetch_usd_to_inr()` only when some holding is in `USD_MARKETS`, else None.
- `portfolio_totals(assets, liabilities, bank_accounts, mutual_funds, equities, usd_to_inr, today) -> dict` with `total_assets`, `total_liabilities`, `net_worth`, `assets_by_category`, `liabilities_by_category`, `asset_count`, `liability_count` — the same keys and category names as today's dashboard (asset categories plus `equities`, `bank_accounts`, `mutual_funds` buckets, each added only when > 0). Asset values via `asset_current_value`; bank via `deposit_status(...)["current_value"]`; liabilities via `loan_status(...)["outstanding"]`; mutual funds `current_value or 0`.
- `upcoming_maturities(bank_accounts, today, within_days=30) -> list[dict]` — FD/RD accounts with a maturity date and `days_to_maturity <= 30` (matured ones included), sorted by maturity date: `{"id", "bank_name", "account_type", "maturity_date", "days_to_maturity", "maturity_value"}`.

`get_dashboard`, `create_snapshot`, `/api/bank-accounts-summary` and `/api/equities-summary` use these functions; their duplicated totals code is deleted.

---

## 3. Data Model Changes (`backend/models.py`)

All new input fields are optional; existing rows keep working unchanged.

### 3.1 Shared input rules

- `IsoDate` — an annotated `str` validated with `date.fromisoformat`, year 1900–2200, normalized to `YYYY-MM-DD`; error "Invalid date".
- `InputModel(BaseModel)` with `model_config = ConfigDict(allow_inf_nan=False)` — the base of every Create/Base, Update and restore model (assets, liabilities, bank accounts, insurances, mutual funds, equities, goal, `SnapshotRestore`).
- `MAX_AMOUNT = 1e15` — upper bound (`le=`) on every money field: asset `value`, liability `amount`/`emi`, bank `balance`/`monthly_deposit`, insurance `sum_assured`/`premium`, mutual fund `invested_amount`/`current_value`/`sip_amount`/`avg_nav`/`current_nav`, equity `avg_buy_price`/`current_price`, goal `target_amount`; `SnapshotRestore` totals `ge=0, le=1e300` (finiteness enforced separately by `InputModel`). Quantities: equity `quantity le=1e9`, mutual fund `units le=1e12`.
- The Round 1 rule holds: every Update field carries the same bounds as its Create counterpart.

### 3.2 New fields

| Model | Field | Type / rule |
|---|---|---|
| Asset | `annual_change_rate` | `Optional[float]`, `ge=-99, le=100` (% per year) |
| Asset | `valuation_date` | `Optional[IsoDate]` (date `value` was accurate) |
| Liability | `emi` | `Optional[float]`, `gt=0, le=MAX_AMOUNT` |
| Liability | `balance_date` | `Optional[IsoDate]` (date `amount` was the balance) |
| Liability | `tenure_months` | `Optional[int]`, `ge=1, le=600` (input helper, see below) |
| BankAccount | `interest_rate` | `Optional[float]`, `ge=0, le=100` |
| BankAccount | `start_date` | `Optional[IsoDate]` |
| BankAccount | `maturity_date` | `Optional[IsoDate]` |
| BankAccount | `monthly_deposit` | `Optional[float]`, `gt=0, le=MAX_AMOUNT` (RD installment) |

Write-time rules (create and update, in `main.py`, applied to the merged row for updates):
- Liability: if the request carries `tenure_months` and no `emi`, compute `emi = emi_for_tenure(amount, interest_rate or 0, tenure_months)` and store it. If the merged row has `emi` but no `balance_date`, set `balance_date` to `valuation.today()`.
- Asset: if the merged row has `annual_change_rate` but no `valuation_date`, set it to today.
- Bank account: `maturity_date` earlier than `start_date` → 400 "Maturity date must be after the start date".

### 3.3 Clearing optional fields

Today `update_*` helpers skip `None`, so an optional field can never be cleared (removing an interest rate does nothing). New rule: each of these entities has a **clearable** set; a `None` for a clearable key that is present in the request clears it, other `None`s are still skipped:
- assets: `description`, `annual_change_rate`, `valuation_date`
- liabilities: `interest_rate`, `description`, `emi`, `balance_date`, `tenure_months`
- bank_accounts: `branch`, `ifsc_code`, `interest_rate`, `start_date`, `maturity_date`, `monthly_deposit`

Implemented once as `_apply_update(row, update_data, clearable)` in `database.py`. Other entities keep today's behaviour.

### 3.4 Response fields (computed, not stored)

- `Asset` gains `current_value: float`.
- `Liability` gains `outstanding: float`, `amortized: bool`, `months_remaining`, `payoff_date`, `interest_remaining`, `next_emi_interest`, `next_emi_principal` (all Optional), `emi_too_low: bool`.
- `BankAccount` gains `current_value: float`, `maturity_value: Optional[float]`, `matured: bool`, `days_to_maturity: Optional[int]`.
- Every list/get/create/update endpoint for these three entities returns `{**row, **computed}` via `valuation.asset_view` / `liability_view` / `bank_account_view`.
- `GET /api/export` keeps returning stored rows only. Restore ignores computed fields (Pydantic `extra="ignore"`).
- `DashboardMetrics` gains `maturities: List[dict]` (from `upcoming_maturities`).

### 3.5 New endpoint

`GET /api/liabilities/{id}/schedule` → `{"rows": loan_schedule(...), "months_remaining", "payoff_date", "interest_remaining"}`; 404 unknown id; 400 "This liability has no EMI set" when not amortized.

---

## 4. Frontend

### 4.1 Assets page
- Form: "Yearly change (%)" (optional, may be negative) and "Value as of" (date, defaults to today). Picking **Vehicles** pre-fills −15 and **Real Estate** +5 when the rate field is empty and untouched (**Decision:** suggested defaults, user-editable). Changing the value field resets "Value as of" to today.
- List and totals use `current_value`. A revalued asset shows a second line: "₹X on <date> · −15%/yr".

### 4.2 Liabilities page
- Form: "Balance (₹)" (was "Amount Owed"), "Balance as of" (date), "EMI (₹/month)" (optional), and a "Calculate EMI from tenure (months)" field that fills EMI using the same formula as the backend (shown, editable). Changing the balance resets "Balance as of" to today.
- List and totals use `outstanding`. An amortized loan shows "EMI ₹X · paid off by Mon YYYY · ₹Y interest left" and a "Schedule" button opening a modal with the yearly table (year, paid, interest, principal, closing balance). `emi_too_low` shows a red "EMI doesn't cover the interest" badge.

### 4.3 Bank Accounts page
- For FD/RD types the form shows "Interest rate (% p.a.)", "Start date", "Maturity date"; RD also "Monthly deposit". Balance is labelled "Principal" for FD and "Deposited so far" for RD.
- List and total use `current_value`. FD/RD rows show "Matures in N days · ₹maturity value" or a red "Matured on <date> — update or renew".

### 4.4 Dashboard
- When `maturities` is non-empty, a card above the charts lists each: "<bank> FD matures in 12 days (₹5,35,000)" / "<bank> RD matured on 3 Oct 2026 — update or renew". Privacy mode masks amounts.

### 4.5 Print report
- Assets and bank accounts use `current_value`; liabilities use `outstanding` and gain an EMI column. US holdings' Avg Buy Price and Current Price columns show `$` (Round 1 follow-up).

---

## 5. Demo Data

When `CREATE_DEMO_DATA=true` creates the demo user, sample rows gain the new fields with dates relative to today: the home loan and car loan get EMI + balance date; the Axis FD gets 7.1% from 200 days ago maturing in 20 days (so the dashboard notice shows); the Honda City gets −15%/yr from a year ago. Existing demo users are not changed.

---

## 6. Error Handling

| Situation | Result |
|---|---|
| Non-finite number in any write (`"inf"`, `NaN`) | 422 "Input should be a finite number" |
| Money above 1e15, quantity above 1e9, units above 1e12 | 422 "Input should be less than or equal to …" |
| Bad date string | 422 "Invalid date" |
| Maturity before start | 400 "Maturity date must be after the start date" |
| Schedule of a non-amortized liability | 400 "This liability has no EMI set" |
| EMI ≤ monthly interest | saved; `emi_too_low = True`; payoff fields None; UI badge |

---

## 7. Testing

- `tests/test_valuation.py` (pure, fixed dates): `add_months`/`months_between` edge cases (month ends, leap years, same day, end before start); asset growth/depreciation and future valuation date; loan: EMI formula against a known value (₹10,00,000 at 12% for 12 months → 88,848.79), outstanding after n months, payoff and paid-off loans, zero-rate loan, EMI too low, yearly schedule sums (principal sums to outstanding); FD against a known value (₹1,00,000 at 7% for 365 days → 107,185.90); RD against the standard Indian RD closed form; matured deposits stop growing; portfolio totals.
- API tests: new fields round-trip through create/update/get/list with computed fields; clearing works; tenure→EMI; default balance/valuation dates; maturity-before-start 400; schedule endpoint; dashboard uses computed values and lists maturities; snapshot totals; export holds stored fields only and restores; bank summary.
- Hardening tests (§8).
- Frontend: `npm run build`; controller checks every flow in the browser.

---

## 8. Round 1 Follow-ups Closed Here

1. **Finite, bounded inputs everywhere** (§3.1). Equity `gain_loss_percent` is 0 when the invested amount is under ₹0.01 (avoids an infinite percent from absurdly small prices); one helper computes equity numbers for create, update and price refresh.
2. **Readable 422 errors:** `utils/errors.js` `errorMessage` formats a FastAPI validation array as "field: message; …"; every page and the restore dialog use it (today an array `detail` crashes the page).
3. **Temp file permissions:** `save_data` copies the existing file's mode onto the temp file before writing any data.
4. **Export date:** `export_date` is UTC with offset (`datetime.now(timezone.utc).isoformat()`), so the restore dialog shows the correct local time.
5. **Shared market constants:** `frontend/src/utils/markets.js` exports `USD_MARKETS`, `isUsdMarket`, `DEFAULT_USD_TO_INR`, used by the Equities page and the report.
6. **Restore dialog polish:** a file that parses but isn't a backup object with at least one section is rejected in the sidebar ("This file doesn't look like a Net Worth Tracker backup") without opening the dialog; a backup whose counts are all zero shows an extra red warning ("This backup is empty — restoring it deletes everything"); the `.json` check is case-insensitive; the pre-restore download happens once per dialog; `onRestored` runs outside the error handler.
7. **USD rate only when needed:** totals fetch the exchange rate only if a US holding exists.
8. **No hardcoded test passwords:** tests take the password from `tests/credentials.py`, which generates one per run with `secrets.token_urlsafe`. New test data uses obviously fake values.

---

## 9. Documentation

README: Liabilities (EMI, payoff date, schedule), Bank Accounts (FD/RD interest and maturity), Assets (yearly change rate), dashboard maturity notice, the new schedule endpoint, and the input limits.
