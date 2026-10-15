# Indian Asset Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** EPF, PPF, NPS, Gold, SGB, Bonds and ESOP/RSU asset categories; EPF/PPF grow from contributions and the published rate; gold/SGB/ESOP-RSU are quantity × price.

**Architecture:** New `AssetCategory` values and four optional asset fields. `valuation.asset_current_value` dispatches provident funds to a monthly-accrual / March-credit model; quantity × price is stored as `value` at write time. One frontend module (`assetCategories.js`) owns labels, icons and each category's kind; the Assets form shows the fields for the selected kind; the dashboard and report use the same labels.

**Tech Stack:** FastAPI 0.115, Pydantic 2.10, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-indian-asset-types-design.md`. Read it before starting any task.

## Global Constraints

- **Branch / worktree:** `feat/indian-assets` from local `main` at `02dbffd`. Local commits only — never push.
- **Environment:** Python and Node exist only in WSL; use the controller's helper scripts for the backend suite and the frontend build.
- **Expected totals:** 302 before; 310 after Task 1; 325 after Task 2; 326 after Task 3. Frontend tasks don't change the backend count.
- **Tests never touch the network** (`offline_markets`); dates are frozen with `frozen_today` (default 2026-10-14; assign `frozen_today["date"]` to move it).
- **No hardcoded credentials, secrets or personal data** in code, tests or docs; fake test data only.
- **No new dependencies.** Backend style: module-level functions, `db.` helpers, `HTTPException`. Frontend: Tailwind component classes with `dark:` variants; dates as local `YYYY-MM-DD`.
- **Commits:** use the commit command in your dispatch's working rules.

## Review Focus

1. Switching an asset's category between kinds (e.g. PPF → Cash, Gold → NPS): expect the fields that no longer apply to be cleared, and the value to stay what the user sees (Task 2 tests clearing; Task 5 sends nulls).
2. A provident fund anchored mid-month, on 31 March, or viewed before its anchor (Task 1 tests each).
3. Quantity × price above the maximum, or a price update on an existing holding (Task 2 tests both).
4. Existing assets in the old categories keep working unchanged (no migration; Task 2's API tests use the old categories too).
5. Privacy mode masks the new amounts (contribution, price, computed value) — controller checks in Task 6.

---

### Task 1: Provident-fund valuation

**Files:** Modify `backend/valuation.py`; Test `backend/tests/test_valuation.py` (append 8 tests)

**Interfaces:** Produces `PROVIDENT_FUNDS = ("epf", "ppf")` and the provident-fund branch inside `asset_current_value(asset, on)` (signature unchanged). Task 2's API tests rely on it through the dashboard and list endpoints.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_valuation.py`:

```python
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
```

- [ ] **Step 2: Run; the provident-fund tests FAIL** (no provident branch yet: values equal the stored value).

- [ ] **Step 3: Implement** — in `backend/valuation.py`: add `timedelta` to the `datetime` import; in the "Assets" section, before `asset_current_value`, add:

```python
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
```

and make `asset_current_value` start with:

```python
    if asset.get("category") in PROVIDENT_FUNDS and asset.get("interest_rate") is not None:
        return _provident_fund_value(asset, on)
```

- [ ] **Step 4:** `tests/test_valuation.py` and the full suite — `310 passed`.
- [ ] **Step 5: Commit** — `feat: EPF and PPF grow with monthly interest credited each March`.

---

### Task 2: Categories, fields and write-time rules

**Files:** Modify `backend/models.py`, `backend/database.py`, `backend/main.py`; Test `backend/tests/test_indian_assets_api.py` (create; 15 tests)

**Interfaces:** Produces `AssetCategory` values `epf`, `ppf`, `nps`, `gold`, `sgb`, `bonds`, `esop_rsu`; asset fields `monthly_contribution`, `interest_rate`, `quantity`, `unit_price` (on `AssetBase` and `AssetUpdate`, therefore on the `Asset` response); 422 detail "Quantity × price is above the allowed maximum". Tasks 4–5 rely on these names.

- [ ] **Step 1: Failing tests** — `backend/tests/test_indian_assets_api.py`:

```python
import json
from datetime import date

import pytest

pytestmark = pytest.mark.usefixtures("offline_markets")


def post(client, headers, body):
    resp = client.post("/api/assets", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


GOLD = {"name": "Test gold", "category": "gold", "value": 0, "quantity": 50, "unit_price": 10_000}
PPF = {"name": "Test PPF", "category": "ppf", "value": 0, "monthly_contribution": 10_000, "interest_rate": 7.1,
       "valuation_date": "2025-03-31"}


@pytest.mark.parametrize("category", ["epf", "ppf", "nps", "gold", "sgb", "bonds", "esop_rsu"])
def test_new_categories_are_accepted(client, auth_headers, frozen_today, category):
    asset = post(client, auth_headers, {"name": "Test asset", "category": category, "value": 1_000})
    assert asset["category"] == category and asset["current_value"] == 1_000


def test_quantity_times_price_becomes_the_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    assert asset["value"] == 500_000 and asset["current_value"] == 500_000


def test_a_sent_value_is_overridden_by_quantity_times_price(client, auth_headers, frozen_today):
    assert post(client, auth_headers, {**GOLD, "value": 1})["value"] == 500_000


def test_updating_the_price_recomputes_the_value(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"unit_price": 11_000})
    assert resp.status_code == 200 and resp.json()["value"] == 550_000


def test_quantity_times_price_above_the_maximum_is_rejected(client, auth_headers, frozen_today):
    resp = client.post("/api/assets", headers=auth_headers, json={**GOLD, "quantity": 1e12, "unit_price": 1e15})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Quantity × price is above the allowed maximum"
    assert client.get("/api/assets", headers=auth_headers).json() == []


def test_an_update_above_the_maximum_is_rejected_and_nothing_changes(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, GOLD)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers, json={"quantity": 1e12, "unit_price": 1e15})
    assert resp.status_code == 422
    assert client.get(f"/api/assets/{asset['id']}", headers=auth_headers).json()["value"] == 500_000


def test_new_fields_can_be_cleared(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, PPF)
    resp = client.put(f"/api/assets/{asset['id']}", headers=auth_headers,
                      json={"monthly_contribution": None, "interest_rate": None, "category": "cash"})
    body = resp.json()
    assert (body["monthly_contribution"], body["interest_rate"], body["category"]) == (None, None, "cash")


def test_a_provident_fund_gets_todays_date(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, {**PPF, "valuation_date": None})
    assert asset["valuation_date"] == "2026-10-14"


def test_list_and_dashboard_use_the_provident_fund_value(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 3, 31)
    post(client, auth_headers, PPF)
    [listed] = client.get("/api/assets", headers=auth_headers).json()
    assert listed["current_value"] == pytest.approx(124_615.00, abs=0.01)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert metrics["assets_by_category"]["ppf"] == pytest.approx(124_615.00, abs=0.01)


def test_old_categories_still_work(client, auth_headers, frozen_today):
    asset = post(client, auth_headers, {"name": "Test fund", "category": "retirement", "value": 7_000})
    assert asset["current_value"] == 7_000


def test_export_and_restore_keep_the_new_fields(client, auth_headers, frozen_today):
    post(client, auth_headers, GOLD)
    post(client, auth_headers, PPF)
    backup = client.get("/api/export", headers=auth_headers).json()
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    by_name = {a["name"]: a for a in client.get("/api/assets", headers=auth_headers).json()}
    assert (by_name["Test gold"]["quantity"], by_name["Test gold"]["unit_price"]) == (50, 10_000)
    assert (by_name["Test PPF"]["monthly_contribution"], by_name["Test PPF"]["interest_rate"]) == (10_000, 7.1)
```

(7 + 8 = 15 tests.)

- [ ] **Step 2: Run; FAIL** (unknown categories 422, fields ignored).

- [ ] **Step 3: Models** — in `AssetCategory` add, before `OTHER`:

```python
    EPF = "epf"
    PPF = "ppf"
    NPS = "nps"
    GOLD = "gold"
    SGB = "sgb"          # Sovereign Gold Bonds
    BONDS = "bonds"
    ESOP_RSU = "esop_rsu"
```

`AssetBase` and `AssetUpdate` both gain:

```python
    monthly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # EPF/PPF
    interest_rate: Optional[float] = Field(None, ge=0, le=100)  # EPF/PPF, % per year
    quantity: Optional[float] = Field(None, gt=0, le=MAX_UNITS)  # grams or units
    unit_price: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # price per gram or unit
```

