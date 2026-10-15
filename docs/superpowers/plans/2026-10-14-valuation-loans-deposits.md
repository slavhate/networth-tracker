# Valuation, Loans, Deposits and Revaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Values are computed as of today in one module: loans amortize from an EMI, FDs/RDs earn interest and mature, assets revalue at a yearly rate; plus the Round 1 hardening follow-ups.

**Architecture:**
- `backend/valuation.py` (new) holds pure functions: date helpers, asset revaluation, FD/RD value, loan amortization and schedule, portfolio totals, upcoming maturities. Endpoints call `valuation.today()` so tests can freeze the date.
- Stored rows keep the user's inputs (balance on a date, rate, EMI…). Endpoints for assets, liabilities and bank accounts return `{**row, **computed}`; export returns stored rows only.
- The dashboard, snapshot and summary endpoints use `valuation.portfolio_totals` instead of their own copies of the totals code.
- Frontend pages show computed values and gain the new inputs; small shared utils (`dates.js`, `loans.js`, `markets.js`, `backup.js`, `errors.js`) keep logic in one place.

**Tech Stack:** FastAPI 0.115, Pydantic 2.10, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-valuation-loans-deposits-design.md`. Read it before starting any task.

## Global Constraints

- **Branch:** `feat/valuation-loans-fd` (from local `main` at `3835682`), worktree `<worktree>` (`/mnt/c/<path-to>/networth-tracker-wt/valuation` in WSL). Nothing is pushed.
- **Environment:** Python and Node exist only inside WSL `Ubuntu-24.04`. The controller provides helper scripts for the backend suite and the frontend build; use them instead of running `python`/`npm` directly.
- **Backend test command:** `cd backend && python -m pytest -p no:cacheprovider tests -q` (via the helper). `tests/conftest.py` pins `TZ=Asia/Kolkata`.
- **Expected totals:** 154 before this work; 154 after Task 1; 164 after Task 2; 166 after Task 3; 193 after Task 4; 206 after Task 5; 216 after Task 6; 232 after Task 7; 233 after Task 8.
- **Frontend build command:** `cd frontend && npm run build` (via the helper). No frontend test framework exists.
- **Tests never touch the network:** use the `offline_markets` fixture for anything that creates equities or mutual funds or reads the dashboard/summaries.
- **No hardcoded secrets or sensitive data anywhere, tests included:** passwords come from `tests/credentials.py` (generated per run); test data uses obviously fake values (`Test Bank`, `00001234`, `user@example.com`). Never add a personal name or email to a committed file.
- **No new dependencies.**
- **Dates:** stored as `YYYY-MM-DD` strings. Frontend parses them as local dates (never `new Date("YYYY-MM-DD")`, which is UTC).
- **Commits:** use the commit identity and `Co-Authored-By` trailer given in your dispatch prompt. Never push.
- **Style:** backend uses module-level functions, `db.` helpers and `HTTPException`; frontend uses Tailwind component classes (`card`, `input`, `label`, `btn-primary`, `btn-secondary`, `btn-danger`) with `dark:` variants. Match each file's line endings (CRLF in the working tree); prefer the Edit tool over `sed -i`.

## Review Focus

1. A loan whose EMI does not cover the monthly interest: expect it saved, `emi_too_low` true, no payoff date, a red badge — never an infinite loop or a crash (Task 5 tests it; Task 11 renders it).
2. Month-end anchors (balance date or deposit start on the 31st, leap days): expect anniversaries on the last day of shorter months (Task 4 tests `add_months`/`months_between`).
3. Editing an item to remove its rate/EMI/dates: expect the value to fall back to the stored amount (Task 6 tests clearing; Task 7 tests the API).
4. A deposit or loan whose dates are in the future: expect the principal/balance unchanged and no negative months (Tasks 4 and 5 test it).
5. Privacy mode: every new amount on the pages, the dashboard maturity card and the schedule modal is masked (Task 14 checks by hand).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/tests/credentials.py` | create | per-run generated test passwords |
| `backend/models.py` | modify | `InputModel`, `MAX_*` bounds, `IsoDate`, new fields, computed response fields, `DashboardMetrics.maturities` |
| `backend/database.py` | modify | `_equity_numbers`; temp-file mode before write; `_apply_update` + clearable sets |
| `backend/valuation.py` | create | dates, revaluation, deposits, loans, totals, maturities |
| `backend/main.py` | modify | views on asset/liability/bank endpoints; write-time defaults; schedule endpoint; dashboard/snapshot/summaries via valuation; tz-aware export date; demo data |
| `backend/tests/conftest.py` | modify | `frozen_today` fixture; generated password |
| `backend/tests/test_input_limits.py` | create | Task 2 |
| `backend/tests/test_valuation.py` | create | Tasks 4–5 |
| `backend/tests/test_new_fields.py` | create | Task 6 |
| `backend/tests/test_valuation_api.py` | create | Tasks 7–8 |
| `frontend/src/utils/errors.js` | modify | readable 422 arrays |
| `frontend/src/utils/markets.js` | create | `USD_MARKETS`, `isUsdMarket`, `DEFAULT_USD_TO_INR` |
| `frontend/src/utils/backup.js` | create | `BACKUP_SECTIONS`, `looksLikeBackup` |
| `frontend/src/utils/dates.js` | create | `todayIso`, `formatDate`, `formatMonthYear` |
| `frontend/src/utils/loans.js` | create | `emiForTenure` |
| `frontend/src/components/LoanScheduleModal.jsx` | create | yearly schedule modal |
| `frontend/src/pages/*.jsx`, `components/Layout.jsx`, `components/RestoreDialog.jsx`, `utils/reportGenerator.js`, `api.js` | modify | per task |
| `README.md` | modify | Task 8 |

---

### Task 1: Generated test passwords

**Files:**
- Create: `backend/tests/credentials.py`
- Modify: `backend/tests/conftest.py`, `backend/tests/api_helpers.py`, `backend/tests/test_change_password.py`, `backend/tests/test_token_version.py`, `backend/tests/test_two_factor_login.py`, `backend/tests/test_two_factor_manage.py`, `backend/tests/test_restore_api.py`

**Interfaces:**
- Produces: `credentials.PASSWORD`, `credentials.OTHER_PASSWORD`, `credentials.WRONG_PASSWORD` (distinct strings, generated per run). Every later test that registers or logs in a user imports from here.

- [ ] **Step 1: Create the module**

`backend/tests/credentials.py`:

```python
"""Passwords for test users, generated fresh on every run so none are hardcoded in the repo."""
import secrets

PASSWORD = secrets.token_urlsafe(16)        # the password every test user is registered with
OTHER_PASSWORD = secrets.token_urlsafe(16)  # a second valid password (e.g. the new one in a password change)
WRONG_PASSWORD = secrets.token_urlsafe(16)  # never set on any account
```

- [ ] **Step 2: Replace every literal**

- `conftest.py` `auth_headers`: add `from credentials import PASSWORD` at the top of the fixture body (or module) and use `PASSWORD` in both the register and login calls instead of the password literal.
- `api_helpers.py`: `from credentials import PASSWORD`; `def enable_2fa(client, headers, password=PASSWORD):`.
- `test_change_password.py`: `from credentials import PASSWORD, OTHER_PASSWORD, WRONG_PASSWORD`; `OLD = PASSWORD  # password of the auth_headers fixture's user "tester"`; `NEW = OTHER_PASSWORD`; replace every `WRONG_PASSWORD` with `WRONG_PASSWORD`; replace `"12345"` (the too-short password) with `"x" * 5`.
- `test_token_version.py`: `from credentials import PASSWORD`; replace each password literal with `PASSWORD`.
- `test_two_factor_login.py` and `test_two_factor_manage.py`: the module-level `PASSWORD` literal → `from credentials import PASSWORD` (delete the assignment; keep any comment on its own line).
- `test_restore_api.py` `login_as_other`: `from credentials import PASSWORD` and use it in both calls.

- [ ] **Step 3: Verify nothing is left**

Run a grep over `backend/tests` for the three passwords the tests used to hardcode (current, new and wrong) → no output.

- [ ] **Step 4: Run the full suite**

Expected: `154 passed`.

- [ ] **Step 5: Commit** — message `test: generate test passwords at runtime instead of hardcoding them`.

---

### Task 2: Finite, bounded inputs everywhere

**Files:**
- Modify: `backend/models.py` (imports; new constants and `InputModel`; the Base/Create/Update/Restore models of assets, liabilities, bank accounts, insurances, mutual funds, equities, goal, `SnapshotRestore`)
- Modify: `backend/database.py` (`_equity_numbers`; `_new_equity_row`, `update_equity`, `update_equity_price` use it)
- Test: `backend/tests/test_input_limits.py` (create)

**Interfaces:**
- Produces: `models.InputModel`, `models.MAX_AMOUNT = 1e15`, `models.MAX_QUANTITY = 1e9`, `models.MAX_UNITS = 1e12`; `database._equity_numbers(quantity, avg_price, current_price) -> dict` with `invested_amount`, `current_value`, `gain_loss`, `gain_loss_percent` (0 when invested < 0.01). Task 6 adds fields to these models and must keep `InputModel` as their base.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_input_limits.py`:

```python
import pytest

pytestmark = pytest.mark.usefixtures("offline_markets")


@pytest.mark.parametrize("path, body", [
    ("/api/assets", {"name": "Test flat", "value": "inf", "category": "real_estate"}),
    ("/api/assets", {"name": "Test flat", "value": 2e15, "category": "real_estate"}),
    ("/api/liabilities", {"name": "Test loan", "amount": "NaN", "category": "mortgage"}),
    ("/api/bank-accounts", {"bank_name": "Test Bank", "account_number": "00001234",
                            "account_type": "savings", "balance": "-Infinity"}),
    ("/api/insurances", {"policy_name": "Test term", "provider": "Test Insurer", "insurance_type": "term",
                         "sum_assured": 2e15, "premium": 1}),
    ("/api/mutual-funds", {"fund_name": "Test index", "amc": "Test AMC", "category": "index",
                           "invested_amount": 1, "units": 2e12}),
    ("/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 2_000_000_000, "avg_buy_price": 1}),
    ("/api/goal", {"target_amount": "inf"}),
])
def test_writes_reject_non_finite_and_out_of_range_numbers(client, auth_headers, path, body):
    assert client.post(path, headers=auth_headers, json=body).status_code == 422


def test_updates_reject_non_finite_numbers_and_keep_the_row(client, auth_headers):
    asset = client.post("/api/assets", headers=auth_headers,
                        json={"name": "Test flat", "value": 100, "category": "real_estate"}).json()

    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"value": "inf"})

    assert resp.status_code == 422
    assert client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()["value"] == 100


def test_a_tiny_invested_amount_gives_zero_percent_instead_of_infinity(client, auth_headers):
    resp = client.post("/api/equities", headers=auth_headers,
                       json={"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 1e-300})
    assert resp.status_code == 201
    equity = resp.json()

    resp = client.put(f"/api/equities/{equity['id']}", headers=auth_headers, json={"current_price": 1e15})

    assert resp.status_code == 200
    assert resp.json()["gain_loss_percent"] == 0
    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200
```

- [ ] **Step 2: Run them to verify they fail**

Run: `tests/test_input_limits.py -q`. Expected: the "inf"/"NaN"/2e15/2e12/2e9 cases and the percent test FAIL (201 or a 500); the percent test's PUT returns 500 because `1e15 / 1e-300` overflows.

- [ ] **Step 3: Models**

In `backend/models.py`:

1. First line becomes `from pydantic import BaseModel, ConfigDict, Field, field_validator`.
2. After the imports add:

```python
# Upper bounds on user-entered numbers: far above any real holding, low enough that products and sums
# of stored values can never overflow a float.
MAX_AMOUNT = 1e15      # any rupee (or dollar) amount
MAX_QUANTITY = 1e9     # shares
MAX_UNITS = 1e12       # mutual fund units


class InputModel(BaseModel):
    """Base for every model that accepts user input: rejects NaN and ±Infinity in any float field."""
    model_config = ConfigDict(allow_inf_nan=False)
```

3. Change the base class from `BaseModel` to `InputModel` for: `AssetBase`, `AssetUpdate`, `LiabilityBase`, `LiabilityUpdate`, `SnapshotRestore`, `BankAccountBase`, `BankAccountUpdate`, `InsuranceBase`, `InsuranceUpdate`, `MutualFundBase`, `MutualFundUpdate`, `EquityBase`, `EquityCreate`, `EquityUpdate`, `GoalBase`, `GoalUpdate`. (`EquityRestore` inherits `EquityCreate`.)
4. Add `le=MAX_AMOUNT` to these fields, in both the Base/Create model and the Update model (keep their existing `ge=`):
   - asset `value`; liability `amount`; bank account `balance`; insurance `sum_assured`, `premium`; mutual fund `avg_nav`, `invested_amount`; equity `avg_buy_price`, `current_price` (Base, Update and `EquityRestore`); goal `target_amount`.
5. Mutual fund optional numbers gain bounds (Base and Update): `current_nav: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)`, `current_value: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)`, `sip_amount: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)`; `units` gets `le=MAX_UNITS` (Base: `Field(default=0, ge=0, le=MAX_UNITS)`, Update: `Field(None, ge=0, le=MAX_UNITS)`). Keep the existing comments.
6. Equity `quantity` gets `le=MAX_QUANTITY` in `EquityBase`, `EquityCreate` and `EquityUpdate`.
7. `SnapshotRestore`: `total_assets: float = Field(..., ge=0, le=1e18)` and `total_liabilities: float = Field(..., ge=0, le=1e18)`.

- [ ] **Step 4: One place for equity numbers**

In `backend/database.py`, after `_new_row`, add:

```python
def _equity_numbers(quantity: float, avg_price: float, current_price: float) -> Dict:
    """Invested amount, value and gain for a holding. The percent is 0 below one paisa invested,
    where it would be meaningless (and can overflow to infinity)."""
    invested = quantity * avg_price
    current_value = quantity * current_price
    gain_loss = current_value - invested
    return {
        "invested_amount": invested,
        "current_value": current_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": gain_loss / invested * 100 if invested >= 0.01 else 0,
    }
```

Then:
- `_new_equity_row`: keep the `current_price` fallback; replace the `invested`/`current_value`/`gain_loss` lines and the four computed dict entries with `**_equity_numbers(quantity, avg_price, current_price),` inside the `_new_row` fields (after `"current_price": current_price,`).
- `update_equity`: after applying the updates, replace the "Recalculate values" block with:

```python
            row = data["equities"][i]
            current_price = row.get("current_price")
            if current_price is None:
                current_price = row["avg_buy_price"]
            row.update(_equity_numbers(row["quantity"], row["avg_buy_price"], current_price))
            row["updated_at"] = get_timestamp()
```

- `update_equity_price`: replace its computed lines with `data["equities"][i]["current_price"] = current_price` followed by `data["equities"][i].update(_equity_numbers(equity["quantity"], equity["avg_buy_price"], current_price))`, then the existing `updated_at`/save/return.

- [ ] **Step 5: Run the full suite** — expected `164 passed`.

- [ ] **Step 6: Commit** — `fix: reject non-finite and out-of-range numbers on every write`.

---

### Task 3: Temp-file mode before write; timezone-aware export date

**Files:**
- Modify: `backend/database.py` (`save_data`), `backend/main.py` (`export_user_data`; datetime import)
- Test: `backend/tests/test_atomic_save.py` (add 1 test), `backend/tests/test_restore_api.py` (add 1 test)

- [ ] **Step 1: Failing tests**

Append to `backend/tests/test_atomic_save.py` (it already imports `json`, `os`, `pytest`; add `import stat` at the top if missing):

```python
def test_the_temp_file_has_the_final_mode_before_any_data_is_written(data_file, monkeypatch):
    import database as db

    db.save_data({"users": []})
    os.chmod(data_file, 0o600)
    modes_while_writing = []
    real_dump = json.dump

    def spy(obj, f, **kwargs):
        modes_while_writing.append(stat.S_IMODE(os.fstat(f.fileno()).st_mode))
        return real_dump(obj, f, **kwargs)

    monkeypatch.setattr(json, "dump", spy)
    db.save_data({"users": []})

    assert modes_while_writing == [0o600]
```

Append to `backend/tests/test_restore_api.py`:

```python
def test_export_date_carries_a_timezone(client, auth_headers):
    from datetime import datetime

    assert datetime.fromisoformat(export(client, auth_headers)["export_date"]).tzinfo is not None
```

- [ ] **Step 2: Run them; both FAIL** (mode is the default while writing; export date is naive).

- [ ] **Step 3: Implement**

`save_data`: move the `shutil.copymode` call to directly after opening the temp file, before `json.dump`:

```python
        with open(tmp_file, 'w') as f:
            if os.path.exists(data_file):
                shutil.copymode(data_file, tmp_file)  # permissions first, so the data is never readable more widely
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, data_file)
```

(delete the old copymode lines after the `with` block).

`main.py`: change `from datetime import datetime, timedelta` to `from datetime import datetime, timedelta, timezone`; in `export_user_data` delete the local `from datetime import datetime` line and set `"export_date": datetime.now(timezone.utc).isoformat(),`.

- [ ] **Step 4: Full suite** — `166 passed`.

- [ ] **Step 5: Commit** — `fix: set the temp file's mode before writing; timezone-aware export date`.

---

### Task 4: Valuation module — dates, revaluation, deposits, totals

**Files:**
- Create: `backend/valuation.py`
- Modify: `backend/tests/conftest.py` (add `frozen_today`)
- Test: `backend/tests/test_valuation.py` (create)

**Interfaces:**
- Produces (all used by Tasks 5, 7, 8): `today()`, `parse_date(s)`, `add_months(d, n)`, `months_between(start, end)`, `asset_current_value(asset, on)`, `asset_view(asset, on)`, `deposit_status(account, on)` → `{"current_value", "maturity_value", "matured", "days_to_maturity"}`, `bank_account_view(account, on)`, `equity_value_inr(equity, usd_to_inr)`, `async usd_rate_if_needed(equities)`, `portfolio_totals(assets, liabilities, bank_accounts, mutual_funds, equities, usd_to_inr, on)` (keys `total_assets`, `total_liabilities`, `net_worth`, `assets_by_category`, `liabilities_by_category`, `asset_count`, `liability_count`), `upcoming_maturities(bank_accounts, on, within_days=30)`. `portfolio_totals` calls `loan_status(l, on)["outstanding"]`; Task 4 adds a minimal `loan_status` returning `{"outstanding": amount}` that Task 5 replaces.
- Fixture `frozen_today`: dict `{"date": date(2026, 10, 14)}`; assigning `frozen_today["date"]` moves `valuation.today()`.