- [ ] **Step 4: Clearing** — `database.ASSET_CLEARABLE` gains `"monthly_contribution", "interest_rate", "quantity", "unit_price"`.

- [ ] **Step 5: Write-time rules in `main.py`** — import `MAX_AMOUNT` if not already imported. Replace `_asset_defaults` and add a value helper:

```python
def _asset_defaults(row: dict) -> dict:
    """An asset that changes by itself (yearly rate, provident-fund interest or contributions) carries the date
    its value was true."""
    changes_by_itself = any(row.get(key) is not None
                            for key in ("annual_change_rate", "interest_rate", "monthly_contribution"))
    if changes_by_itself and not row.get("valuation_date"):
        return {"valuation_date": _today_iso()}
    return {}


def _value_from_quantity(row: dict) -> dict:
    """Quantity × price holdings store their product as the value."""
    quantity, unit_price = row.get("quantity"), row.get("unit_price")
    if quantity is None or unit_price is None:
        return {}
    value = round(quantity * unit_price, 2)
    if not value <= MAX_AMOUNT:
        raise HTTPException(status_code=422, detail="Quantity × price is above the allowed maximum")
    return {"value": value}
```

Create: after `data = asset_data.model_dump()`, add `data.update(_value_from_quantity(data))` before `data.update(_asset_defaults(data))`.

Update: fetch the current row first (404 if missing), then compute on the row storage will hold:

```python
    current = db.get_asset_by_id(asset_id, user_id)
    if not current:
        raise HTTPException(status_code=404, detail="Asset not found")
    changes = update_data.model_dump(exclude_unset=True)
    changes.update(_value_from_quantity(_merged(current, changes, db.ASSET_CLEARABLE)))
    asset = db.update_asset(asset_id, user_id, changes)
    extra = _asset_defaults(asset)
    if extra:
        asset = db.update_asset(asset_id, user_id, extra)
    return valuation.asset_view(asset, valuation.today())
```

- [ ] **Step 6:** test file, then full suite — `325 passed`.
- [ ] **Step 7: Commit** — `feat: Indian asset categories; quantity × price and provident-fund fields`.

---

### Task 3: Demo data and README

**Files:** Modify `backend/main.py` (`startup_event` sample assets), `README.md`; Test `backend/tests/test_valuation_api.py` (append 1)

- [ ] **Step 1: Failing test** — append:

```python
def test_demo_assets_use_the_indian_categories(client, monkeypatch, frozen_today):
    import asyncio

    import database as db
    import main
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())

    demo_id = db.get_user_by_username("demo")["id"]
    by_name = {a["name"]: a for a in db.get_assets_by_user(demo_id)}
    assert (by_name["EPF Balance"]["category"], by_name["EPF Balance"]["interest_rate"]) == ("epf", 8.25)
    assert (by_name["PPF Account"]["category"], by_name["PPF Account"]["interest_rate"]) == ("ppf", 7.1)
    assert by_name["NPS Account"]["category"] == "nps"
    gold = by_name["Gold Jewelry"]
    assert (gold["category"], gold["quantity"], gold["unit_price"], gold["value"]) == ("gold", 50, 10_000, 500_000)
```

- [ ] **Step 2: Implement** — in the demo `sample_assets` list: "PPF Account" → `"category": "ppf", "interest_rate": 7.1, "monthly_contribution": 12500, "valuation_date": iso(valuation.add_months(on, -6))`; "EPF Balance" → `"category": "epf", "interest_rate": 8.25, "monthly_contribution": 3600, "valuation_date": iso(valuation.add_months(on, -6))`; "NPS Account" → `"category": "nps"`; "Gold Jewelry" → `"category": "gold", "quantity": 50, "unit_price": 10000` (value stays 500000). Keep everything else.

README: under Asset & Liability Management list the new categories; explain that EPF and PPF grow from a balance on a date plus a monthly contribution at the entered rate (interest monthly on the running balance, credited every 31 March — re-anchor on each annual statement for exact figures), and that gold, SGB and ESOP/RSU can be entered as quantity × price per gram/unit.

- [ ] **Step 3:** full suite — `326 passed`. **Step 4: Commit** — `feat: demo data and docs for Indian asset types`.

---