- [ ] **Step 1: Fixture**

Append to `backend/tests/conftest.py`:

```python


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze valuation.today(); move it by assigning frozen_today["date"]."""
    from datetime import date

    import valuation

    state = {"date": date(2026, 10, 14)}
    monkeypatch.setattr(valuation, "today", lambda: state["date"])
    return state
```

- [ ] **Step 2: Failing tests**

`backend/tests/test_valuation.py`:

```python
import asyncio
from datetime import date

import pytest

import exchange_service
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
```

(27 tests: 8 + 4 parametrized cases, 15 plain.)

- [ ] **Step 3: Run; collection ERROR** (`No module named 'valuation'`).

- [ ] **Step 4: Create `backend/valuation.py`**

```python
"""What each holding is worth on a given day: revaluation, FD/RD interest, loan amortization, totals.

Pure functions over stored rows plus a date; nothing here reads or writes storage.
Endpoints call `today()` so tests can freeze the date.
"""
import calendar
from datetime import date
from typing import Dict, List, Optional

import exchange_service
from models import USD_MARKETS


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

def asset_current_value(asset: Dict, on: date) -> float:
    rate = asset.get("annual_change_rate")
    since = parse_date(asset.get("valuation_date"))
    if rate is None or since is None:
        return asset["value"]
    years = (on - since).days / 365.25
    if years <= 0:
        return asset["value"]
    return asset["value"] * (1 + rate / 100) ** years


def asset_view(asset: Dict, on: date) -> Dict:
    return {**asset, "current_value": round(asset_current_value(asset, on), 2)}


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
    return sorted(due, key=lambda m: m["maturity_date"])


# ---------- Loans ----------

def loan_status(liability: Dict, on: date) -> Dict:
    """Placeholder until amortization lands: the stored amount is the outstanding balance."""
    return {"outstanding": liability["amount"]}


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
    for asset in assets:
        assets_by_category[asset["category"]] = (
            assets_by_category.get(asset["category"], 0) + asset_current_value(asset, on))
    buckets = {
        "equities": sum(equity_value_inr(e, usd_to_inr) for e in equities),
        "bank_accounts": sum(deposit_status(b, on)["current_value"] for b in bank_accounts),
        "mutual_funds": sum(m.get("current_value") or 0 for m in mutual_funds),
    }
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
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "assets_by_category": assets_by_category,
        "liabilities_by_category": liabilities_by_category,
        "asset_count": len(assets) + len(equities) + len(bank_accounts) + len(mutual_funds),
        "liability_count": len(liabilities),
    }
```

- [ ] **Step 5: Run `tests/test_valuation.py`** — 27 passed. Full suite — `193 passed`.

- [ ] **Step 6: Commit** — `feat: add valuation module for revaluation, deposits and totals`.

---

### Task 5: Loan amortization

**Files:**
- Modify: `backend/valuation.py` (replace the `loan_status` placeholder; add `emi_for_tenure`, `loan_schedule`, `liability_view`)
- Test: `backend/tests/test_valuation.py` (append 13 tests)

**Interfaces:**
- Produces: `emi_for_tenure(principal, annual_rate, months) -> float`; `loan_status(liability, on) -> dict` with `outstanding`, `amortized`, `months_remaining`, `payoff_date`, `interest_remaining`, `next_emi_interest`, `next_emi_principal`, `emi_too_low`; `loan_schedule(liability, on) -> list` of `{"year", "paid", "interest", "principal", "closing_balance"}`; `liability_view(liability, on)`.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_valuation.py`:

```python
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
```

- [ ] **Step 2: Run; the new tests FAIL** (`emi_for_tenure` missing; placeholder `loan_status`).

- [ ] **Step 3: Implement** — in `backend/valuation.py` replace the whole "Loans" section with:

```python
# ---------- Loans ----------
# A loan is amortized when it has an EMI and a balance date: `amount` was the balance on `balance_date`
# and one EMI is paid on every monthly anniversary of that date.

PAID_OFF = 0.005            # a balance at or below half a paisa counts as cleared
MAX_SCHEDULE_MONTHS = 1200  # don't project payoffs more than 100 years out

_NOT_AMORTIZED = {
    "amortized": False, "months_remaining": None, "payoff_date": None, "interest_remaining": None,
    "next_emi_interest": None, "next_emi_principal": None, "emi_too_low": False,
}


def emi_for_tenure(principal: float, annual_rate: float, months: int) -> float:
    r = annual_rate / 1200
    if r == 0:
        return round(principal / months, 2)
    growth = (1 + r) ** months
    return round(principal * r * growth / (growth - 1), 2)


def _remaining_payments(balance: float, r: float, emi: float, start: date) -> Optional[List[Dict]]:
    """Monthly payments from `balance` (owed on `start`) until cleared; None past MAX_SCHEDULE_MONTHS.
    The caller guarantees the EMI exceeds the first month's interest."""
    payments: List[Dict] = []
    while balance > PAID_OFF:
        if len(payments) == MAX_SCHEDULE_MONTHS:
            return None
        interest = balance * r
        payment = min(emi, balance + interest)
        balance -= payment - interest
        payments.append({"date": add_months(start, len(payments) + 1), "payment": payment, "interest": interest,
                         "principal": payment - interest, "balance": max(balance, 0.0)})
    return payments


def _loan_projection(liability: Dict, on: date):
    """(status, remaining payments or None) for `liability` as of `on`."""
    emi = liability.get("emi")
    anchor = parse_date(liability.get("balance_date"))
    if not emi or anchor is None:
        return {"outstanding": liability["amount"], **_NOT_AMORTIZED}, None

    r = (liability.get("interest_rate") or 0) / 1200
    paid = months_between(anchor, on)
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
                "emi_too_low": False}, []

    status = {"outstanding": round(balance, 2), "amortized": True, "months_remaining": None, "payoff_date": None,
              "interest_remaining": None, "next_emi_interest": None, "next_emi_principal": None,
              "emi_too_low": emi <= balance * r}
    if status["emi_too_low"]:
        return status, None

    status["next_emi_interest"] = round(balance * r, 2)
    status["next_emi_principal"] = round(min(emi, balance * (1 + r)) - balance * r, 2)
    payments = _remaining_payments(balance, r, emi, add_months(anchor, paid))
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
```

- [ ] **Step 4: Run `tests/test_valuation.py`** — 40 passed. Full suite — `206 passed`.

- [ ] **Step 5: Commit** — `feat: amortize loans from an EMI and a balance date`.

---

### Task 6: New fields, computed response fields, clearing

**Files:**
- Modify: `backend/models.py` (imports; `IsoDate`; new fields; response fields; `DashboardMetrics`)
- Modify: `backend/database.py` (`_apply_update`, clearable sets; `update_asset`/`update_liability`/`update_bank_account`)
- Test: `backend/tests/test_new_fields.py` (create)

**Interfaces:**
- Produces: `models.IsoDate`; new optional input fields per spec §3.2 on Base and Update models; computed response fields per spec §3.4 (with defaults so stored rows validate); `DashboardMetrics.maturities: List[dict] = []`; `database.ASSET_CLEARABLE`, `LIABILITY_CLEARABLE`, `BANK_ACCOUNT_CLEARABLE`; `database._apply_update(row, update_data, clearable)`.

- [ ] **Step 1: Failing tests** — `backend/tests/test_new_fields.py`:

```python
import pytest
from pydantic import ValidationError

import database as db
from models import AssetCreate, BankAccountCreate, LiabilityCreate


@pytest.fixture(autouse=True)
def data_file(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


@pytest.mark.parametrize("value", ["2026-02-30", "1899-12-31", "2026-10-14T10:00", "soon"])
def test_bad_dates_are_rejected(value):
    with pytest.raises(ValidationError, match="Invalid date"):
        AssetCreate(name="Test car", value=1, category="vehicles", valuation_date=value)


def test_dates_are_normalized():
    assert AssetCreate(name="Test car", value=1, category="vehicles", valuation_date="20261014").valuation_date == "2026-10-14"


def test_new_fields_have_their_bounds():
    with pytest.raises(ValidationError):
        AssetCreate(name="Test car", value=1, category="vehicles", annual_change_rate=-100)
    with pytest.raises(ValidationError):
        LiabilityCreate(name="Test loan", amount=1, category="mortgage", emi=0)
    with pytest.raises(ValidationError):
        LiabilityCreate(name="Test loan", amount=1, category="mortgage", tenure_months=601)
    with pytest.raises(ValidationError):
        BankAccountCreate(bank_name="Test Bank", account_number="00001234", account_type="rd", balance=0,
                          monthly_deposit=0)


@pytest.mark.parametrize("create, update, field, value", [
    ("create_asset", "update_asset", "annual_change_rate", -15),
    ("create_liability", "update_liability", "emi", 5000),
    ("create_bank_account", "update_bank_account", "maturity_date", "2027-01-01"),
])
def test_clearable_fields_can_be_cleared(create, update, field, value):
    base = {
        "create_asset": {"name": "Test car", "value": 5, "category": "vehicles"},
        "create_liability": {"name": "Test loan", "amount": 5, "category": "mortgage"},
        "create_bank_account": {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "fd",
                                "balance": 5},
    }[create]
    row = getattr(db, create)("me", {**base, field: value})

    updated = getattr(db, update)(row["id"], "me", {field: None})

    assert updated[field] is None


def test_none_for_a_field_that_is_not_clearable_is_still_ignored():
    row = db.create_asset("me", {"name": "Test car", "value": 5, "category": "vehicles"})

    updated = db.update_asset(row["id"], "me", {"name": None, "value": 7})

    assert updated["name"] == "Test car" and updated["value"] == 7
```

(10 tests: 4 bad dates, 1 normalized, 1 bounds, 3 clearable, 1 not clearable.)

- [ ] **Step 2: Run; FAIL** (unknown fields ignored, no `Invalid date`, clearing ignored).

- [ ] **Step 3: Models**

1. Imports: `from typing import Annotated, Optional, List`; `from datetime import date, datetime`; `from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator`.
2. After `InputModel` add:

```python
def _iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid date")
    if not 1900 <= parsed.year <= 2200:
        raise ValueError("Invalid date")
    return parsed.isoformat()


# A calendar date stored as "YYYY-MM-DD"
IsoDate = Annotated[str, AfterValidator(_iso_date)]
```

3. `AssetBase` and `AssetUpdate` gain:

```python
    annual_change_rate: Optional[float] = Field(None, ge=-99, le=100)  # % per year; negative depreciates
    valuation_date: Optional[IsoDate] = None  # the date `value` was accurate
```

   `Asset` (response) gains `current_value: float = 0`.
4. `LiabilityBase` and `LiabilityUpdate` gain:

```python
    emi: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)
    balance_date: Optional[IsoDate] = None  # the date `amount` was the balance; EMIs fall on its anniversaries
    tenure_months: Optional[int] = Field(None, ge=1, le=600)  # input helper: EMI is derived from it when not given
```

   `Liability` (response) gains:

```python
    outstanding: float = 0
    amortized: bool = False
    months_remaining: Optional[int] = None
    payoff_date: Optional[str] = None
    interest_remaining: Optional[float] = None
    next_emi_interest: Optional[float] = None
    next_emi_principal: Optional[float] = None
    emi_too_low: bool = False
```

5. `BankAccountBase` and `BankAccountUpdate` gain:

```python
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # FD/RD only, % per year
    start_date: Optional[IsoDate] = None
    maturity_date: Optional[IsoDate] = None
    monthly_deposit: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)  # RD installment
```

   `BankAccount` (response) gains `current_value: float = 0`, `maturity_value: Optional[float] = None`, `matured: bool = False`, `days_to_maturity: Optional[int] = None`.
6. `DashboardMetrics` gains `maturities: List[dict] = []`.

- [ ] **Step 4: Clearing in `database.py`**

After `_equity_numbers` add:

```python
# Optional fields a PUT may clear by sending null; any other null in an update is ignored
ASSET_CLEARABLE = frozenset({"description", "annual_change_rate", "valuation_date"})
LIABILITY_CLEARABLE = frozenset({"interest_rate", "description", "emi", "balance_date", "tenure_months"})
BANK_ACCOUNT_CLEARABLE = frozenset({"branch", "ifsc_code", "interest_rate", "start_date", "maturity_date",
                                    "monthly_deposit"})


def _apply_update(row: Dict, update_data: Dict, clearable: frozenset = frozenset()) -> None:
    for key, value in update_data.items():
        if value is not None or key in clearable:
            row[key] = value
    row["updated_at"] = get_timestamp()
```

In `update_asset`, `update_liability` and `update_bank_account`, replace the `for key, value …` loop and the `updated_at` line with `_apply_update(data["<collection>"][i], update_data, <SET>_CLEARABLE)`.

- [ ] **Step 5: Full suite** — `216 passed`.

- [ ] **Step 6: Commit** — `feat: add revaluation, EMI and deposit fields; allow clearing optional fields`.

---

### Task 7: Endpoints use the valuation module

**Files:**
- Modify: `backend/main.py` (imports; asset/liability/bank routes; schedule route; dashboard; snapshot; bank and equities summaries)
- Test: `backend/tests/test_valuation_api.py` (create)

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces: computed fields on every asset/liability/bank-account response; `GET /api/liabilities/{id}/schedule`; `DashboardMetrics.maturities`. Tasks 10–13 rely on these exact field names.

- [ ] **Step 1: Failing tests** — `backend/tests/test_valuation_api.py`:

```python
import json
from datetime import date

import pytest

import exchange_service

pytestmark = pytest.mark.usefixtures("offline_markets")


def post(client, headers, path, body):
    resp = client.post(path, headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


CAR = {"name": "Test car", "value": 1_200_000, "category": "vehicles", "annual_change_rate": -15}
LOAN = {"name": "Test loan", "amount": 1_000_000, "category": "personal_loan", "interest_rate": 12}
FD = {"bank_name": "Test Bank", "account_number": "00001234", "account_type": "fd", "balance": 100_000,
      "interest_rate": 7, "start_date": "2025-10-14", "maturity_date": "2026-11-13"}


def test_revalued_asset_gets_todays_date_and_a_current_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, "/api/assets", CAR)
    assert asset["valuation_date"] == "2026-10-14"
    assert asset["current_value"] == 1_200_000

    frozen_today["date"] = date(2030, 10, 14)  # 1461 days later
    [listed] = client.get("/api/assets", headers=auth_headers).json()
    assert listed["current_value"] == pytest.approx(626_407.50, abs=0.01)


def test_tenure_fills_the_emi_and_the_balance_date(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 1, 15)
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12})
    assert loan["emi"] == 88_848.79
    assert loan["balance_date"] == "2026-01-15"
    assert loan["amortized"] is True and loan["months_remaining"] == 12

    frozen_today["date"] = date(2026, 2, 15)
    got = client.get(f"/api/liabilities/{loan['id']}", headers=auth_headers).json()
    assert got["outstanding"] == pytest.approx(921_151.21, abs=0.01)
    assert got["payoff_date"] == "2027-01-15"


def test_an_explicit_emi_wins_over_the_tenure(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12, "emi": 90_000})
    assert loan["emi"] == 90_000


def test_updating_the_tenure_recomputes_the_emi(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", LOAN)
    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers, json={"tenure_months": 12})
    assert resp.json()["emi"] == 88_848.79
    assert resp.json()["balance_date"] == "2026-10-14"


def test_clearing_the_emi_makes_the_loan_manual_again(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 20_000})
    resp = client.put(f"/api/liabilities/{loan['id']}", headers=auth_headers, json={"emi": None})
    assert resp.json()["amortized"] is False
    assert resp.json()["outstanding"] == 1_000_000


def test_schedule_endpoint(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 1, 15)
    loan = post(client, auth_headers, "/api/liabilities", {**LOAN, "tenure_months": 12})
    frozen_today["date"] = date(2026, 2, 15)

    body = client.get(f"/api/liabilities/{loan['id']}/schedule", headers=auth_headers).json()

    assert [r["year"] for r in body["rows"]] == [2026, 2027]
    assert body["months_remaining"] == 11 and body["payoff_date"] == "2027-01-15"