### Task 4: Shared category labels (dashboard and report)

**Files:** Create `frontend/src/utils/assetCategories.js`; Modify `frontend/src/pages/Dashboard.jsx`, `frontend/src/utils/reportGenerator.js`

**Interfaces:** Produces `ASSET_CATEGORIES`, `assetCategoryInfo(value)`, `categoryLabel(name)`. Task 5 uses the first two.

- [ ] **Step 1: Create `assetCategories.js`:**

```js
import {
  Banknote, PiggyBank, Building, Car, Wallet, Bitcoin, HelpCircle,
  Briefcase, Umbrella, Gem, Coins, ScrollText, BadgePercent,
} from 'lucide-react';

// Every asset category. `kind` picks the extra form fields: 'provident' (balance + contribution + rate)
// or 'quantity' (quantity × price); others are a plain value. `unit` labels quantity holdings.
export const ASSET_CATEGORIES = [
  { value: 'cash', label: 'Cash & Savings', icon: Banknote, color: 'bg-green-100 text-green-600' },
  { value: 'investments', label: 'Investments', icon: PiggyBank, color: 'bg-blue-100 text-blue-600' },
  { value: 'real_estate', label: 'Real Estate', icon: Building, color: 'bg-purple-100 text-purple-600' },
  { value: 'vehicles', label: 'Vehicles', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'epf', label: 'EPF', icon: Briefcase, color: 'bg-indigo-100 text-indigo-600', kind: 'provident' },
  { value: 'ppf', label: 'PPF', icon: PiggyBank, color: 'bg-teal-100 text-teal-600', kind: 'provident' },
  { value: 'nps', label: 'NPS', icon: Umbrella, color: 'bg-sky-100 text-sky-600' },
  { value: 'retirement', label: 'Retirement (other)', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  { value: 'gold', label: 'Gold', icon: Gem, color: 'bg-amber-100 text-amber-600', kind: 'quantity', unit: 'g' },
  { value: 'sgb', label: 'Sovereign Gold Bonds', icon: Coins, color: 'bg-amber-100 text-amber-700', kind: 'quantity', unit: 'g' },
  { value: 'bonds', label: 'Bonds', icon: ScrollText, color: 'bg-slate-100 text-slate-600' },
  { value: 'esop_rsu', label: 'ESOP / RSU', icon: BadgePercent, color: 'bg-pink-100 text-pink-600', kind: 'quantity', unit: 'units' },
  { value: 'crypto', label: 'Cryptocurrency', icon: Bitcoin, color: 'bg-yellow-100 text-yellow-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

export const assetCategoryInfo = (value) =>
  ASSET_CATEGORIES.find((c) => c.value === value) || ASSET_CATEGORIES[ASSET_CATEGORIES.length - 1];

const BUCKET_LABELS = { equities: 'Equities', bank_accounts: 'Bank Accounts', mutual_funds: 'Mutual Funds' };
const titleCase = (name) => name.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

// Label for a dashboard key: an asset category, a holdings bucket, or (title-cased) a liability category.
export const categoryLabel = (name) =>
  ASSET_CATEGORIES.find((c) => c.value === name)?.label ?? BUCKET_LABELS[name] ?? titleCase(name);
```

- [ ] **Step 2: Dashboard** — import `categoryLabel`; delete `formatCategoryName` and use `categoryLabel(name)` for both chart datasets.
- [ ] **Step 3: Report** — import `categoryLabel` from `./assetCategories`; in `buildAssetsSection` the category cell becomes `${escapeHtml(categoryLabel(a.category))}`.
- [ ] **Step 4: Build** — green. **Step 5: Commit** — `feat: one place for asset category labels and icons`.

---

### Task 5: Assets page for the new kinds

**Files:** Modify `frontend/src/pages/Assets.jsx`

- [ ] **Step 1: Category data** — delete the local `CATEGORIES`, `getCategoryInfo` and the lucide icon imports that become unused; import `ASSET_CATEGORIES` and `assetCategoryInfo` from `../utils/assetCategories`. Use `assetCategoryInfo` wherever `getCategoryInfo` was used and `ASSET_CATEGORIES` for the select options.
- [ ] **Step 2: Form state** — `emptyForm` gains `monthly_contribution: ''`, `interest_rate: ''`, `quantity: ''`, `unit_price: ''`; `openModal`'s edit branch loads them with `?.toString() ?? ''`. Add `const SUGGESTED_INTEREST = { epf: '8.25', ppf: '7.1' };` and an `interestTouched` state handled exactly like `rateTouched` (false for a new asset, true when editing, set true on typing in the interest field). Add helpers inside the component:

```js
  const kind = assetCategoryInfo(formData.category).kind;
  const unit = assetCategoryInfo(formData.category).unit;
  const quantityValue = (() => {
    const q = parseFloat(formData.quantity);
    const p = parseFloat(formData.unit_price);
    return q > 0 && p >= 0 ? Math.round(q * p * 100) / 100 : null;
  })();
```

- [ ] **Step 3: Category change** — the select's `onChange` also applies `SUGGESTED_INTEREST[category] ?? ''` to `interest_rate` when `!interestTouched` (alongside the existing yearly-change suggestion).
- [ ] **Step 4: Submit** — build the payload per kind (fields that don't apply are sent as null so a category change clears them):

```js
      const num = (v) => (v === '' ? null : parseFloat(v));
      const data = {
        name: formData.name,
        category: formData.category,
        description: formData.description || null,
        value: kind === 'quantity' ? (quantityValue ?? 0) : parseFloat(formData.value),
        annual_change_rate: kind === 'provident' ? null : num(formData.annual_change_rate),
        valuation_date: formData.valuation_date || null,
        monthly_contribution: kind === 'provident' ? num(formData.monthly_contribution) : null,
        interest_rate: kind === 'provident' ? num(formData.interest_rate) : null,
        quantity: kind === 'quantity' ? num(formData.quantity) : null,
        unit_price: kind === 'quantity' ? num(formData.unit_price) : null,
      };
```

- [ ] **Step 5: Form layout** — order: Asset Name, Category, then by kind:
  - plain (no kind): Value (₹) [required], Value as of, Yearly change % — as today;
  - `provident`: "Balance (₹)" (the `value` field, required), "Balance as of" (`valuation_date`), "Monthly contribution (₹)" (`min="0" step="any"`), "Interest rate (% p.a.)" (`min="0" max="100" step="any"`, required) with the hint `Interest is added monthly on the running balance and credited every 31 March, as EPFO and PPF do.`; no yearly-change field;
  - `quantity`: "Quantity ({unit === 'g' ? 'grams' : 'units'})" (`min="0" step="any"`, required), "Price per {unit === 'g' ? 'gram' : 'unit'} (₹)" (`min="0" step="any"`, required), "Price as of" (`valuation_date`), a read-only line `Value: {formatCurrency(quantityValue ?? 0)}`, then Yearly change % (optional).
  Typing in value, quantity or price resets `valuation_date` to `todayIso()` (as the value field does today). Reuse the existing input/label markup and classes; re-read every className you write.
- [ ] **Step 6: List lines** — under the category label:
  - provident with `interest_rate != null && valuation_date`: `{formatCurrency(asset.value)} on {formatDate(asset.valuation_date)} · +{formatCurrency(asset.monthly_contribution || 0)}/month at {asset.interest_rate}%`;
  - quantity with `quantity != null && unit_price != null`: `{asset.quantity} {unit} × {formatCurrency(asset.unit_price)}/{unit === 'g' ? 'g' : 'unit'}`;
  - the existing yearly-change line unchanged (it only shows when `annual_change_rate` is set).
  Use the existing small-text classes (`text-xs text-gray-400 dark:text-gray-500 mt-1`).
- [ ] **Step 7: Build** — green. **Step 8: Commit** — `feat: EPF/PPF and quantity × price on the Assets page`.

---

### Task 6: Browser check (controller)

Throwaway backend + Vite (generated SECRET_KEY, temp DATA_FILE, freshly registered user with a generated password). Check: every new category in the select; EPF suggests 8.25 and PPF 7.1; a PPF with balance, contribution and rate shows the provident line and a current value above the balance once a month has passed (or with a past "Balance as of"); gold 50 g × ₹10,000 shows ₹5,00,000 live in the form and in the list; switching PPF → Cash clears the PF fields; dashboard pie labels read EPF/PPF/Gold…; the report shows the labels; privacy masks the new amounts. Then the full suite and stop the servers.