def test_schedule_of_a_manual_liability_is_400(client, auth_headers, frozen_today):
    loan = post(client, auth_headers, "/api/liabilities", LOAN)
    resp = client.get(f"/api/liabilities/{loan['id']}/schedule", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "This liability has no EMI set"


def test_schedule_of_an_unknown_liability_is_404(client, auth_headers, frozen_today):
    assert client.get("/api/liabilities/nope/schedule", headers=auth_headers).status_code == 404


def test_fd_value_and_countdown(client, auth_headers, frozen_today):
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    assert fd["current_value"] == pytest.approx(107_185.90, abs=0.01)
    assert fd["days_to_maturity"] == 30 and fd["matured"] is False
    assert fd["maturity_value"] > fd["current_value"]


def test_maturity_before_start_is_rejected_on_create(client, auth_headers, frozen_today):
    resp = client.post("/api/bank-accounts", headers=auth_headers,
                       json={**FD, "start_date": "2026-01-01", "maturity_date": "2025-12-31"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Maturity date must be after the start date"


def test_maturity_before_start_is_rejected_on_update(client, auth_headers, frozen_today):
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    resp = client.put(f"/api/bank-accounts/{fd['id']}", headers=auth_headers, json={"maturity_date": "2025-01-01"})
    assert resp.status_code == 400
    assert client.get(f"/api/bank-accounts/{fd['id']}", headers=auth_headers).json()["maturity_date"] == "2026-11-13"


def test_dashboard_uses_computed_values_and_lists_maturities(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2022, 10, 14)
    post(client, auth_headers, "/api/assets", CAR)
    frozen_today["date"] = date(2026, 10, 14)
    fd = post(client, auth_headers, "/api/bank-accounts", FD)
    post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 88_848.79, "balance_date": "2026-09-14"})

    metrics = client.get("/api/dashboard", headers=auth_headers).json()

    assert metrics["total_assets"] == pytest.approx(626_407.50 + 107_185.90, abs=0.02)
    assert metrics["total_liabilities"] == pytest.approx(921_151.21, abs=0.01)
    assert [m["id"] for m in metrics["maturities"]] == [fd["id"]]
    assert metrics["maturities"][0]["days_to_maturity"] == 30


def test_snapshot_matches_the_dashboard(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/bank-accounts", FD)
    post(client, auth_headers, "/api/liabilities", {**LOAN, "emi": 88_848.79, "balance_date": "2026-09-14"})

    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    snapshot = client.post("/api/snapshot", headers=auth_headers).json()

    assert snapshot["total_assets"] == pytest.approx(metrics["total_assets"])
    assert snapshot["total_liabilities"] == pytest.approx(metrics["total_liabilities"])


def test_bank_summary_uses_current_values(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/bank-accounts", FD)
    summary = client.get("/api/bank-accounts-summary", headers=auth_headers).json()
    assert summary["total_balance"] == pytest.approx(107_185.90, abs=0.01)


def test_export_holds_inputs_only_and_restores_them(client, auth_headers, frozen_today):
    post(client, auth_headers, "/api/assets", CAR)
    backup = client.get("/api/export", headers=auth_headers).json()
    assert "current_value" not in backup["assets"][0]
    assert backup["assets"][0]["annual_change_rate"] == -15

    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})

    assert resp.status_code == 200
    [asset] = client.get("/api/assets", headers=auth_headers).json()
    assert (asset["annual_change_rate"], asset["valuation_date"]) == (-15, "2026-10-14")


def test_no_rate_fetch_without_us_holdings(client, auth_headers, frozen_today, monkeypatch):
    post(client, auth_headers, "/api/equities", {"symbol": "TEST", "market": "NSE", "quantity": 1, "avg_buy_price": 10})

    async def must_not_be_called():
        raise AssertionError("rate fetched without US holdings")

    monkeypatch.setattr(exchange_service, "fetch_usd_to_inr", must_not_be_called)

    assert client.get("/api/dashboard", headers=auth_headers).status_code == 200
    assert client.get("/api/equities-summary", headers=auth_headers).status_code == 200
```

(16 tests.)

- [ ] **Step 2: Run; FAIL** (no computed fields, no schedule route, old totals).

- [ ] **Step 3: Implement in `main.py`**

1. Add `import valuation` after `import restore`.
2. Above the asset routes add the write-time helpers:

```python
# ============== Write-time defaults ==============

def _today_iso() -> str:
    return valuation.today().isoformat()


def _asset_defaults(row: dict) -> dict:
    """A revalued asset always carries the date its value was true."""
    if row.get("annual_change_rate") is not None and not row.get("valuation_date"):
        return {"valuation_date": _today_iso()}
    return {}


def _liability_defaults(row: dict) -> dict:
    """An EMI needs a balance date to count payments from."""
    if row.get("emi") and not row.get("balance_date"):
        return {"balance_date": _today_iso()}
    return {}


def _emi_from_tenure(changes: dict, current: dict) -> dict:
    """When a tenure is given without an EMI, derive the EMI from the balance and rate."""
    if changes.get("tenure_months") and not changes.get("emi"):
        merged = {**current, **changes}
        return {"emi": valuation.emi_for_tenure(merged["amount"], merged.get("interest_rate") or 0,
                                                changes["tenure_months"])}
    return {}


def _check_deposit_dates(row: dict) -> None:
    start, maturity = row.get("start_date"), row.get("maturity_date")
    if start and maturity and maturity < start:
        raise HTTPException(status_code=400, detail="Maturity date must be after the start date")
```

3. Asset routes return views:

```python
@app.get("/api/assets", response_model=List[Asset])
async def get_assets(user_id: str = Depends(get_user_id)):
    """Get all assets for current user, valued as of today"""
    on = valuation.today()
    return [valuation.asset_view(a, on) for a in db.get_assets_by_user(user_id)]

@app.post("/api/assets", response_model=Asset, status_code=status.HTTP_201_CREATED)
async def create_asset(asset_data: AssetCreate, user_id: str = Depends(get_user_id)):
    """Create a new asset"""
    data = asset_data.model_dump()
    data.update(_asset_defaults(data))
    return valuation.asset_view(db.create_asset(user_id, data), valuation.today())

@app.get("/api/assets/{asset_id}", response_model=Asset)
async def get_asset(asset_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific asset"""
    asset = db.get_asset_by_id(asset_id, user_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return valuation.asset_view(asset, valuation.today())

@app.put("/api/assets/{asset_id}", response_model=Asset)
async def update_asset(asset_id: str, update_data: AssetUpdate, user_id: str = Depends(get_user_id)):
    """Update an asset"""
    asset = db.update_asset(asset_id, user_id, update_data.model_dump(exclude_unset=True))
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    extra = _asset_defaults(asset)
    if extra:
        asset = db.update_asset(asset_id, user_id, extra)
    return valuation.asset_view(asset, valuation.today())
```

4. Liability routes:

```python
@app.get("/api/liabilities", response_model=List[Liability])
async def get_liabilities(user_id: str = Depends(get_user_id)):
    """Get all liabilities for current user, with today's outstanding balance"""
    on = valuation.today()
    return [valuation.liability_view(l, on) for l in db.get_liabilities_by_user(user_id)]

@app.post("/api/liabilities", response_model=Liability, status_code=status.HTTP_201_CREATED)
async def create_liability(liability_data: LiabilityCreate, user_id: str = Depends(get_user_id)):
    """Create a new liability"""
    data = liability_data.model_dump()
    data.update(_emi_from_tenure(data, {}))
    data.update(_liability_defaults(data))
    return valuation.liability_view(db.create_liability(user_id, data), valuation.today())

@app.get("/api/liabilities/{liability_id}", response_model=Liability)
async def get_liability(liability_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific liability"""
    liability = db.get_liability_by_id(liability_id, user_id)
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    return valuation.liability_view(liability, valuation.today())

@app.get("/api/liabilities/{liability_id}/schedule")
async def get_liability_schedule(liability_id: str, user_id: str = Depends(get_user_id)):
    """Remaining EMI payments grouped by year"""
    liability = db.get_liability_by_id(liability_id, user_id)
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    on = valuation.today()
    status_now = valuation.loan_status(liability, on)
    if not status_now["amortized"]:
        raise HTTPException(status_code=400, detail="This liability has no EMI set")
    return {
        "rows": valuation.loan_schedule(liability, on),
        "months_remaining": status_now["months_remaining"],
        "payoff_date": status_now["payoff_date"],
        "interest_remaining": status_now["interest_remaining"],
    }

@app.put("/api/liabilities/{liability_id}", response_model=Liability)
async def update_liability(liability_id: str, update_data: LiabilityUpdate, user_id: str = Depends(get_user_id)):
    """Update a liability"""
    current = db.get_liability_by_id(liability_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Liability not found")
    changes = update_data.model_dump(exclude_unset=True)
    changes.update(_emi_from_tenure(changes, current))
    liability = db.update_liability(liability_id, user_id, changes)
    extra = _liability_defaults(liability)
    if extra:
        liability = db.update_liability(liability_id, user_id, extra)
    return valuation.liability_view(liability, valuation.today())
```

(Keep the delete route as is. `status_now` avoids shadowing FastAPI's `status`.)

5. Bank account routes:

```python
@app.get("/api/bank-accounts", response_model=List[BankAccount])
async def get_bank_accounts(user_id: str = Depends(get_user_id)):
    """Get all bank accounts for current user, FDs/RDs valued as of today"""
    on = valuation.today()
    return [valuation.bank_account_view(a, on) for a in db.get_bank_accounts_by_user(user_id)]

@app.post("/api/bank-accounts", response_model=BankAccount, status_code=status.HTTP_201_CREATED)
async def create_bank_account(account_data: BankAccountCreate, user_id: str = Depends(get_user_id)):
    """Create a new bank account"""
    data = account_data.model_dump()
    _check_deposit_dates(data)
    return valuation.bank_account_view(db.create_bank_account(user_id, data), valuation.today())

@app.get("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def get_bank_account(account_id: str, user_id: str = Depends(get_user_id)):
    """Get a specific bank account"""
    account = db.get_bank_account_by_id(account_id, user_id)
    if not account:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return valuation.bank_account_view(account, valuation.today())

@app.put("/api/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, update_data: BankAccountUpdate, user_id: str = Depends(get_user_id)):
    """Update a bank account"""
    current = db.get_bank_account_by_id(account_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Bank account not found")
    changes = update_data.model_dump(exclude_unset=True)
    _check_deposit_dates({**current, **changes})
    account = db.update_bank_account(account_id, user_id, changes)
    return valuation.bank_account_view(account, valuation.today())

@app.get("/api/bank-accounts-summary")
async def get_bank_accounts_summary(user_id: str = Depends(get_user_id)):
    """Get the total value of all bank accounts (FDs/RDs include interest earned so far)"""
    on = valuation.today()
    accounts = db.get_bank_accounts_by_user(user_id)
    total = sum(valuation.deposit_status(a, on)["current_value"] for a in accounts)
    return {"total_balance": total, "account_count": len(accounts)}
```

6. Dashboard and snapshot — replace both functions with:

```python
async def _portfolio_totals(user_id: str, on) -> dict:
    equities = db.get_equities_by_user(user_id)
    return valuation.portfolio_totals(
        assets=db.get_assets_by_user(user_id),
        liabilities=db.get_liabilities_by_user(user_id),
        bank_accounts=db.get_bank_accounts_by_user(user_id),
        mutual_funds=db.get_mutual_funds_by_user(user_id),
        equities=equities,
        usd_to_inr=await valuation.usd_rate_if_needed(equities),
        on=on,
    )

@app.get("/api/dashboard", response_model=DashboardMetrics)
async def get_dashboard(user_id: str = Depends(get_user_id)):
    """Get dashboard metrics, valued as of today"""
    on = valuation.today()
    totals = await _portfolio_totals(user_id, on)
    ratio = totals["total_liabilities"] / totals["total_assets"] * 100 if totals["total_assets"] > 0 else 0
    return DashboardMetrics(
        **totals,
        debt_to_asset_ratio=round(ratio, 2),
        net_worth_history=db.get_snapshots_by_user(user_id),
        maturities=valuation.upcoming_maturities(db.get_bank_accounts_by_user(user_id), on),
    )

@app.post("/api/snapshot", response_model=NetWorthSnapshot, status_code=status.HTTP_201_CREATED)
async def create_snapshot(user_id: str = Depends(get_user_id)):
    """Create a net worth snapshot"""
    totals = await _portfolio_totals(user_id, valuation.today())
    return db.create_snapshot(user_id, totals["total_assets"], totals["total_liabilities"])
```

7. `get_equities_summary`: replace `usd_to_inr = await exchange_service.fetch_usd_to_inr()` with `usd_to_inr = await valuation.usd_rate_if_needed(equities)`.
8. If `USD_MARKETS` is now unused in `main.py` other than `get_equities_summary`, keep the import (it is still used there).

- [ ] **Step 4: Full suite** — `232 passed`.

- [ ] **Step 5: Commit** — `feat: serve values computed as of today; loan schedule endpoint; maturities on the dashboard`.

---

### Task 8: Demo data and README

**Files:**
- Modify: `backend/main.py` (`startup_event` sample data), `README.md`
- Test: `backend/tests/test_valuation_api.py` (append 1 test)

- [ ] **Step 1: Failing test** — append:

```python
def test_demo_data_shows_off_the_new_features(client, monkeypatch, frozen_today):
    import asyncio

    import database as db
    import main
    import valuation
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())

    demo_id = db.get_user_by_username("demo")["id"]
    on = valuation.today()
    loans = [valuation.loan_status(l, on) for l in db.get_liabilities_by_user(demo_id)]
    assert sum(1 for s in loans if s["amortized"]) == 2
    assert [m["days_to_maturity"] for m in valuation.upcoming_maturities(db.get_bank_accounts_by_user(demo_id), on)] == [20]
    revalued = [a for a in db.get_assets_by_user(demo_id) if a.get("annual_change_rate") is not None]
    assert len(revalued) == 1
```

- [ ] **Step 2: Run; FAIL.**

- [ ] **Step 3: Implement** — in `startup_event` (only the rows created for a new demo user; nothing else changes):
- Compute once near the top: `on = valuation.today()` and `iso = lambda d: d.isoformat()`; use `timedelta` (already imported) and `valuation.add_months`.
- `Honda City` asset: add `"annual_change_rate": -15, "valuation_date": iso(valuation.add_months(on, -12))`.
- `Home Loan - SBI`: add `"emi": 52000, "balance_date": iso(valuation.add_months(on, -6))`. `Car Loan - HDFC`: add `"emi": 12500, "balance_date": iso(valuation.add_months(on, -6))`.
- `Axis Bank` FD: add `"interest_rate": 7.1, "start_date": iso(on - timedelta(days=200)), "maturity_date": iso(on + timedelta(days=20))`.

README: in Features → Asset & Liability Management add bullets for yearly change rates (vehicles depreciate, property appreciates), EMI loans (outstanding balance, payoff date, interest left, yearly schedule); in Financial Sections → Bank Accounts mention FD/RD interest (quarterly compounding), maturity value and the dashboard's "deposits maturing" card; in the API tables add `GET /api/liabilities/{id}/schedule`; under Security add "Every number must be finite and within sane limits (amounts up to 10^15)". Keep the README's tone; no personal data.

- [ ] **Step 4: Full suite** — `233 passed`.

- [ ] **Step 5: Commit** — `feat: demo data for EMIs, FD maturity and depreciation; document Round 2 features`.

---

### Task 9: Frontend shared utils and Round 1 polish

**Files:**
- Modify: `frontend/src/utils/errors.js`
- Create: `frontend/src/utils/markets.js`, `frontend/src/utils/backup.js`
- Modify: `frontend/src/pages/{Assets,BankAccounts,Equities,Insurances,Liabilities,MutualFunds,Register}.jsx`, `frontend/src/components/{Layout,RestoreDialog}.jsx`, `frontend/src/utils/reportGenerator.js`

- [ ] **Step 1: `errors.js`** — replace the file:

```js
// FastAPI puts a human-readable message in `detail`; validation errors (422) carry an array of
// { loc, msg } objects instead, shown here as "field: message; field: message".
export const errorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc.filter((part) => part !== 'body').join('.') : '';
        const msg = typeof d?.msg === 'string' ? d.msg : 'Invalid value';
        return field ? `${field}: ${msg}` : msg;
      })
      .join('; ');
  }
  return fallback;
};
```

- [ ] **Step 2: Use it everywhere** — in each file below add `import { errorMessage } from '../utils/errors';` and replace the expression:
- `Assets.jsx`: `err.response?.data?.detail || 'Failed to save asset'` → `errorMessage(err, 'Failed to save asset')`
- `BankAccounts.jsx`: `… 'Failed to save bank account'`; `Equities.jsx`: `'Failed to save equity'`; `Insurances.jsx`: `'Failed to save insurance'`; `Liabilities.jsx`: `'Failed to save liability'`; `MutualFunds.jsx`: `'Failed to save mutual fund'`; `Register.jsx`: `'Registration failed. Please try again.'`; `RestoreDialog.jsx`: `'Restore failed'`.
- Afterwards `grep -rn "data?.detail ||" frontend/src` → no output.

- [ ] **Step 3: `markets.js`** (new):

```js
// US listings are priced in USD and converted to INR wherever values are totalled.
export const USD_MARKETS = ['NASDAQ', 'NYSE'];
export const isUsdMarket = (market) => USD_MARKETS.includes(market);
// Used when the live USD→INR rate can't be fetched.
export const DEFAULT_USD_TO_INR = 83.5;
```

`Equities.jsx`: delete its local `DEFAULT_USD_TO_INR`, `USD_MARKETS` and `isUsdMarket` (and their comment) and add `import { DEFAULT_USD_TO_INR, isUsdMarket } from '../utils/markets';`. `reportGenerator.js`: delete its local `DEFAULT_USD_TO_INR` and `USD_MARKETS`, add `import { DEFAULT_USD_TO_INR, isUsdMarket } from './markets';`, and replace `USD_MARKETS.includes(e.market)` with `isUsdMarket(e.market)`.

- [ ] **Step 4: `backup.js`** (new):

```js
// Sections of a backup file, in the order the restore dialog lists them.
export const BACKUP_SECTIONS = [
  { key: 'assets', label: 'Assets' },
  { key: 'liabilities', label: 'Liabilities' },
  { key: 'bank_accounts', label: 'Bank accounts' },
  { key: 'insurances', label: 'Insurances' },
  { key: 'mutual_funds', label: 'Mutual funds' },
  { key: 'equities', label: 'Equities' },
  { key: 'snapshots', label: 'Snapshots' },
];

export const countOf = (data, key) => (Array.isArray(data?.[key]) ? data[key].length : 0);

// Same shape check the server makes first: a JSON object with at least one known section.
export const looksLikeBackup = (data) =>
  data !== null && typeof data === 'object' && !Array.isArray(data) &&
  [...BACKUP_SECTIONS.map((s) => s.key), 'goal'].some((key) => key in data);
```

- [ ] **Step 5: `Layout.jsx`** — add `import { looksLikeBackup } from '../utils/backup';`; in `handleFileChange` change `!file.name.endsWith('.json')` to `!file.name.toLowerCase().endsWith('.json')`, and replace the parse block with:

```js
    let backup;
    try {
      backup = JSON.parse(await file.text());
    } catch {
      showRestoreResult(false, 'Invalid JSON file');
      return;
    }
    if (!looksLikeBackup(backup)) {
      showRestoreResult(false, "This file doesn't look like a Net Worth Tracker backup");
      return;
    }
    setPendingRestore({ file, backup });
```

- [ ] **Step 6: `RestoreDialog.jsx`**
- Imports: `import { useEffect, useRef, useState } from 'react';` and `import { BACKUP_SECTIONS, countOf } from '../utils/backup';`; delete the local `SECTIONS` and `countOf`; use `BACKUP_SECTIONS` in the table.
- Add `const downloadedRef = useRef(false);` and `const backupIsEmpty = BACKUP_SECTIONS.every(({ key }) => countOf(backup, key) === 0) && !backup?.goal;`.
- Replace `handleReplace` with:

```js
  const handleReplace = async () => {
    setError('');
    setRestoring(true);
    let restored;
    try {
      if (downloadFirst && !downloadedRef.current) {
        downloadJson(current, `networth_pre-restore_${filenameTimestamp()}.json`);
        downloadedRef.current = true;
      }
      restored = (await exportAPI.restore(file)).data.restored;
    } catch (err) {
      setError(errorMessage(err, 'Restore failed'));
      setRestoring(false);
      return;
    }
    onRestored(restored);
  };
```

- Directly above the amber warning add:

```jsx
          {backupIsEmpty && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm font-medium">
              This backup is empty — restoring it deletes everything in your account.
            </div>
          )}
```

- [ ] **Step 7: Build** (helper) — green.

- [ ] **Step 8: Commit** — `fix: readable validation errors; shared market and backup helpers; restore dialog polish`.

---

### Task 10: Assets page — yearly change rate

**Files:**
- Create: `frontend/src/utils/dates.js`
- Modify: `frontend/src/pages/Assets.jsx`

**Interfaces:**
- Produces: `todayIso()`, `formatDate(iso)`, `formatMonthYear(iso)` (Tasks 11–13 use them).

- [ ] **Step 1: `dates.js`** (new):

```js
// Dates travel as "YYYY-MM-DD". Parse them as local dates: new Date("YYYY-MM-DD") is UTC and can show the previous day.
const parseIso = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};

export const todayIso = () => new Date().toLocaleDateString('en-CA'); // en-CA formats as YYYY-MM-DD

export const formatDate = (iso) =>
  iso ? new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(parseIso(iso)) : '';

export const formatMonthYear = (iso) =>
  iso ? new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' }).format(parseIso(iso)) : '';
```

- [ ] **Step 2: `Assets.jsx`**
1. Import `import { todayIso, formatDate } from '../utils/dates';`.
2. After `getCategoryInfo` add:

```js
// Suggested yearly change when a category is picked; the user can change or clear it.
const SUGGESTED_YEARLY_CHANGE = { vehicles: '-15', real_estate: '5' };

const emptyForm = () => ({
  name: '', value: '', category: 'cash', description: '', annual_change_rate: '', valuation_date: todayIso(),
});
```

3. State: `useState(emptyForm)` for `formData`; add `const [rateTouched, setRateTouched] = useState(false);`.
4. `openModal`: edit branch sets `annual_change_rate: asset.annual_change_rate?.toString() ?? ''`, `valuation_date: asset.valuation_date || todayIso()` and `setRateTouched(true)`; new branch `setFormData(emptyForm())` and `setRateTouched(false)`. `closeModal`: `setFormData(emptyForm())`.
5. `handleSubmit` data adds `annual_change_rate: formData.annual_change_rate === '' ? null : parseFloat(formData.annual_change_rate)` and `valuation_date: formData.valuation_date || null`.
6. `totalAssets` sums `asset.current_value`.
7. In the list, the amount shows `formatCurrency(asset.current_value)`, and under the category line add:

```jsx
                    {asset.annual_change_rate != null && asset.valuation_date && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                        {formatCurrency(asset.value)} on {formatDate(asset.valuation_date)} · {asset.annual_change_rate > 0 ? '+' : ''}{asset.annual_change_rate}%/yr
                      </p>
                    )}
```

8. Form: the value input's `onChange` becomes `setFormData({ ...formData, value: e.target.value, valuation_date: todayIso() })`; after it add

```jsx
              <div>
                <label className="label">Value as of</label>
                <input
                  type="date"
                  className="input"
                  value={formData.valuation_date}
                  onChange={(e) => setFormData({ ...formData, valuation_date: e.target.value })}
                />
              </div>
```

   the category select's `onChange` becomes

```jsx
                  onChange={(e) => {
                    const category = e.target.value;
                    setFormData((f) => ({
                      ...f,
                      category,
                      ...(rateTouched ? {} : { annual_change_rate: SUGGESTED_YEARLY_CHANGE[category] ?? '' }),
                    }));
                  }}
```

   and after the category field add

```jsx
              <div>
                <label className="label">Yearly change % (Optional)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="e.g., -15 for a car, 5 for property"
                  min="-99"
                  max="100"
                  step="0.1"
                  value={formData.annual_change_rate}
                  onChange={(e) => {
                    setRateTouched(true);
                    setFormData({ ...formData, annual_change_rate: e.target.value });
                  }}
                />
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  The value is adjusted every day at this yearly rate, starting from the date above.
                </p>
              </div>
```

- [ ] **Step 3: Build** — green. **Step 4: Commit** — `feat: yearly change rate on assets`.

---

### Task 11: Liabilities page — EMI, payoff, schedule

**Files:**
- Create: `frontend/src/utils/loans.js`, `frontend/src/components/LoanScheduleModal.jsx`
- Modify: `frontend/src/api.js`, `frontend/src/pages/Liabilities.jsx`

- [ ] **Step 1: `loans.js`** (new) — same formula as `valuation.emi_for_tenure`:

```js
// Monthly EMI that clears `principal` in `months` at `annualRate` % (reducing balance).
export const emiForTenure = (principal, annualRate, months) => {
  const r = annualRate / 1200;
  if (r === 0) return Math.round((principal / months) * 100) / 100;
  const growth = (1 + r) ** months;
  return Math.round(((principal * r * growth) / (growth - 1)) * 100) / 100;
};
```

- [ ] **Step 2: `api.js`** — add to `liabilitiesAPI`: `schedule: (id) => api.get(\`/api/liabilities/${id}/schedule\`),`.

- [ ] **Step 3: `LoanScheduleModal.jsx`** (new):

```jsx
import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { liabilitiesAPI } from '../api';
import { errorMessage } from '../utils/errors';
import { formatMonthYear } from '../utils/dates';

export default function LoanScheduleModal({ liability, formatCurrency, onClose }) {
  const [schedule, setSchedule] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    liabilitiesAPI.schedule(liability.id)
      .then((response) => { if (!cancelled) setSchedule(response.data); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, 'Failed to load the schedule')); });
    return () => { cancelled = true; };
  }, [liability.id]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{liability.name} — repayment schedule</h2>
            {schedule?.payoff_date && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Paid off by {formatMonthYear(schedule.payoff_date)} · {formatCurrency(schedule.interest_remaining)} interest left
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6">
          {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}
          {!error && !schedule && <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>}
          {schedule && schedule.rows.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {schedule.payoff_date ? 'This loan is paid off.' : 'The payoff is too far out to project.'}
            </p>
          )}
          {schedule && schedule.rows.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="font-medium pb-2">Year</th>
                  <th className="font-medium pb-2 text-right">Paid</th>
                  <th className="font-medium pb-2 text-right">Interest</th>
                  <th className="font-medium pb-2 text-right">Principal</th>
                  <th className="font-medium pb-2 text-right">Balance at year end</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-gray-100">
                {schedule.rows.map((row) => (
                  <tr key={row.year} className="border-t border-gray-100 dark:border-gray-700">
                    <td className="py-1.5">{row.year}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.paid)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.interest)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.principal)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.closing_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `Liabilities.jsx`**
1. Imports: add `CalendarDays` to the lucide import; `import LoanScheduleModal from '../components/LoanScheduleModal';`, `import { todayIso, formatMonthYear } from '../utils/dates';`, `import { emiForTenure } from '../utils/loans';`.
2. Add (module level):

```js
const emptyForm = () => ({
  name: '', amount: '', category: 'credit_card', interest_rate: '', description: '',
  emi: '', balance_date: todayIso(), tenure_months: '',
});
```

   and use it for the initial state, the new branch of `openModal` and `closeModal`. The edit branch also sets `emi: liability.emi?.toString() ?? ''`, `balance_date: liability.balance_date || todayIso()`, `tenure_months: liability.tenure_months?.toString() ?? ''`.
3. State: `const [scheduleFor, setScheduleFor] = useState(null);`.
4. `handleSubmit` data adds `emi: formData.emi === '' ? null : parseFloat(formData.emi)`, `balance_date: formData.balance_date || null`, `tenure_months: formData.tenure_months === '' ? null : parseInt(formData.tenure_months, 10)`.
5. Add a helper above `return`:

```js
  // Fill the EMI from a tenure, using the balance and rate already entered.
  const fillEmiFromTenure = (form) => {
    const principal = parseFloat(form.amount);
    const months = parseInt(form.tenure_months, 10);
    if (!(principal > 0) || !(months > 0)) return form;
    return { ...form, emi: emiForTenure(principal, parseFloat(form.interest_rate) || 0, months).toString() };
  };
```

6. `totalLiabilities` sums `liability.outstanding`.
7. List: the amount shows `formatCurrency(liability.outstanding)`; under the description add

```jsx
                    {liability.amortized && (
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        EMI {formatCurrency(liability.emi)}
                        {liability.emi_too_low ? (
                          <span className="ml-2 inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300">
                            EMI doesn't cover the interest
                          </span>
                        ) : liability.payoff_date && (
                          <> · paid off by {formatMonthYear(liability.payoff_date)} · {formatCurrency(liability.interest_remaining)} interest left</>
                        )}
                      </p>
                    )}
```

   and, before the edit button, for amortized liabilities that aren't `emi_too_low`:

```jsx
                    {liability.amortized && !liability.emi_too_low && (
                      <button
                        onClick={() => setScheduleFor(liability)}
                        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-700"
                        title="Repayment schedule"
                      >
                        <CalendarDays className="w-4 h-4" />
                      </button>
                    )}
```

8. Form: relabel "Amount Owed (₹)" to "Balance (₹)" and make its `onChange` `setFormData({ ...formData, amount: e.target.value, balance_date: todayIso() })`. After it add a "Balance as of" date input bound to `balance_date` (same markup as the Assets "Value as of" field). After the interest-rate field add:

```jsx
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">EMI ₹/month (Optional)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="e.g., 52000"
                    min="0"
                    step="0.01"
                    value={formData.emi}
                    onChange={(e) => setFormData({ ...formData, emi: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">…or tenure (months)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="e.g., 240"
                    min="1"
                    max="600"
                    step="1"
                    value={formData.tenure_months}
                    onChange={(e) => setFormData(fillEmiFromTenure({ ...formData, tenure_months: e.target.value }))}
                  />
                </div>
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500 -mt-2">
                With an EMI, the balance goes down every month from the date above. Enter a tenure to work out the EMI.
              </p>
```

9. After the edit modal, render `{scheduleFor && <LoanScheduleModal liability={scheduleFor} formatCurrency={formatCurrency} onClose={() => setScheduleFor(null)} />}`.

- [ ] **Step 5: Build** — green. **Step 6: Commit** — `feat: EMI loans with payoff date and yearly schedule`.

---

### Task 12: Bank Accounts page — FD/RD interest and maturity

**Files:** Modify `frontend/src/pages/BankAccounts.jsx`

- [ ] **Step 1: Edits**
1. Import `import { formatDate } from '../utils/dates';`.
2. Module level:

```js
const DEPOSIT_TYPES = ['fd', 'rd'];

const emptyForm = () => ({
  bank_name: '', account_number: '', account_type: 'savings', balance: '', branch: '', ifsc_code: '',
  interest_rate: '', start_date: '', maturity_date: '', monthly_deposit: '',
});

const balanceLabel = (type) => (type === 'fd' ? 'Principal (₹)' : type === 'rd' ? 'Deposited so far (₹)' : 'Balance (₹)');
```

   Use `emptyForm` for the initial state, the new branch of `openModal` and `closeModal`; the edit branch also sets `interest_rate: account.interest_rate?.toString() ?? ''`, `start_date: account.start_date || ''`, `maturity_date: account.maturity_date || ''`, `monthly_deposit: account.monthly_deposit?.toString() ?? ''`.
3. `handleSubmit` data adds (all `null` for non-deposit types, which clears them when the type changes):

```js
      const isDeposit = DEPOSIT_TYPES.includes(formData.account_type);
      const optionalNumber = (v) => (v === '' ? null : parseFloat(v));
      // …inside data:
        interest_rate: isDeposit ? optionalNumber(formData.interest_rate) : null,
        start_date: isDeposit ? formData.start_date || null : null,
        maturity_date: isDeposit ? formData.maturity_date || null : null,
        monthly_deposit: formData.account_type === 'rd' ? optionalNumber(formData.monthly_deposit) : null,
```

4. `totalBalance` sums `account.current_value`.
5. List: the amount shows `formatCurrency(account.current_value)`; under the branch line add

```jsx
                    {account.maturity_date && (
                      account.matured ? (
                        <p className="text-xs font-medium text-red-600 dark:text-red-400 mt-1">
                          Matured on {formatDate(account.maturity_date)} — update or renew it
                        </p>
                      ) : (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          Matures in {account.days_to_maturity} day{account.days_to_maturity === 1 ? '' : 's'} ({formatDate(account.maturity_date)})
                          {account.maturity_value != null && <> · {formatCurrency(account.maturity_value)}</>}
                        </p>
                      )
                    )}
```

6. Form: the balance label becomes `{balanceLabel(formData.account_type)}`. After the balance field, when `DEPOSIT_TYPES.includes(formData.account_type)`, render:

```jsx
              {DEPOSIT_TYPES.includes(formData.account_type) && (
                <>
                  {formData.account_type === 'rd' && (
                    <div>
                      <label className="label">Monthly deposit (₹)</label>
                      <input type="number" className="input" placeholder="e.g., 5000" min="0" step="0.01"
                        value={formData.monthly_deposit}
                        onChange={(e) => setFormData({ ...formData, monthly_deposit: e.target.value })} />
                    </div>
                  )}
                  <div>
                    <label className="label">Interest rate (% p.a.)</label>
                    <input type="number" className="input" placeholder="e.g., 7.1" min="0" max="100" step="0.01"
                      value={formData.interest_rate}
                      onChange={(e) => setFormData({ ...formData, interest_rate: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Start date</label>
                      <input type="date" className="input" value={formData.start_date}
                        onChange={(e) => setFormData({ ...formData, start_date: e.target.value })} />
                    </div>
                    <div>
                      <label className="label">Maturity date</label>
                      <input type="date" className="input" value={formData.maturity_date} min={formData.start_date || undefined}
                        onChange={(e) => setFormData({ ...formData, maturity_date: e.target.value })} />
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 -mt-2">
                    Interest compounds quarterly, as banks quote FD and RD rates.
                  </p>
                </>
              )}
```

- [ ] **Step 2: Build** — green. **Step 3: Commit** — `feat: FD and RD interest, maturity value and countdown`.

---

### Task 13: Dashboard maturity card; report uses computed values

**Files:** Modify `frontend/src/pages/Dashboard.jsx`, `frontend/src/utils/reportGenerator.js`

- [ ] **Step 1: Dashboard**
1. Add `CalendarClock` to the lucide import and `import { formatDate } from '../utils/dates';`.
2. Directly above `{/* Charts Row */}` add:

```jsx
      {/* Deposits maturing */}
      {metrics?.maturities?.length > 0 && (
        <div className="card border-l-4 border-l-amber-500">
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock className="w-5 h-5 text-amber-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Deposits maturing</h2>
          </div>
          <ul className="space-y-2">
            {metrics.maturities.map((m) => {
              const label = `${m.bank_name} ${m.account_type.toUpperCase()}`;
              return (
                <li key={m.id} className="text-sm">
                  {m.days_to_maturity <= 0 ? (
                    <span className="text-red-600 dark:text-red-400 font-medium">
                      {label} matured on {formatDate(m.maturity_date)} — update or renew it
                    </span>
                  ) : (
                    <span className="text-gray-700 dark:text-gray-300">
                      {label} matures in {m.days_to_maturity} day{m.days_to_maturity === 1 ? '' : 's'}
                      {m.maturity_value != null && <> ({formatCurrency(m.maturity_value)})</>}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
```

- [ ] **Step 2: Report**
- `buildAssetsSection`: the value cell uses `a.current_value` and the total uses `sumField(assets, 'current_value')`.
- `buildLiabilitiesSection`: the amount cell and total use `outstanding`; add an "EMI" column after "Interest Rate" with `${l.emi != null ? fmt(l.emi, isPrivate) : '—'}` (header `<th class="num">EMI</th>`; the no-data colspan becomes 5; the total row gets one more empty `<td></td>`).
- `buildBankAccountsSection`: the balance cell and total use `current_value`; header text "Value".
- `buildEquitiesSection`: Avg Buy Price and Current Price cells show `isUsdMarket(e.market) ? fmtUsd(e.avg_buy_price, false) : fmtNum(e.avg_buy_price)` (and the same for `current_price`, keeping the `—` when null).

- [ ] **Step 3: Build** — green. **Step 4: Commit** — `feat: deposits-maturing card on the dashboard; report shows today's values`.

---

### Task 14: End-to-end check in the browser (controller)

Run a throwaway backend and Vite in WSL with a temp `DATA_FILE`, a SECRET_KEY generated at launch (`openssl rand -hex 32`), and a freshly registered user whose password is generated at launch (never typed into a file). Check:
- Assets: add a vehicle — the rate pre-fills −15; the list shows value, "₹X on <date> · −15%/yr"; editing the rate to empty makes the value constant.
- Liabilities: add a loan with tenure 240 — EMI fills in; the list shows EMI, payoff month and interest left; the schedule modal shows yearly rows; an EMI below the interest shows the red badge and no schedule button; clearing the EMI returns it to a manual balance.
- Bank Accounts: an FD with rate and dates shows interest earned and "Matures in N days · ₹…"; an RD with a monthly deposit; a matured FD shows the red line; the form hides deposit fields for savings.
- Dashboard: totals match the pages; the maturity card lists the FD maturing within 30 days.
- Privacy mode masks every new amount (list lines, schedule modal, maturity card).
- A 422 (e.g. an account number of 3 characters) shows "account_number: String should have at least 4 characters" instead of crashing the page.
- Restore: an empty-but-valid backup shows the red "empty" warning; a JSON array is rejected in the sidebar.
- Print report: assets, liabilities (with EMI column) and bank values match the pages.
Then the full backend suite once more and stop the servers.
