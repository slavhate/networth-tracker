# NPS Contributions, Investment Options and Form Hint Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:**
- Give NPS assets employer-monthly and own-yearly contributions, plus scheme holdings valued from NAVs fetched online.
- Stop form hints from overlapping the inputs above them.
- Give mutual funds SIPs whose installments buy units at their day's NAV (spec Part B).
- Replace the logo and favicon (spec Part C).
- Let the user choose how often automatic snapshots are saved, and show it (spec Part D).
- Flash a dismissible warning whenever a price or NAV source fails (spec Part E).

**Architecture:**
- **Pure valuation:** `valuation.py` holds the contribution schedule, the value with and without NAVs, unit pricing from NAV histories, and NPS asset-class shares. It never touches the network.
- **NAV fetching:** a new `nps_service.py` fetches and caches the npsnav.in scheme list and NAV histories.
- **API:** `main.py` prices NPS assets on save (best effort) and on an explicit refresh. It also serves the scheme list for the form.
- **Frontend:** two new components (a scheme editor and the scheme lines on a card) plug into `Assets.jsx`.

**Tech Stack:** FastAPI + Pydantic v2, JSON-file store, httpx (already a dependency), pytest; React 18 + Vite + Tailwind.

**Spec:** `docs/superpowers/specs/2026-10-15-nps-contributions-and-schemes-design.md`

## Global Constraints

- **No screenshot data:** never use any value from a screenshot the user shared — no scheme names, units, NAVs or amounts. Tests use made-up codes `SM9000xx` and names like `TEST PENSION FUND SCHEME E - TIER I`.
- **No hardcoded credentials, secrets or personal data:** test users come from `backend/tests/credentials.py`.
- **No new dependencies.**
- **Toolchain:** Python and Node run only in WSL. Use `bash <workspace>/run-backend-tests.sh [tests/test_x.py -q]` and `bash <workspace>/build-frontend.sh` (the controller's dispatch gives the paths).
- **Line endings:** the working tree uses CRLF. Prefer the Edit tool, and re-read every Tailwind `className` you touch.
- **Commits:** use the repository's configured no-reply identity, and end each message with a `Co-Authored-By:` trailer. Never stage `frontend/package-lock.json`.
- **Bounds:** NPS amounts stay ≤ `MAX_AMOUNT` (1e15) and units ≤ `MAX_UNITS` (1e12). Stored data must always pass the restore model.
- **Network:** saving never fails because NAVs can't be fetched. Startup and restore make no network calls.
- **Credit:** the UI and README credit npsnav.in as the NAV source (CC BY-NC 4.0 data, personal use).

## Review Focus

1. **NAV service down while saving an NPS asset with schemes:** the save succeeds unpriced, and the value is the balance plus contributions — never 0 or an error. Task 5 test `test_create_while_navs_unavailable_saves_unpriced`.
2. **Allocations like 33.33 / 33.33 / 33.34:** accepted (tolerance 0.01). Task 2 test `test_allocations_may_be_rounded`.
3. **A scheme whose NAV history starts after the balance date:** the asset stays unpriced (all-or-nothing) and nothing crashes. Task 3 test `test_pricing_is_all_or_nothing`.
4. **Editing only the name of a priced NPS asset** (the form re-sends every field): units and NAVs are kept and nothing is fetched. Task 5 test `test_name_only_update_keeps_pricing_without_fetching`.
5. **Restoring an older backup** whose assets lack the new fields, and restoring one with priced NPS assets: both work, and the second keeps its units and NAVs. Task 5 tests `test_restore_round_trip_keeps_nps_pricing` and `test_restore_accepts_assets_without_nps_fields`.

## Decisions made while planning (add to the spec in Task 5's README step)

- **No automatic re-anchoring for NPS.** Unlike EPF/PPF, the NPS form does not move the balance to today when a contribution changes. With statement units, re-anchoring would need today's units per scheme. The hint tells the user to update the balance, its date and the units from their latest statement when contributions change.
- **Refresh trigger.** The Assets page refreshes stale NPS assets in the background after loading. The dashboard and snapshots use the stored NAVs, as mutual funds do.

---

### Task 1: Form hints no longer overlap the inputs above them

**Files:**
- Modify: `frontend/src/pages/Liabilities.jsx` (2 hints), `frontend/src/pages/Assets.jsx` (1 hint), `frontend/src/pages/BankAccounts.jsx` (1 hint)

The form uses `space-y-4`. These hints override that spacing with `!-mt-2`, a forced negative top margin of 0.5rem, which pulls the text up into the inputs above it.

- [ ] **Step 1:** In each of the four files, replace the class `!-mt-2` with `!mt-1` on the hint `<p>` elements. There are exactly 4 occurrences:

```bash
grep -rn -- "!-mt-2" frontend/src
```

Each changed line reads:

```jsx
<p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
```

- [ ] **Step 2:** Confirm `grep -rn -- "!-mt-2" frontend/src` prints nothing, and that each edited line is the only change in its file (`git diff --stat`: 4 lines in 3 files).
- [ ] **Step 3:** Build: `bash <workspace>/build-frontend.sh` → `✓ built`.
- [ ] **Step 4:** Commit: `fix: form hints sit below their inputs instead of overlapping them`.

---

### Task 2: NPS fields in the models, storage and restore

**Files:**
- Modify: `backend/models.py`, `backend/database.py:95-96` (`ASSET_CLEARABLE`), `backend/restore.py` (`LIST_SECTIONS`)
- Test: `backend/tests/test_nps_models.py` (create)

**Interfaces:**
- Produces:
  - `models.NpsSchemeInput`, `models.NpsSchemeStored`, `models.NpsSchemeView`, `models.NpsSchemeOption`, `models.AssetRestore`.
  - `AssetBase` / `AssetUpdate` fields `yearly_contribution`, `yearly_contribution_month`, `nps_schemes`.
  - `Asset` response fields `nps_schemes: Optional[List[NpsSchemeView]]` and `nps_priced_through: Optional[str]`.
  - `ASSET_CLEARABLE` gains `yearly_contribution`, `yearly_contribution_month`, `nps_schemes`, `nps_priced_through`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_nps_models.py`:

```python
"""NPS asset fields: contributions and investment options (schemes)."""
import pytest
from pydantic import ValidationError

from models import AssetCreate, AssetRestore, AssetUpdate


def scheme(code="SM900001", pct=100, units=None, name=None):
    row = {"scheme_code": code, "scheme_name": name or f"TEST PENSION FUND SCHEME E - TIER I {code}",
           "allocation_pct": pct}
    if units is not None:
        row["units"] = units
    return row


def nps(**extra):
    return {"name": "NPS", "category": "nps", "value": 100000, "valuation_date": "2026-03-31", **extra}


def messages(exc):
    return " | ".join(e["msg"] for e in exc.value.errors())


def test_contribution_fields_are_accepted():
    asset = AssetCreate(**nps(monthly_contribution=6000, yearly_contribution=50000, yearly_contribution_month=3))
    assert (asset.yearly_contribution, asset.yearly_contribution_month) == (50000, 3)


@pytest.mark.parametrize("month", [0, 13])
def test_contribution_month_is_a_calendar_month(month):
    with pytest.raises(ValidationError):
        AssetCreate(**nps(yearly_contribution=50000, yearly_contribution_month=month))


def test_schemes_are_accepted():
    asset = AssetCreate(**nps(nps_schemes=[scheme("SM900001", 75), scheme("SM900002", 25)]))
    assert [s.scheme_code for s in asset.nps_schemes] == ["SM900001", "SM900002"]


def test_allocations_may_be_rounded():
    rows = [scheme("SM900001", 33.33), scheme("SM900002", 33.33), scheme("SM900003", 33.34)]
    assert len(AssetCreate(**nps(nps_schemes=rows)).nps_schemes) == 3


def test_allocations_must_add_up_to_100():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 60), scheme("SM900002", 30)]))
    assert "Allocations must add up to 100%" in messages(exc)


def test_a_scheme_can_be_added_once():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 50), scheme("SM900001", 50)]))
    assert "Each scheme can be added once" in messages(exc)


def test_units_for_every_scheme_or_none():
    with pytest.raises(ValidationError) as exc:
        AssetCreate(**nps(nps_schemes=[scheme("SM900001", 50, units=10), scheme("SM900002", 50)]))
    assert "Enter units for every scheme or for none" in messages(exc)


@pytest.mark.parametrize("code", ["SM90001", "XX900001", "sm900001", "SM9000011"])
def test_scheme_code_format(code):
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=[scheme(code)]))


def test_at_most_ten_schemes():
    rows = [scheme(f"SM90{i:04d}", 100 / 11) for i in range(11)]
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=rows))


def test_an_empty_scheme_list_is_rejected():
    with pytest.raises(ValidationError):
        AssetCreate(**nps(nps_schemes=[]))


def test_input_cannot_set_priced_fields():
    row = {**scheme(), "nav": 12.5, "base_units": 5, "contribution_units": 1, "nav_date": "2026-03-31"}
    stored = AssetCreate(**nps(nps_schemes=[row], nps_priced_through="2026-03-31")).model_dump()
    assert set(stored["nps_schemes"][0]) == {"scheme_code", "scheme_name", "allocation_pct", "units"}
    assert "nps_priced_through" not in stored


def test_update_accepts_and_clears_nps_fields():
    update = AssetUpdate(nps_schemes=None, yearly_contribution=None, yearly_contribution_month=None)
    assert update.model_dump(exclude_unset=True) == {
        "nps_schemes": None, "yearly_contribution": None, "yearly_contribution_month": None}
    with pytest.raises(ValidationError):
        AssetUpdate(nps_schemes=[scheme("SM900001", 40)])


def test_restore_keeps_priced_fields():
    row = {**scheme(), "nav": 12.5, "nav_date": "2026-03-31", "base_units": 5.0, "contribution_units": 1.0}
    restored = AssetRestore(**nps(nps_schemes=[row], nps_priced_through="2026-04-01")).model_dump()
    assert restored["nps_schemes"][0]["nav"] == 12.5
    assert restored["nps_priced_through"] == "2026-04-01"


@pytest.mark.parametrize("bad", [{"nav": -1}, {"nav": 0}, {"base_units": 2e12}, {"nav_date": "2026-02-30"}])
def test_restore_bounds_priced_fields(bad):
    with pytest.raises(ValidationError):
        AssetRestore(**nps(nps_schemes=[{**scheme(), **bad}]))
```

- [ ] **Step 2:** Run `bash <workspace>/run-backend-tests.sh tests/test_nps_models.py -q`. Expected: FAIL (`ImportError: cannot import name 'AssetRestore'`).

- [ ] **Step 3: Implement.** In `backend/models.py`, after the `IsoDate` definition, add:

```python
NPS_SCHEME_CODE = r"^SM\d{6}$"  # the CRA's code for an NPS scheme


class NpsSchemeInput(InputModel):
    """One NPS investment option: the scheme, the share of new contributions it gets and, optionally, the units
    held on the balance date (from the statement)."""
    scheme_code: str = Field(..., pattern=NPS_SCHEME_CODE)
    scheme_name: str = Field(..., min_length=1, max_length=150)
    allocation_pct: float = Field(..., ge=0, le=100)
    units: Optional[float] = Field(None, gt=0, le=MAX_UNITS)


class NpsSchemeStored(NpsSchemeInput):
    """A scheme as stored: the input plus what pricing worked out (absent while the asset is unpriced)."""
    nav: Optional[float] = Field(None, gt=0, le=MAX_AMOUNT)
    nav_date: Optional[IsoDate] = None
    base_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)
    contribution_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)


class NpsSchemeView(NpsSchemeStored):
    """A scheme as the API returns it: units held today and their value, when priced."""
    current_units: Optional[float] = None
    current_value: Optional[float] = None


class NpsSchemeOption(BaseModel):
    """An NPS scheme the form can pick from, with its latest NAV."""
    scheme_code: str
    scheme_name: str
    pfm_name: Optional[str] = None
    nav: Optional[float] = None
    nav_date: Optional[str] = None


def _check_nps_schemes(schemes: List[NpsSchemeInput]) -> List[NpsSchemeInput]:
    codes = [s.scheme_code for s in schemes]
    if len(set(codes)) != len(codes):
        raise PydanticCustomError("nps_schemes", "Each scheme can be added once")
    if abs(sum(s.allocation_pct for s in schemes) - 100) > 0.01:
        raise PydanticCustomError("nps_schemes", "Allocations must add up to 100%")
    with_units = sum(1 for s in schemes if s.units is not None)
    if 0 < with_units < len(schemes):
        raise PydanticCustomError("nps_schemes", "Enter units for every scheme or for none")
    return schemes


NpsSchemes = Annotated[List[NpsSchemeInput], Field(min_length=1, max_length=10), AfterValidator(_check_nps_schemes)]
StoredNpsSchemes = Annotated[List[NpsSchemeStored], Field(min_length=1, max_length=10),
                             AfterValidator(_check_nps_schemes)]
```

In `AssetBase`, add these after `unit_price`:

```python
    yearly_contribution: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)  # NPS: the subscriber's own, per year
    yearly_contribution_month: Optional[int] = Field(None, ge=1, le=12)  # NPS: month it's paid (March if unset)
    nps_schemes: Optional[NpsSchemes] = None  # NPS investment options
```

Add the same three lines to `AssetUpdate`. In `Asset` (the response model), add:

```python
    nps_schemes: Optional[List[NpsSchemeView]] = None
    nps_priced_through: Optional[str] = None  # contributions up to this date are converted to units
```

After `class AssetCreate`, add:

```python
class AssetRestore(AssetCreate):
    """An asset as stored in a backup file: the create fields plus what NPS pricing worked out"""
    nps_schemes: Optional[StoredNpsSchemes] = None
    nps_priced_through: Optional[IsoDate] = None
```

In `backend/database.py`:

```python
ASSET_CLEARABLE = frozenset({"description", "annual_change_rate", "valuation_date", "monthly_contribution",
                             "interest_rate", "quantity", "unit_price", "yearly_contribution",
                             "yearly_contribution_month", "nps_schemes", "nps_priced_through"})
```

In `backend/restore.py`, import `AssetRestore` instead of `AssetCreate` and use it for `"assets"` in `LIST_SECTIONS`.

- [ ] **Step 4:** Run the new tests. Expected: PASS. Then run the whole suite (391 + 21 = 412 expected). If `tests/test_restore_parse.py` has a key-set expectation for cleaned assets, it now includes the new fields as `None`. Update that expectation and mention it in the report.
- [ ] **Step 5:** Commit: `feat: NPS contribution and investment option fields`.

---

### Task 3: NPS valuation (pure)

**Files:**
- Modify: `backend/valuation.py`
- Test: `backend/tests/test_nps_valuation.py` (create)

**Interfaces:**
- Consumes: asset dicts with the Task 2 fields.
- Produces (all in `valuation`):
  - `NavHistory = List[Tuple[date, float]]` (ascending by date)
  - `nps_contributions(asset: Dict, after: date, through: date) -> List[Tuple[date, float]]`
  - `nav_on_or_before(history: NavHistory, day: date) -> Optional[Tuple[date, float]]`
  - `nps_scheme_inputs(schemes: List[Dict]) -> List[Dict]` (input keys only)
  - `nps_priced(asset: Dict) -> bool`
  - `nps_price(asset: Dict, histories: Dict[str, NavHistory], on: date) -> Optional[Dict]`, which returns `{"nps_schemes": [...], "nps_priced_through": "YYYY-MM-DD"}`
  - `nps_scheme_classes(name: str) -> Dict[str, float]`
  - `asset_class_shares(asset: Dict, on: date) -> Dict[str, float]`
  - `asset_current_value` and `asset_view` now handle NPS
  - `portfolio_totals` uses `asset_class_shares`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_nps_valuation.py`:

```python
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
```

- [ ] **Step 2:** Run `bash <workspace>/run-backend-tests.sh tests/test_nps_valuation.py -q`. Expected: FAIL (`AttributeError: module 'valuation' has no attribute 'nps_contributions'`).

- [ ] **Step 3: Implement.** In `backend/valuation.py`:
  - add `import bisect` and `import re`;
  - import `Tuple` from `typing`;
  - extend `from models import USD_MARKETS` to `from models import MAX_AMOUNT, MAX_UNITS, USD_MARKETS`.

Then add this section after `asset_view`'s current position (keep the existing EPF/PPF code as is):

```python
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


def _nps_value_from_navs(asset: Dict, on: date) -> float:
    held = sum(_units_held(s) * s["nav"] for s in asset["nps_schemes"])
    since = parse_date(asset["nps_priced_through"])
    return held + sum(amount for _, amount in nps_contributions(asset, since, on))


def nav_on_or_before(history: NavHistory, day: date) -> Optional[Tuple[date, float]]:
    index = bisect.bisect_right(history, (day, math.inf)) - 1
    return history[index] if index >= 0 else None


def nps_price(asset: Dict, histories: Dict[str, NavHistory], on: date) -> Optional[Dict]:
    """Units and NAVs for every scheme of an NPS asset, as of `on`; None when any scheme can't be priced
    (pricing is all or nothing, so a stored asset is either fully priced or not at all)."""
    schemes = asset.get("nps_schemes") or []
    since = parse_date(asset.get("valuation_date"))
    if not schemes or since is None:
        return None
    contributions = nps_contributions(asset, since, on)
    priced = []
    for scheme in schemes:
        history = histories.get(scheme["scheme_code"]) or []
        latest, at_balance = nav_on_or_before(history, on), nav_on_or_before(history, since)
        if latest is None or at_balance is None:
            return None
        share = scheme["allocation_pct"] / 100
        units = scheme.get("units")
        base_units = units if units is not None else asset["value"] * share / at_balance[1]
        contribution_units = 0.0
        for when, amount in contributions:
            bought_at = nav_on_or_before(history, when)
            if bought_at is None:
                return None
            contribution_units += amount * share / bought_at[1]
        held = base_units + contribution_units
        if not (held <= MAX_UNITS and held * latest[1] <= MAX_AMOUNT):
            return None
        priced.append({
            **nps_scheme_inputs([scheme])[0],
            "nav": round(latest[1], 4), "nav_date": latest[0].isoformat(),
            "base_units": round(base_units, 4), "contribution_units": round(contribution_units, 4),
        })
    return {"nps_schemes": priced, "nps_priced_through": on.isoformat()}
```

Change `asset_current_value` to start with the NPS branch:

```python
def asset_current_value(asset: Dict, on: date) -> float:
    if asset.get("category") == "nps":
        return _nps_value_from_navs(asset, on) if nps_priced(asset) else _nps_value_without_navs(asset, on)
    if asset.get("category") in PROVIDENT_FUNDS and asset.get("interest_rate") is not None:
        return _provident_fund_value(asset, on)
    ...  # unchanged
```

Python resolves names at call time, so `asset_current_value` may call the NPS helpers defined further down.

Change `asset_view`:

```python
def asset_view(asset: Dict, on: date) -> Dict:
    view = {**asset, "current_value": round(asset_current_value(asset, on), 2)}
    if asset.get("category") == "nps" and nps_priced(asset):
        view["nps_schemes"] = [{**s, "current_units": round(_units_held(s), 4),
                                "current_value": round(_units_held(s) * s["nav"], 2)} for s in asset["nps_schemes"]]
    return view
```

In the asset-class section, after `_add_to_classes`, add:

```python
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
            since = parse_date(asset["nps_priced_through"])
            at_cost = sum(amount for _, amount in nps_contributions(asset, since, on))
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
```

In `portfolio_totals`, replace `_add_to_classes(by_class, ASSET_CATEGORY_CLASSES.get(asset["category"], _OTHER), value)` with `_add_to_classes(by_class, asset_class_shares(asset, on), value)`.

- [ ] **Step 4:** Run the new tests. Expected: PASS. Then run the whole suite (412 + 28 = 440 expected; report the actual count).
- [ ] **Step 5:** Commit: `feat: NPS value from contributions and scheme NAVs`.

---

### Task 4: NPS NAV service

**Files:**
- Create: `backend/nps_service.py`
- Modify: `backend/config.py` (setting `NPS_NAV_API_URL`)
- Test: `backend/tests/test_nps_service.py` (create)

**Interfaces:**
- Produces:
  - `nps_service.list_schemes() -> Optional[List[Dict]]` (async). Each dict has `scheme_code`, `scheme_name`, `pfm_name`, `nav`, `nav_date`, sorted by name.
  - `nps_service.fetch_history(code: str) -> Optional[NavHistory]` (async).
  - `nps_service.parse_latest(payload) -> List[Dict]`, `nps_service.parse_history(payload) -> NavHistory`.
  - `nps_service._get_json(url) -> Optional[Any]` (async; tests monkeypatch it), `nps_service._cache` (dict).
  - `settings.NPS_NAV_API_URL`, default `"https://npsnav.in/api"`.

Response formats (from the npsnav.in documentation):
- `GET {base}/latest` returns `{"data": [{"PFM Code": "...", "PFM Name": "...", "Scheme Code": "SM…", "Scheme Name": "...", "NAV": "46.7686", "Last Updated": "01-10-2024"}], "metadata": {...}}`.
- `GET {base}/historical/{code}` returns `{"data": [{"date": "01-10-2024", "nav": 46.7686}, …], "metadata": {...}}`, newest first.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_nps_service.py`:

```python
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


def test_an_invalid_code_is_never_requested(feed):
    assert asyncio.run(nps_service.fetch_history("../latest")) is None
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
```

- [ ] **Step 2:** Run the tests. Expected: FAIL (`ModuleNotFoundError: No module named 'nps_service'`).

- [ ] **Step 3: Implement.** In `backend/config.py` `Settings`, add after `DEMO_PASSWORD`:

```python
    NPS_NAV_API_URL: str = "https://npsnav.in/api"  # NPS scheme list and NAV history (npsnav.in, or a mirror)
```

Create `backend/nps_service.py`:

```python
"""NPS scheme list and NAV history from the npsnav.in API.

npsnav.in is free and needs no key; its data comes from the NPS CRA and is licensed CC BY-NC 4.0
(personal, non-commercial use). The base URL is a setting so a mirror or a local stub can stand in.
"""
import math
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from config import settings

CACHE_SECONDS = 6 * 60 * 60
SCHEME_CODE = re.compile(r"SM\d{6}")
_cache: Dict[str, Tuple[float, Any]] = {}


async def _get_json(url: str) -> Optional[Any]:
    """GET a JSON document; None on any network, HTTP or decoding error."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def _cached(key: str, url: str, parse: Callable[[Any], Any]) -> Optional[Any]:
    """The parsed document, from the cache when fresh; a failed or empty fetch is not cached."""
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    payload = await _get_json(url)
    parsed = parse(payload) if payload is not None else None
    if not parsed:
        return None
    _cache[key] = (time.time(), parsed)
    return parsed


def _base_url() -> str:
    return settings.NPS_NAV_API_URL.rstrip("/")


def _parse_day(text: Any) -> Optional[date]:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_nav(value: Any) -> Optional[float]:
    try:
        nav = float(value)
    except (TypeError, ValueError):
        return None
    return nav if math.isfinite(nav) and nav > 0 else None


def _rows(payload: Any) -> List[Dict]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def parse_history(payload: Any) -> List[Tuple[date, float]]:
    """(date, NAV) pairs, oldest first; rows without a usable date and a positive NAV are skipped."""
    navs: Dict[date, float] = {}
    for row in _rows(payload):
        day, nav = _parse_day(row.get("date")), _parse_nav(row.get("nav"))
        if day is not None and nav is not None:
            navs[day] = nav
    return sorted(navs.items())


def parse_latest(payload: Any) -> List[Dict]:
    """Every scheme with its latest NAV, sorted by name; rows without a valid code and a name are skipped."""
    schemes = []
    for row in _rows(payload):
        code = str(row.get("Scheme Code") or "").strip()
        name = " ".join(str(row.get("Scheme Name") or "").split())[:150]
        if not SCHEME_CODE.fullmatch(code) or not name:
            continue
        day = _parse_day(row.get("Last Updated"))
        schemes.append({
            "scheme_code": code,
            "scheme_name": name,
            "pfm_name": " ".join(str(row.get("PFM Name") or "").split()) or None,
            "nav": _parse_nav(row.get("NAV")),
            "nav_date": day.isoformat() if day else None,
        })
    return sorted(schemes, key=lambda scheme: scheme["scheme_name"])


async def list_schemes() -> Optional[List[Dict]]:
    return await _cached("latest", f"{_base_url()}/latest", parse_latest)


async def fetch_history(code: str) -> Optional[List[Tuple[date, float]]]:
    if not SCHEME_CODE.fullmatch(code or ""):
        return None
    return await _cached(f"history:{code}", f"{_base_url()}/historical/{code}", parse_history)
```

- [ ] **Step 4:** Run the new tests. Expected: PASS. Run the whole suite (440 + 13 = 453 expected) and report the count.
- [ ] **Step 5:** Commit: `feat: NPS scheme list and NAV history service`.

---

### Task 5: NPS in the API, demo data and README

**Files:**
- Modify: `backend/main.py`, `README.md`, `docs/superpowers/specs/2026-10-15-nps-contributions-and-schemes-design.md` (append the planning decisions)
- Test: `backend/tests/test_nps_api.py` (create). Update the existing demo test(s) only where they now fail for an expected reason, and say which in the report.

**Interfaces:**
- Consumes:
  - Task 2's models: `AssetRestore`, `NpsSchemeOption`.
  - Task 3's valuation functions: `nps_price`, `nps_scheme_inputs`, `asset_view`.
  - Task 4's service: `nps_service.fetch_history` and `nps_service.list_schemes`.
- Produces:
  - `POST /api/assets/{asset_id}/refresh-nav` returns `Asset`, or 400, 404 or 502.
  - `GET /api/nps/schemes` returns `List[NpsSchemeOption]`, or 502.
  - Create and update price NPS assets.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_nps_api.py`:

```python
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
```

Before running: check how `tests/test_restore_api.py` calls restore and export (its `restore` and `export` helpers), and match the endpoint paths and field name used there in `_restore` and the export call above. If they differ, use what that file uses and note it in the report.

- [ ] **Step 2:** Run `bash <workspace>/run-backend-tests.sh tests/test_nps_api.py -q`. Expected: FAIL (no pricing on create, 404/405 for the new endpoints).

- [ ] **Step 3: Implement in `backend/main.py`.** Add `import nps_service` next to `import nav_service`, and `AssetRestore` / `NpsSchemeOption` to the models import if `main.py` needs them (the restore endpoint uses `restore.parse_backup`, which Task 2 already pointed at `AssetRestore`).

Let an NPS asset with contributions or schemes carry its balance date. Extend the tuple in `_asset_defaults`:

```python
    changes_by_itself = any(row.get(key) is not None
                            for key in ("annual_change_rate", "interest_rate", "monthly_contribution",
                                        "yearly_contribution", "nps_schemes"))
```

Add the pricing helpers after `_check_deposit_dates`:

```python
# Inputs an NPS asset's units depend on; when one changes, its schemes are priced again
NPS_PRICING_FIELDS = ("value", "valuation_date", "monthly_contribution", "yearly_contribution",
                      "yearly_contribution_month", "nps_schemes", "category")


async def _nps_pricing(row: dict, on) -> Optional[dict]:
    """Units and NAVs for an NPS asset's schemes, or None when the NAVs can't be fetched or used right now."""
    histories = {}
    for scheme in row.get("nps_schemes") or []:
        history = await nps_service.fetch_history(scheme["scheme_code"])
        if not history:
            return None
        histories[scheme["scheme_code"]] = history
    return valuation.nps_price(row, histories, on)


async def _nps_changes(row: dict) -> dict:
    """What to store once an NPS asset's inputs changed: fresh pricing, or the schemes without any (saving never
    waits on the NAV service succeeding)."""
    if row.get("category") != "nps" or not row.get("nps_schemes"):
        return {"nps_priced_through": None} if row.get("nps_priced_through") else {}
    priced = await _nps_pricing(row, valuation.today())
    return priced or {"nps_schemes": valuation.nps_scheme_inputs(row["nps_schemes"]), "nps_priced_through": None}


def _nps_inputs(row: dict) -> dict:
    return {key: valuation.nps_scheme_inputs(row[key]) if key == "nps_schemes" and row.get(key) else row.get(key)
            for key in NPS_PRICING_FIELDS}
```

Replace `create_asset`'s body:

```python
    data = asset_data.model_dump()
    data.update(_value_from_quantity(data))
    data.update(_asset_defaults(data))
    data.update(await _nps_changes(data))
    return valuation.asset_view(db.create_asset(user_id, data), valuation.today())
```

Replace `update_asset`'s body after the 404 check:

```python
    changes = update_data.model_dump(exclude_unset=True)
    changes.update(_value_from_quantity(_merged(current, changes, db.ASSET_CLEARABLE)))
    changes.update(_asset_defaults(_merged(current, changes, db.ASSET_CLEARABLE)))
    merged = _merged(current, changes, db.ASSET_CLEARABLE)
    if _nps_inputs(merged) != _nps_inputs(current):
        changes.update(await _nps_changes(merged))
    elif "nps_schemes" in changes:
        changes["nps_schemes"] = current.get("nps_schemes")  # same inputs: keep what pricing worked out
    asset = db.update_asset(asset_id, user_id, changes)
    return valuation.asset_view(asset, valuation.today())
```

`_asset_defaults` now runs before the write, on the merged row. Before, it ran after the write; the stored result is the same. The existing asset tests check this.

Add the two endpoints after `delete_asset`:

```python
@app.post("/api/assets/{asset_id}/refresh-nav", response_model=Asset)
async def refresh_asset_nav(asset_id: str, user_id: str = Depends(get_user_id)):
    """Price an NPS asset's schemes again with the latest NAVs"""
    asset = db.get_asset_by_id(asset_id, user_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.get("category") != "nps" or not asset.get("nps_schemes"):
        raise HTTPException(status_code=400, detail="Only an NPS asset with investment options has NAVs to refresh")
    on = valuation.today()
    pricing = await _nps_pricing(asset, on)
    if pricing is None:
        raise HTTPException(status_code=502, detail="Couldn't fetch NPS NAVs right now")
    return valuation.asset_view(db.update_asset(asset_id, user_id, pricing), on)


@app.get("/api/nps/schemes", response_model=List[NpsSchemeOption])
async def get_nps_schemes(user_id: str = Depends(get_user_id)):
    """Every NPS scheme with its latest NAV, for choosing investment options"""
    schemes = await nps_service.list_schemes()
    if not schemes:
        raise HTTPException(status_code=502, detail="Couldn't fetch the NPS scheme list right now")
    return schemes
```

**Demo data:** in `startup_event`, replace the NPS sample asset with the following. These are generic UTI direct-plan schemes; no screenshot data.

```python
            {"name": "NPS Account", "category": "nps", "value": 350000, "notes": "National Pension Scheme",
             "monthly_contribution": 6000, "yearly_contribution": 50000, "yearly_contribution_month": 3,
             "valuation_date": iso(valuation.add_months(on, -6)),
             "nps_schemes": [
                 {"scheme_code": "SM002027", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME E - TIER I DIRECT",
                  "allocation_pct": 75, "units": None},
                 {"scheme_code": "SM002028", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME C - TIER I DIRECT",
                  "allocation_pct": 15, "units": None},
                 {"scheme_code": "SM002029", "scheme_name": "NPS TRUST A/C - UTI PENSION FUND SCHEME G - TIER I DIRECT",
                  "allocation_pct": 10, "units": None},
             ]},
```

**README:** in the assets/Indian asset types section, add an NPS subsection covering:
- the employer contribution per month and the own contribution per year (with its month, March by default), counted from the month after the balance date, on the 1st;
- investment options: pick schemes, give the % of new money and optionally the statement units;
- how the value is worked out (statement units, or the balance split by % at the balance date's NAV; each contribution buys units at the NAV on its date; contributions since the last refresh count at cost);
- that the Assets page refreshes NAVs in the background and has a Refresh NAV button;
- that without NAVs the value is the balance plus contributions, grown at the expected return when one is set;
- asset classes (E equity, C/G debt, A other, other schemes 50/50);
- the credit: "NAVs from npsnav.in (data from the NPS CRA, CC BY-NC 4.0; personal use)";
- the planning decision that contribution changes don't re-anchor: update the balance, date and units from the latest statement.

Add `NPS_NAV_API_URL` to the environment-variable table (default `https://npsnav.in/api`; a mirror or self-hosted copy of the same API).

**Spec:** append the two "Decisions made while planning" to the spec's §4 (Frontend) as **Decision** lines.

- [ ] **Step 4:** Run `tests/test_nps_api.py`, then the whole suite (453 + 15 = 468 expected). Report the count, and any existing test you changed and why.
- [ ] **Step 5:** Commit: `feat: NPS pricing on save, NAV refresh and scheme list endpoints`.

---

### Task 6: Frontend — NPS form, investment options editor, card

**Files:**
- Modify: `frontend/src/api.js`, `frontend/src/utils/assetCategories.js`, `frontend/src/pages/Assets.jsx`
- Create: `frontend/src/components/NpsSchemesEditor.jsx`, `frontend/src/components/NpsSchemeLines.jsx`

**Interfaces:**
- Consumes:
  - `POST /api/assets/{id}/refresh-nav` and `GET /api/nps/schemes` (Task 5).
  - Asset fields `yearly_contribution`, `yearly_contribution_month`, `nps_schemes[]` (`scheme_code`, `scheme_name`, `allocation_pct`, `units`, `nav`, `nav_date`, `current_units`, `current_value`) and `nps_priced_through`.

There are no frontend unit tests in this repo. Verify with the build, and trace each flow in the report.

- [ ] **Step 1: API client.** In `frontend/src/api.js`, add to `assetsAPI`:

```js
  refreshNav: (id) => api.post(`/api/assets/${id}/refresh-nav`),
```

and a new export:

```js
export const npsAPI = {
  schemes: () => api.get('/api/nps/schemes'),
};
```

- [ ] **Step 2: Category kind.** In `frontend/src/utils/assetCategories.js`, give NPS `kind: 'nps'`, and extend the comment above `ASSET_CATEGORIES` to mention `'nps'` (balance + contributions + investment options):

```js
  { value: 'nps', label: 'NPS', icon: Umbrella, color: 'bg-sky-100 text-sky-600', kind: 'nps' },
```

- [ ] **Step 3: `NpsSchemesEditor.jsx`** (create):

```jsx
import { Plus, Trash2 } from 'lucide-react';

export const MAX_NPS_SCHEMES = 10;
export const emptySchemeRow = () => ({ scheme_code: '', scheme_name: '', allocation_pct: '', units: '' });

// Problems that stop the form from saving, or null.
export function schemeRowsError(rows) {
  if (rows.length === 0) return null;
  if (rows.some((r) => !r.scheme_code)) return 'Pick each scheme from the list';
  if (new Set(rows.map((r) => r.scheme_code)).size !== rows.length) return 'Each scheme can be added once';
  const total = rows.reduce((sum, r) => sum + (parseFloat(r.allocation_pct) || 0), 0);
  if (Math.abs(total - 100) > 0.01) return 'Allocations must add up to 100%';
  const withUnits = rows.filter((r) => r.units !== '').length;
  if (withUnits > 0 && withUnits < rows.length) return 'Enter units for every scheme or for none';
  return null;
}

// The NPS investment options: a scheme picked from the published list, the % of new money it gets and,
// optionally, the units held on the balance date.
export default function NpsSchemesEditor({ rows, onChange, schemes, schemesError }) {
  const update = (index, changes) => onChange(rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  const pickByName = (index, name) => {
    const match = (schemes || []).find((s) => s.scheme_name === name);
    update(index, { scheme_name: name, scheme_code: match ? match.scheme_code : '' });
  };
  const total = rows.reduce((sum, r) => sum + (parseFloat(r.allocation_pct) || 0), 0);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="label !mb-0">Investment options (Optional)</label>
        {rows.length > 0 && (
          <span className={`text-xs font-medium ${Math.abs(total - 100) <= 0.01 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            Total {Math.round(total * 100) / 100}%
          </span>
        )}
      </div>
      {schemesError && (
        <p className="text-xs text-amber-600 dark:text-amber-400">{schemesError}</p>
      )}
      <datalist id="nps-scheme-options">
        {(schemes || []).map((s) => (
          <option key={s.scheme_code} value={s.scheme_name}>
            {[s.pfm_name, s.nav != null ? `NAV ${s.nav}` : null].filter(Boolean).join(' · ')}
          </option>
        ))}
      </datalist>
      {rows.map((row, index) => (
        <div key={index} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
          <input
            type="text"
            className="input"
            list="nps-scheme-options"
            placeholder="Search schemes, e.g., scheme E tier I"
            value={row.scheme_name}
            onChange={(e) => pickByName(index, e.target.value)}
          />
          <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
            <input
              type="number"
              className="input"
              placeholder="% of new money"
              min="0"
              max="100"
              step="any"
              value={row.allocation_pct}
              onChange={(e) => update(index, { allocation_pct: e.target.value })}
            />
            <input
              type="number"
              className="input"
              placeholder="Units (optional)"
              min="0.0001"
              step="any"
              value={row.units}
              onChange={(e) => update(index, { units: e.target.value })}
            />
            <button
              type="button"
              onClick={() => onChange(rows.filter((_, i) => i !== index))}
              className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 text-gray-500 hover:text-red-600"
              aria-label="Remove scheme"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      ))}
      {rows.length < MAX_NPS_SCHEMES && (
        <button type="button" onClick={() => onChange([...rows, emptySchemeRow()])} className="btn-secondary w-full">
          <Plus className="w-4 h-4 inline mr-2" />
          Add scheme
        </button>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Units from your statement (on the Balance as of date) give the most accurate value. Without units, the balance is
        split by these percentages at each scheme's NAV on that date. Each contribution buys units at the NAV on its
        date. When contributions change, update the balance, its date and the units from your latest statement.
        NAVs from npsnav.in.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: `NpsSchemeLines.jsx`** (create):

```jsx
import { RefreshCw } from 'lucide-react';
import { formatDate } from '../utils/dates';

// An NPS asset's schemes on its card: units × NAV and value when priced, otherwise the allocation only.
export default function NpsSchemeLines({ asset, formatCurrency, privacyMode, refreshing, onRefresh }) {
  const priced = Boolean(asset.nps_priced_through);
  return (
    <div className="mt-2 space-y-1">
      {asset.nps_schemes.map((s) => (
        <div key={s.scheme_code} className="flex items-baseline justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
          <span className="min-w-0 truncate" title={s.scheme_name}>
            {s.scheme_name} · {s.allocation_pct}%
          </span>
          {priced && s.current_units != null && (
            <span className="shrink-0 text-right">
              {privacyMode ? '••' : s.current_units.toLocaleString('en-IN', { maximumFractionDigits: 4 })} units × ₹{s.nav}
              {s.nav_date ? ` (${formatDate(s.nav_date)})` : ''} = {formatCurrency(s.current_value)}
            </span>
          )}
        </div>
      ))}
      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        {priced ? <span>Contributions priced up to {formatDate(asset.nps_priced_through)}</span> : <span>NAV not available yet</span>}
        <button
          type="button"
          onClick={() => onRefresh(asset.id)}
          disabled={refreshing}
          className="inline-flex items-center gap-1 text-primary-600 dark:text-primary-400 hover:underline disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh NAV
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: `Assets.jsx` — state, loading and refresh.**

Imports:
- add `npsAPI` to the `../api` import;
- add `NpsSchemesEditor, { emptySchemeRow, schemeRowsError }` from `../components/NpsSchemesEditor`;
- add `NpsSchemeLines` from `../components/NpsSchemeLines`;
- add `useRef` to the React import.

Constants: add `const MONTHS = ['January', …, 'December'];` with all 12 names written out.

`emptyForm()`: add `yearly_contribution: '', yearly_contribution_month: '3', nps_schemes: []`.

New state:

```jsx
  const [npsSchemes, setNpsSchemes] = useState(null);       // the scheme list, once loaded
  const [npsSchemesError, setNpsSchemesError] = useState('');
  const [refreshingIds, setRefreshingIds] = useState([]);
  const backgroundRefresh = useRef(false);
```

The functions below are placed after `fetchAssets` and before the effects that call them, so nothing is used before it is defined.

`refreshNav(id)`:

```jsx
  const refreshNav = async (id, { quiet = false } = {}) => {
    setRefreshingIds((ids) => [...ids, id]);
    try {
      const response = await assetsAPI.refreshNav(id);
      setAssets((list) => list.map((a) => (a.id === id ? response.data : a)));
    } catch (err) {
      if (!quiet) setError(errorMessage(err, 'Failed to refresh NAV'));
    } finally {
      setRefreshingIds((ids) => ids.filter((x) => x !== id));
    }
  };
```

`refreshStaleNps(list)`:

```jsx
  // NPS assets priced before today (or not at all) are refreshed one at a time after the list loads; failures are
  // quiet and the card keeps what it showed.
  const refreshStaleNps = async (list) => {
    if (backgroundRefresh.current) return;
    backgroundRefresh.current = true;
    try {
      for (const asset of list) {
        const stale = asset.category === 'nps' && asset.nps_schemes?.length
          && (!asset.nps_priced_through || asset.nps_priced_through < todayIso());
        if (stale) await refreshNav(asset.id, { quiet: true });
      }
    } finally {
      backgroundRefresh.current = false;
    }
  };
```

Call `refreshStaleNps(response.data)` in `fetchAssets` right after `setAssets(response.data)`, without awaiting it.

Load the scheme list when an NPS form is open:

```jsx
  useEffect(() => {
    if (!modalOpen || kind !== 'nps' || npsSchemes) return;
    npsAPI.schemes()
      .then((response) => { setNpsSchemes(response.data); setNpsSchemesError(''); })
      .catch(() => setNpsSchemesError("The scheme list couldn't be loaded right now; existing options stay as they are."));
  }, [modalOpen, kind, npsSchemes]);
```

`kind` is defined before this effect, so place the effect after the `const kind = …` line.

`openModal(asset)`: add to the form data:

```jsx
        yearly_contribution: asset.yearly_contribution?.toString() ?? '',
        yearly_contribution_month: asset.yearly_contribution_month?.toString() ?? '3',
        nps_schemes: (asset.nps_schemes || []).map((s) => ({
          scheme_code: s.scheme_code, scheme_name: s.scheme_name,
          allocation_pct: s.allocation_pct.toString(), units: s.units?.toString() ?? '',
        })),
```

- [ ] **Step 6: `Assets.jsx` — submit.**

In `handleSubmit`, before building `data`, add:

```jsx
      if (kind === 'nps') {
        const problem = schemeRowsError(formData.nps_schemes);
        if (problem) { setError(problem); setSubmitting(false); return; }
      }
```

The check sits inside the `try` after `setSubmitting(true)`, so it resets `submitting` itself before returning.

Change these `data` fields:

```jsx
        monthly_contribution: kind === 'provident' || kind === 'nps' ? num(formData.monthly_contribution) : null,
        yearly_contribution: kind === 'nps' ? num(formData.yearly_contribution) : null,
        yearly_contribution_month: kind === 'nps' && formData.yearly_contribution !== ''
          ? parseInt(formData.yearly_contribution_month, 10) : null,
        nps_schemes: kind === 'nps' && formData.nps_schemes.length
          ? formData.nps_schemes.map((r) => ({
            scheme_code: r.scheme_code, scheme_name: r.scheme_name,
            allocation_pct: parseFloat(r.allocation_pct), units: r.units === '' ? null : parseFloat(r.units),
          }))
          : null,
```

`value` stays `parseFloat(formData.value)` for NPS, as it is for every kind except `'quantity'`.

- [ ] **Step 7: `Assets.jsx` — the NPS form section.** Add it after the `kind === 'provident'` block:

```jsx
              {kind === 'nps' && (
                <>
                  <div>
                    <label className="label">Balance (₹)</label>
                    <input type="number" className="input" placeholder="0.00" min="0" step="0.01"
                      value={formData.value}
                      onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                      required />
                  </div>
                  <div>
                    <label className="label">Balance as of (statement date)</label>
                    <input type="date" className="input" value={formData.valuation_date}
                      onChange={(e) => setFormData({ ...formData, valuation_date: e.target.value })} />
                  </div>
                  <div>
                    <label className="label">Employer contribution ₹/month (Optional)</label>
                    <input type="number" className="input" placeholder="From your salary" min="0" step="any"
                      value={formData.monthly_contribution}
                      onChange={(e) => setFormData({ ...formData, monthly_contribution: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Own contribution ₹/year</label>
                      <input type="number" className="input" placeholder="Optional" min="0" step="any"
                        value={formData.yearly_contribution}
                        onChange={(e) => setFormData({ ...formData, yearly_contribution: e.target.value })} />
                    </div>
                    <div>
                      <label className="label">Paid in</label>
                      <select className="input" value={formData.yearly_contribution_month}
                        onChange={(e) => setFormData({ ...formData, yearly_contribution_month: e.target.value })}>
                        {MONTHS.map((month, i) => <option key={month} value={i + 1}>{month}</option>)}
                      </select>
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                    Contributions are counted on the 1st of each month from the month after the balance date.
                  </p>
                  <NpsSchemesEditor
                    rows={formData.nps_schemes}
                    onChange={(nps_schemes) => setFormData((f) => ({ ...f, nps_schemes }))}
                    schemes={npsSchemes}
                    schemesError={npsSchemesError}
                  />
                </>
              )}
```

Format each element across lines like the rest of the file. The compact form above is for the plan only. Re-read every `className` after editing.

- [ ] **Step 8: `Assets.jsx` — expected-return label and card.**

In the `kind !== 'provident'` yearly-change block:
- When `kind === 'nps'`, the label reads `Expected return % per year (Optional)`.
- The hint reads `Used for the balance and contributions while NAVs aren't available.` instead of the generic text.
- The placeholder for NPS is `e.g., 10`.

On the card, after the quantity line, add:

```jsx
                    {categoryInfo.kind === 'nps' && (asset.monthly_contribution || asset.yearly_contribution) && asset.valuation_date && (
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                        {formatCurrency(asset.value)} on {formatDate(asset.valuation_date)}
                        {asset.monthly_contribution ? ` · +${formatCurrency(asset.monthly_contribution)}/month` : ''}
                        {asset.yearly_contribution ? ` · +${formatCurrency(asset.yearly_contribution)} every ${MONTHS[(asset.yearly_contribution_month || 3) - 1]}` : ''}
                      </p>
                    )}
                    {categoryInfo.kind === 'nps' && asset.nps_schemes?.length > 0 && (
                      <NpsSchemeLines
                        asset={asset}
                        formatCurrency={formatCurrency}
                        privacyMode={privacyMode}
                        refreshing={refreshingIds.includes(asset.id)}
                        onRefresh={(id) => refreshNav(id)}
                      />
                    )}
```

The existing `asset.annual_change_rate != null && asset.valuation_date` line stays. For NPS it shows the expected return, which is correct.

- [ ] **Step 9:** Build: `bash <workspace>/build-frontend.sh` → `✓ built`.

In the report, trace these four flows:
- (a) a new NPS asset with two schemes, and the payload sent;
- (b) editing it, with rows prefilled from `nps_schemes`;
- (c) switching an NPS asset to Cash, which sends nulls for every NPS field;
- (d) the background refresh, which runs once per load and skips assets already priced today.

- [ ] **Step 10:** Commit: `feat: NPS contributions and investment options in the assets form`.

---

### Task 7: Logo and favicon

**Files:**
- Create: `frontend/public/logo.png`, `frontend/public/favicon.png`, `frontend/public/favicon-32.png`, `frontend/public/apple-touch-icon.png` (copy from the workspace's `logo/` folder; they are already cropped and sized)
- Delete: `frontend/public/vite.svg`
- Modify: `frontend/index.html`, `frontend/src/components/Layout.jsx` (mobile header and sidebar logo), `frontend/src/pages/Login.jsx`, `frontend/src/pages/Register.jsx`

- [ ] **Step 1:** Copy the four PNGs from `<workspace>/logo/` into `frontend/public/` with the same names, and `git rm frontend/public/vite.svg`.
- [ ] **Step 2:** In `frontend/index.html`, replace the `vite.svg` icon line with:

```html
    <link rel="icon" type="image/png" sizes="64x64" href="/favicon.png" />
    <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png" />
    <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png" />
```

- [ ] **Step 3:** Replace the 💰 emoji logos with the image. Keep the surrounding text and layout as they are.

Mobile header (`Layout.jsx`): `<span className="text-3xl">💰</span>` becomes

```jsx
          <img src="/logo.png" alt="NetWorth Tracker" className="w-8 h-8 rounded-lg" />
```

Sidebar (`Layout.jsx`): the whole `<div className="w-10 h-10 bg-primary-100 dark:bg-primary-900 rounded-xl flex items-center justify-center"><span className="text-2xl">💰</span></div>` becomes

```jsx
                <img src="/logo.png" alt="NetWorth Tracker" className="w-10 h-10 rounded-xl" />
```

Login and Register: the whole `<div className="inline-flex items-center justify-center w-16 h-16 bg-white rounded-2xl shadow-lg mb-4"><span className="text-4xl">💰</span></div>` becomes

```jsx
          <img src="/logo.png" alt="NetWorth Tracker" className="inline-block w-16 h-16 rounded-2xl shadow-lg mb-4" />
```

- [ ] **Step 4:** Confirm `grep -rn "💰\|vite.svg" frontend/src frontend/index.html` prints nothing. Build: `✓ built`, and `frontend/dist/` contains the four PNGs.
- [ ] **Step 5:** Commit: `feat: new app logo and favicon`, staging the four PNGs, the deleted `vite.svg` and the four edited files.

---

### Task 8: SIP fields and SIP valuation (pure)

**Files:**
- Modify: `backend/models.py` (mutual fund models), `backend/database.py` (`MUTUAL_FUND_CLEARABLE`, `update_mutual_fund`), `backend/restore.py` (`LIST_SECTIONS`), `backend/valuation.py`
- Test: `backend/tests/test_mf_sip.py` (create)

**Interfaces:**
- Consumes: `valuation.nav_on_or_before`, `valuation.NavHistory`, `add_months`, `parse_date` (Task 3 and existing code).
- Produces:
  - `MutualFundBase` / `MutualFundUpdate` fields `sip_frequency` (`"weekly" | "monthly" | "quarterly"`), `sip_day` (1–31), `sip_start_date`, `sip_end_date`, `holdings_date`.
  - `MutualFund` response fields `sip_units`, `sip_invested`, `sip_priced_through`, `total_units`, `total_invested`.
  - `models.MutualFundRestore`; `database.MUTUAL_FUND_CLEARABLE`.
  - `valuation.sip_active(fund) -> bool`
  - `valuation.sip_installments(fund, after, through) -> List[Tuple[date, float]]`
  - `valuation.sip_price(fund, history, on) -> Optional[Dict]`, whose keys are `sip_units`, `sip_invested`, `sip_priced_through`, `current_nav`, `current_value`
  - `valuation.sip_priced(fund) -> bool`
  - `valuation.fund_view(fund, on) -> Dict`
  - `portfolio_totals` values funds with `fund_view`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_mf_sip.py`:

```python
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
```

- [ ] **Step 2:** Run `bash <workspace>/run-backend-tests.sh tests/test_mf_sip.py -q`. Expected: FAIL (`ImportError: cannot import name 'MutualFundRestore'`).

- [ ] **Step 3: Implement the models.** In `backend/models.py`, import `Literal` from `typing` and `model_validator` from `pydantic`. Above `class MutualFundBase`, add:

```python
SipFrequency = Literal["weekly", "monthly", "quarterly"]


def _check_sip_dates(start: Optional[str], end: Optional[str]) -> None:
    if start and end and end < start:
        raise PydanticCustomError("sip_dates", "SIP end date must be on or after its start date")
```

In `MutualFundBase`, after `sip_amount`, add these fields and the validator:

```python
    sip_frequency: Optional[SipFrequency] = None  # monthly when a SIP is set without one
    sip_day: Optional[int] = Field(None, ge=1, le=31)  # monthly/quarterly: the day each installment lands
    sip_start_date: Optional[IsoDate] = None  # the first installment
    sip_end_date: Optional[IsoDate] = None  # no installment after this
    holdings_date: Optional[IsoDate] = None  # when `units` and `invested_amount` were accurate

    @model_validator(mode="after")
    def sip_dates_in_order(self):
        _check_sip_dates(self.sip_start_date, self.sip_end_date)
        return self
```

Add the same five fields (with the same validator) to `MutualFundUpdate`. Add to the `MutualFund` response model:

```python
    sip_units: Optional[float] = None  # units the SIP installments bought, up to sip_priced_through
    sip_invested: Optional[float] = None
    sip_priced_through: Optional[str] = None
    total_units: Optional[float] = None  # units + SIP units
    total_invested: Optional[float] = None  # invested amount + SIP installments
```

After `MutualFundCreate`, add:

```python
class MutualFundRestore(MutualFundCreate):
    """A mutual fund as stored in a backup file: the create fields plus what SIP pricing worked out"""
    sip_units: Optional[float] = Field(None, ge=0, le=MAX_UNITS)
    sip_invested: Optional[float] = Field(None, ge=0, le=MAX_AMOUNT)
    sip_priced_through: Optional[IsoDate] = None
```

In `backend/restore.py`, import `MutualFundRestore` and use it for `"mutual_funds"`.

In `backend/database.py`, add next to the other clearable sets:

```python
MUTUAL_FUND_CLEARABLE = frozenset({"sip_amount", "sip_frequency", "sip_day", "sip_start_date", "sip_end_date",
                                   "holdings_date", "sip_units", "sip_invested", "sip_priced_through"})
```

In `update_mutual_fund`, replace the `for key, value in update_data.items(): if value is not None: …` loop with `_apply_update(data["mutual_funds"][i], update_data, MUTUAL_FUND_CLEARABLE)`, keeping the `updated_at` line. Read `_apply_update` first. If it treats keys differently from the old loop (for example `id`/`user_id`), say so in the report.

- [ ] **Step 4: Implement the valuation.** In `backend/valuation.py`, after the NPS section, add:

```python
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
        later = sum(amount for _, amount in sip_installments(fund, parse_date(fund["sip_priced_through"]), on))
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
```

In `portfolio_totals`, the mutual-fund loop's `value = fund.get("current_value") or 0` becomes `value = fund_view(fund, on)["current_value"] or 0`.

- [ ] **Step 5:** Run the new tests. Expected: PASS. Then run the whole suite and report the count. Existing mutual-fund tests must still pass; funds without a SIP are unchanged.
- [ ] **Step 6:** Commit: `feat: SIP fields and installment valuation for mutual funds`.

---

### Task 9: SIPs in the mutual fund API, demo data and README

**Files:**
- Modify: `backend/nav_service.py` (`fetch_history`), `backend/main.py` (mutual fund endpoints, demo data), `README.md`
- Test: `backend/tests/test_mf_sip_api.py` (create)

**Interfaces:**
- Consumes:
  - Task 8: `valuation.sip_active/sip_price/fund_view`, `MUTUAL_FUND_CLEARABLE`.
  - Task 4: `nps_service.parse_history`. mfapi.in's `/mf/{code}` has the same `{"data": [{"date": "DD-MM-YYYY", "nav": "…"}]}` shape.
- Produces:
  - `nav_service.fetch_history(scheme_code) -> Optional[NavHistory]` (async), with the module-level `_get_history_json(scheme_code)` for tests to patch.
  - Every mutual-fund response is a `fund_view`.
  - The summary uses the views.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_mf_sip_api.py`:

```python
"""Mutual fund SIPs through the API: pricing on save and refresh, stopping a SIP, summary, restore."""
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
    """mfapi for one made-up fund; set state["up"] = False to make it unavailable."""
    frozen_today["date"] = date(2026, 6, 10)
    state = {"up": True, "history": list(HISTORY), "history_calls": 0, "today": frozen_today}

    async def fetch_nav_by_fund_name(name):
        if not state["up"]:
            return None
        when, nav = state["history"][-1]
        return {"nav": nav, "date": when.strftime("%d-%m-%Y"), "scheme_name": name, "scheme_code": "100001"}

    async def fetch_history(code):
        state["history_calls"] += 1
        return state["history"] if state["up"] and code == "100001" else None

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


def test_sip_change_prices_again(client, auth_headers, feed):
    fund = create(client, auth_headers)
    resp = client.put(f"/api/mutual-funds/{fund['id']}", json={"sip_amount": 2000}, headers=auth_headers)
    assert resp.json()["sip_units"] == 460


def test_stopping_the_sip_clears_its_pricing(client, auth_headers, feed):
    fund = create(client, auth_headers)
    resp = client.put(f"/api/mutual-funds/{fund['id']}", json={"sip_amount": None}, headers=auth_headers)
    body = resp.json()
    assert body["sip_amount"] is None and body["sip_units"] is None and body["sip_priced_through"] is None
    assert (body["total_units"], body["total_invested"]) == (100, 1000)


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
```

Match `_restore` and the export call to the helpers in `tests/test_restore_api.py`, as in Task 5.

- [ ] **Step 2:** Run the tests. Expected: FAIL (no SIP pricing; `nav_service.fetch_history` missing).

- [ ] **Step 3: NAV history.** In `backend/nav_service.py`:

```python
from nps_service import parse_history  # mfapi.in uses the same {"data": [{"date", "nav"}]} shape

_history_cache: Dict[str, Dict] = {}


async def _get_history_json(scheme_code: str):
    """mfapi.in's full NAV history for a scheme; None on any network, HTTP or decoding error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.mfapi.in/mf/{scheme_code}")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def fetch_history(scheme_code: str):
    """Every NAV the scheme has published, oldest first; None when unavailable. Cached like the latest NAV."""
    if not str(scheme_code or "").isdigit():
        return None
    cached = _history_cache.get(scheme_code)
    if cached and time.time() - cached["timestamp"] < NAV_CACHE_DURATION:
        return cached["data"]
    payload = await _get_history_json(scheme_code)
    history = parse_history(payload) if payload is not None else []
    if not history:
        return None
    _history_cache[scheme_code] = {"data": history, "timestamp": time.time()}
    return history
```

Add these tests to `test_mf_sip_api.py`. They patch `_get_history_json` and clear `_history_cache`. They cover:
- the history is parsed from an mfapi-shaped payload;
- it is cached (one call for two fetches);
- a failure is not cached;
- a non-numeric code is never requested.

- [ ] **Step 4: Endpoints (`backend/main.py`).** Add after `_nav_fits`:

```python
# Inputs a fund's SIP units depend on; when one changes, the SIP is priced again
SIP_PRICING_FIELDS = ("sip_amount", "sip_frequency", "sip_day", "sip_start_date", "sip_end_date", "holdings_date",
                      "units", "fund_name", "scheme_code")
SIP_UNPRICED = {"sip_units": None, "sip_invested": None, "sip_priced_through": None}


def _sip_defaults(row: dict) -> dict:
    """A fund with a SIP carries the dates its installments count from, a frequency and (monthly or quarterly)
    the day each installment lands."""
    if not row.get("sip_amount"):
        return {}
    changes = {}
    holdings = row.get("holdings_date") or _today_iso()
    start = row.get("sip_start_date") or holdings
    frequency = row.get("sip_frequency") or "monthly"
    if not row.get("holdings_date"):
        changes["holdings_date"] = holdings
    if not row.get("sip_start_date"):
        changes["sip_start_date"] = start
    if not row.get("sip_frequency"):
        changes["sip_frequency"] = frequency
    if frequency != "weekly" and not row.get("sip_day"):
        changes["sip_day"] = date.fromisoformat(start).day
    return changes


def _check_sip_dates(row: dict) -> None:
    start, end = row.get("sip_start_date"), row.get("sip_end_date")
    if start and end and end < start:
        raise HTTPException(status_code=422, detail="SIP end date must be on or after its start date")


async def _sip_pricing(fund: dict, on) -> Optional[dict]:
    """SIP units and the fund's NAV and value as of `on`, or None when NAVs can't be fetched or used right now."""
    code = fund.get("scheme_code")
    if not code:
        info = await nav_service.fetch_nav_by_fund_name(fund["fund_name"])
        code = info.get("scheme_code") if info else None
    history = await nav_service.fetch_history(code) if code else None
    priced = valuation.sip_price(fund, history, on) if history else None
    if priced and not fund.get("scheme_code"):
        priced["scheme_code"] = code
    return priced


async def _sip_changes(row: dict) -> dict:
    """What to store once a fund's SIP inputs changed: fresh pricing, or none (saving never waits on NAVs)."""
    if not valuation.sip_active(row):
        return dict(SIP_UNPRICED)
    return await _sip_pricing(row, valuation.today()) or dict(SIP_UNPRICED)
```

`create_mutual_fund`:

```python
    fund_dict = fund_data.model_dump()
    fund_dict.update(_sip_defaults(fund_dict))
    fund_dict = await _process_mutual_fund_data(fund_dict)
    _reject_oversized_fund(fund_dict)
    fund_dict.update(await _sip_changes(fund_dict))
    return valuation.fund_view(db.create_mutual_fund(user_id, fund_dict), valuation.today())
```

`update_mutual_fund`:

```python
    existing = db.get_mutual_fund_by_id(fund_id, user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    merged = {**existing, **update_data.model_dump(exclude_unset=True)}
    merged.update(_sip_defaults(merged))
    _check_sip_dates(merged)
    merged = await _process_mutual_fund_data(merged)
    _reject_oversized_fund(merged)
    if any(merged.get(key) != existing.get(key) for key in SIP_PRICING_FIELDS):
        merged.update(await _sip_changes(merged))
    return valuation.fund_view(db.update_mutual_fund(fund_id, user_id, merged), valuation.today())
```

Changes to the other endpoints:
- `get_mutual_fund` returns `valuation.fund_view(fund, valuation.today())`.
- `get_mutual_funds`: after the existing NAV refresh of a fund (inside `if refresh_nav`), when `valuation.sip_active(fund)`, run `pricing = await _sip_pricing(fund, on)`. When it succeeds, `db.update_mutual_fund(...)` and `fund.update(pricing)`. Return `[valuation.fund_view(f, on) for f in funds]`, with `on = valuation.today()`.
- `refresh_fund_nav`: after the NAV update, price the SIP the same way (only on success). The response's `"fund"` is `valuation.fund_view(updated_fund, on)`.
- `get_mutual_funds_summary`: build `views = [valuation.fund_view(f, on) for f in funds]`. Then `total_invested = sum(v["total_invested"] for v in views)` and `total_current = sum(v.get("current_value") or 0 for v in views)`.

**Demo data:** give the demo "UTI Nifty Index Fund" a SIP. It stays unpriced at startup, which makes no network calls.

```python
             "sip_amount": 5000, "sip_frequency": "monthly", "sip_day": 5,
             "sip_start_date": iso(valuation.add_months(on, -6)), "holdings_date": iso(valuation.add_months(on, -6)),
```

**README:** add a "SIPs" paragraph under mutual funds covering:
- the amount, frequency, day of month, first and last dates, and "units and invested amount as of";
- that each installment after that date buys units at its day's NAV (mfapi.in);
- that installments since the last refresh count at cost;
- that the Mutual Funds page refreshes SIP funds in the background;
- stopping a SIP;
- that when a SIP changes, the form moves the units and invested amount to today's totals.

- [ ] **Step 5:** Run the new tests, then the whole suite, and report the count.
- [ ] **Step 6:** Commit: `feat: SIP pricing on save and refresh for mutual funds`.

---

### Task 10: Frontend — SIP fields on the Mutual Funds page

**Files:**
- Modify: `frontend/src/pages/MutualFunds.jsx`

**Interfaces:**
- Consumes:
  - fund fields `sip_amount`, `sip_frequency`, `sip_day`, `sip_start_date`, `sip_end_date`, `holdings_date`, `sip_units`, `sip_priced_through`, `total_units`, `total_invested`, `current_value`;
  - `mutualFundsAPI.refreshNav(id)`, which returns `{status, fund}`.

- [ ] **Step 1: Form state.** Add these to the initial form and to `openModal` (prefilled from the fund):
  - `sip_amount: ''`
  - `sip_frequency: 'monthly'`
  - `sip_day: ''`
  - `sip_start_date: ''`
  - `sip_end_date: ''`
  - `holdings_date: todayIso()` (from `../utils/dates`)
  - a `sipAnchor` state: `'stored' | 'moved' | 'typed'`, reset to `'stored'` when the modal opens.

- [ ] **Step 2: Form section.** After the Units / Current NAV fields, add a "SIP (Optional)" group:
  - SIP amount (₹), `type="number" min="0" step="any"`;
  - Frequency `<select>` with Weekly / Monthly / Quarterly (values `weekly`, `monthly`, `quarterly`);
  - "SIP date (day of month)" `type="number" min="1" max="31" step="1"`, shown only for monthly or quarterly;
  - First SIP date and Last SIP date (Optional), both `type="date"`;
  - "Units and invested amount as of", `type="date"` bound to `holdings_date`.

  Hint under the group: "Each SIP installment after the 'as of' date buys units at that day's NAV (from mfapi.in); until NAVs are fetched, installments count at cost." Use `className="text-xs text-gray-400 dark:text-gray-500 !mt-1"` for hints that follow an input directly; otherwise use `mt-1` inside the field's div, as the page does elsewhere.

- [ ] **Step 3: Re-anchor on SIP changes.** When editing a fund that has a SIP (`editingFund.sip_amount > 0`) and `sipAnchor === 'stored'`, the first change to any SIP field (including clearing the amount) also sets:
  - `units` = `editingFund.total_units`;
  - `invested_amount` = `editingFund.total_invested`;
  - `current_value` = `editingFund.current_value`;
  - `holdings_date` = `todayIso()`;
  - `sipAnchor` = `'moved'`.

  Show "SIP changes apply from today: units and invested amount are today's totals." under the as-of field while `'moved'`. Typing in units, invested amount or the as-of date sets `'typed'`, and nothing moves after that.

  This mirrors the provident-fund re-anchor in `Assets.jsx`; read it first.

- [ ] **Step 4: Payload.** In `handleSubmit`, add:

```jsx
        sip_amount: formData.sip_amount === '' ? null : parseFloat(formData.sip_amount),
        sip_frequency: formData.sip_amount === '' ? null : formData.sip_frequency,
        sip_day: formData.sip_amount === '' || formData.sip_frequency === 'weekly' || formData.sip_day === ''
          ? null : parseInt(formData.sip_day, 10),
        sip_start_date: formData.sip_amount === '' ? null : (formData.sip_start_date || null),
        sip_end_date: formData.sip_amount === '' ? null : (formData.sip_end_date || null),
        holdings_date: formData.holdings_date || null,
```

- [ ] **Step 5: Card and totals.**
  - On each card, Invested shows `fund.total_invested ?? fund.invested_amount` and Units shows `fund.total_units ?? fund.units`. Returns are computed from those.
  - Add a SIP line when `fund.sip_amount > 0`: `SIP ₹5,000 monthly on day 5 · since 5 Apr 2026` (use `formatCurrency` and `formatDate`). Weekly shows `weekly`; quarterly shows `quarterly on day N`. Add `· priced to <date>` when `fund.sip_priced_through` is set.
  - The page summary uses `total_invested` and `current_value`.

- [ ] **Step 6: Background refresh.** After `fetchFunds()` loads (without the refresh flag), refresh SIP funds whose `sip_priced_through` is not today, one at a time and quietly. Call `mutualFundsAPI.refreshNav(fund.id)`; on `status === 'success'`, replace the fund in state with `response.data.fund`. Guard with a `useRef` so only one background pass runs at a time, like the NPS background refresh in `Assets.jsx`.

- [ ] **Step 7:** Build → `✓ built`. In the report, trace three flows:
  - (a) create with a monthly SIP, and the payload sent;
  - (b) edit: changing the SIP amount moves units, invested amount and as-of to today's totals;
  - (c) stopping the SIP sends nulls.
- [ ] **Step 8:** Commit: `feat: SIP fields on the Mutual Funds page`.

---

### Task 11: Automatic snapshot frequency (backend)

**Files:**
- Modify: `backend/valuation.py`, `backend/models.py`, `backend/main.py`, `README.md`
- Test: `backend/tests/test_snapshot_frequency.py` (create). Existing tests that reference `_ensure_monthly_snapshot` are updated to the new name. Say which in the report.

**Interfaces:**
- Produces:
  - `valuation.SNAPSHOT_FREQUENCIES`, `valuation.DEFAULT_SNAPSHOT_FREQUENCY`
  - `valuation.next_snapshot_date(frequency, timestamps, on) -> date`, `valuation.snapshot_due(frequency, timestamps, on) -> bool`
  - `models.SnapshotSettings` (input `{frequency}`), `models.SnapshotSettingsView` (`{frequency, next_snapshot_on}`)
  - `DashboardMetrics.snapshot_frequency`, `DashboardMetrics.next_snapshot_on`
  - `GET/PUT /api/settings/snapshots`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_snapshot_frequency.py`:

```python
"""How often the dashboard saves an automatic snapshot: weekly, every 2 weeks, monthly or quarterly."""
from datetime import date

import pytest

import valuation
from credentials import OTHER_EMAIL, OTHER_PASSWORD, OTHER_USERNAME


def ts(*days):
    return [f"{d}T00:00:00" for d in days]


@pytest.mark.parametrize("frequency, taken, on, expected", [
    ("weekly", [], date(2026, 10, 15), date(2026, 10, 15)),
    ("weekly", ts("2026-10-08"), date(2026, 10, 15), date(2026, 10, 15)),        # 7 days old: due
    ("weekly", ts("2026-10-09"), date(2026, 10, 15), date(2026, 10, 16)),        # 6 days old: tomorrow
    ("fortnightly", ts("2026-10-02"), date(2026, 10, 15), date(2026, 10, 16)),   # 13 days old
    ("fortnightly", ts("2026-10-01"), date(2026, 10, 15), date(2026, 10, 15)),   # 14 days old
    ("monthly", ts("2026-09-30"), date(2026, 10, 15), date(2026, 10, 15)),
    ("monthly", ts("2026-10-01"), date(2026, 10, 15), date(2026, 11, 1)),
    ("monthly", ts("2026-12-03"), date(2026, 12, 20), date(2027, 1, 1)),
    ("quarterly", ts("2026-03-31"), date(2026, 4, 1), date(2026, 4, 1)),         # a new quarter
    ("quarterly", ts("2026-04-01"), date(2026, 6, 30), date(2026, 7, 1)),
    ("quarterly", ts("2026-11-15"), date(2026, 12, 31), date(2027, 1, 1)),
    ("unknown", ts("2026-10-01"), date(2026, 10, 15), date(2026, 11, 1)),        # treated as monthly
])
def test_next_snapshot_date(frequency, taken, on, expected):
    assert valuation.next_snapshot_date(frequency, taken, on) == expected
    assert valuation.snapshot_due(frequency, taken, on) == (expected == on)


def test_future_snapshots_do_not_count():
    assert valuation.snapshot_due("weekly", ts("2026-10-20"), date(2026, 10, 15))


def settings(client, headers):
    return client.get("/api/settings/snapshots", headers=headers)


def test_default_is_monthly(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 10, 15)
    assert settings(client, auth_headers).json() == {"frequency": "monthly", "next_snapshot_on": "2026-10-15"}


def test_frequency_can_be_changed(client, auth_headers, frozen_today):
    frozen_today["date"] = date(2026, 10, 15)
    resp = client.put("/api/settings/snapshots", json={"frequency": "weekly"}, headers=auth_headers)
    assert resp.status_code == 200 and resp.json()["frequency"] == "weekly"
    assert settings(client, auth_headers).json()["frequency"] == "weekly"


@pytest.mark.parametrize("bad", [{"frequency": "daily"}, {"frequency": ""}, {}])
def test_unknown_frequency_is_rejected(client, auth_headers, bad):
    assert client.put("/api/settings/snapshots", json=bad, headers=auth_headers).status_code == 422


def test_each_user_has_their_own_frequency(client, auth_headers):
    client.put("/api/settings/snapshots", json={"frequency": "quarterly"}, headers=auth_headers)
    client.post("/api/auth/register", json={"username": OTHER_USERNAME, "password": OTHER_PASSWORD,
                                            "email": OTHER_EMAIL})
    token = client.post("/api/auth/login", data={"username": OTHER_USERNAME, "password": OTHER_PASSWORD}).json()
    other = {"Authorization": f"Bearer {token['access_token']}"}
    assert settings(client, other).json()["frequency"] == "monthly"


def test_settings_need_login(client):
    assert client.get("/api/settings/snapshots").status_code == 401
    assert client.put("/api/settings/snapshots", json={"frequency": "weekly"}).status_code == 401


def test_dashboard_takes_weekly_snapshots(client, auth_headers, frozen_today):
    client.post("/api/assets", json={"name": "Cash", "category": "cash", "value": 1000}, headers=auth_headers)
    client.put("/api/settings/snapshots", json={"frequency": "weekly"}, headers=auth_headers)
    frozen_today["date"] = date(2026, 10, 1)
    first = client.get("/api/dashboard", headers=auth_headers).json()
    assert len(first["net_worth_history"]) == 1
    assert (first["snapshot_frequency"], first["next_snapshot_on"]) == ("weekly", "2026-10-08")
    frozen_today["date"] = date(2026, 10, 7)  # 6 days later: not yet
    assert len(client.get("/api/dashboard", headers=auth_headers).json()["net_worth_history"]) == 1
    frozen_today["date"] = date(2026, 10, 8)  # 7 days later: due
    assert len(client.get("/api/dashboard", headers=auth_headers).json()["net_worth_history"]) == 2


def test_dashboard_reports_the_next_monthly_snapshot(client, auth_headers, frozen_today):
    client.post("/api/assets", json={"name": "Cash", "category": "cash", "value": 1000}, headers=auth_headers)
    frozen_today["date"] = date(2026, 10, 15)
    body = client.get("/api/dashboard", headers=auth_headers).json()
    assert (body["snapshot_frequency"], body["next_snapshot_on"]) == ("monthly", "2026-11-01")
```

- [ ] **Step 2:** Run the new tests. Expected: FAIL (`AttributeError: module 'valuation' has no attribute 'next_snapshot_date'`).

- [ ] **Step 3: Valuation.** Add at the end of `backend/valuation.py`:

```python
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
```

- [ ] **Step 4: Models.** In `backend/models.py`, import `Literal` if Task 8 hasn't already, then add:

```python
SnapshotFrequency = Literal["weekly", "fortnightly", "monthly", "quarterly"]


class SnapshotSettings(InputModel):
    frequency: SnapshotFrequency


class SnapshotSettingsView(BaseModel):
    frequency: str
    next_snapshot_on: str
```

Add to `DashboardMetrics`:

```python
    snapshot_frequency: str = "monthly"
    next_snapshot_on: Optional[str] = None  # the first day the next automatic snapshot is due
```

- [ ] **Step 5: API (`backend/main.py`).** Replace `_ensure_monthly_snapshot` with:

```python
def _snapshot_frequency(user_id: str) -> str:
    user = db.get_user_by_id(user_id) or {}
    return user.get("snapshot_frequency") or valuation.DEFAULT_SNAPSHOT_FREQUENCY


def _snapshot_timestamps(user_id: str) -> List[str]:
    return [s["timestamp"] for s in db.get_snapshots_by_user(user_id, limit=None)]


def _ensure_auto_snapshot(user_id: str, totals: dict, on, frequency: str) -> None:
    """A snapshot saved the first time the dashboard is opened once one is due at the user's frequency
    (manual snapshots count). Empty accounts are skipped."""
    if not totals["total_assets"] and not totals["total_liabilities"]:
        return
    if not valuation.snapshot_due(frequency, _snapshot_timestamps(user_id), on):
        return
    try:
        db.create_snapshot(user_id, totals["total_assets"], totals["total_liabilities"],
                           breakdown=_snapshot_breakdown(totals), timestamp=f"{on.isoformat()}T00:00:00")
    except OSError:
        # The dashboard is a read; a full or read-only disk must not break it. The next visit tries again.
        logger.warning("Could not save the automatic snapshot", exc_info=True)
```

In `get_dashboard`:
- set `frequency = _snapshot_frequency(user_id)`;
- call `_ensure_auto_snapshot(user_id, totals, on, frequency)`;
- add to the `DashboardMetrics(...)` arguments:

```python
        snapshot_frequency=frequency,
        next_snapshot_on=valuation.next_snapshot_date(frequency, _snapshot_timestamps(user_id), on).isoformat(),
```

Add the endpoints after `create_snapshot`:

```python
def _snapshot_settings(user_id: str) -> dict:
    frequency = _snapshot_frequency(user_id)
    next_on = valuation.next_snapshot_date(frequency, _snapshot_timestamps(user_id), valuation.today())
    return {"frequency": frequency, "next_snapshot_on": next_on.isoformat()}


@app.get("/api/settings/snapshots", response_model=SnapshotSettingsView)
async def get_snapshot_settings(user_id: str = Depends(get_user_id)):
    """How often the dashboard saves an automatic snapshot, and when the next one is due"""
    return _snapshot_settings(user_id)


@app.put("/api/settings/snapshots", response_model=SnapshotSettingsView)
async def update_snapshot_settings(body: SnapshotSettings, user_id: str = Depends(get_user_id)):
    """Change how often the dashboard saves an automatic snapshot"""
    db.update_user(user_id, {"snapshot_frequency": body.frequency})
    return _snapshot_settings(user_id)
```

Import `SnapshotSettings` and `SnapshotSettingsView` from models. Read `db.update_user` first, and confirm it stores a new key on the user record.

- [ ] **Step 6: README.** In the snapshots section, cover:
  - the four frequencies and how each is decided;
  - that the dashboard shows the next date and the selector;
  - that the setting is per user and not part of backups.
- [ ] **Step 7:** Run the new tests, then the whole suite. Report the count and any existing test you updated.
- [ ] **Step 8:** Commit: `feat: choose how often automatic snapshots are saved`.

---

### Task 12: Frontend — auto snapshot frequency on the dashboard

**Files:**
- Modify: `frontend/src/api.js`, `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Consumes:
  - the dashboard fields `snapshot_frequency` and `next_snapshot_on`;
  - `PUT /api/settings/snapshots` (`{frequency}` → `{frequency, next_snapshot_on}`).

- [ ] **Step 1:** In `api.js`, add:

```js
export const snapshotSettingsAPI = {
  get: () => api.get('/api/settings/snapshots'),
  update: (frequency) => api.put('/api/settings/snapshots', { frequency }),
};
```

- [ ] **Step 2: Constants** in `Dashboard.jsx`:

```jsx
const SNAPSHOT_FREQUENCIES = [
  { value: 'weekly', label: 'Weekly', phrase: 'every week' },
  { value: 'fortnightly', label: 'Every 2 weeks', phrase: 'every 2 weeks' },
  { value: 'monthly', label: 'Monthly', phrase: 'once a month' },
  { value: 'quarterly', label: 'Quarterly', phrase: 'once a quarter' },
];
```

- [ ] **Step 3: Control.** Next to the "Save Snapshot" button (in the same header row), add a labelled select. The row must wrap on narrow screens (`flex flex-wrap items-center gap-2`):

```jsx
<label htmlFor="auto-snapshot" className="text-sm text-gray-600 dark:text-gray-400">Auto snapshot</label>
<select
  id="auto-snapshot"
  className="input !w-auto !py-2 text-sm"
  value={data.snapshot_frequency || 'monthly'}
  onChange={(e) => changeSnapshotFrequency(e.target.value)}
  disabled={frequencySaving}
>
  {SNAPSHOT_FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
</select>
```

Below the row, add the caption:

```jsx
{data.next_snapshot_on && (
  <p className="text-xs text-gray-500 dark:text-gray-400">
    Next automatic snapshot: {formatDate(data.next_snapshot_on)} — saved when you open the dashboard on or after that day.
  </p>
)}
```

`changeSnapshotFrequency(value)`:
- sets `frequencySaving`;
- calls `snapshotSettingsAPI.update(value)`;
- merges `{snapshot_frequency, next_snapshot_on}` from the response into the dashboard state;
- on error, shows the message through the page's existing error display, with `errorMessage(err, 'Failed to change the snapshot frequency')`.

Adapt the names to the ones `Dashboard.jsx` actually uses for its dashboard data, its error display and the snapshot handler. Confirm that the existing reload after a manual "Save Snapshot" brings the new `next_snapshot_on`.

- [ ] **Step 4:** Change the history empty-state text to name the chosen frequency:

```jsx
A snapshot is saved automatically {phrase} when you open the dashboard; Save Snapshot adds one now.
```

`phrase` comes from `SNAPSHOT_FREQUENCIES`; it defaults to "once a month".

- [ ] **Step 5:** Build → `✓ built`. In the report, trace three flows:
  - changing the select;
  - the caption after Save Snapshot;
  - the narrow-screen wrap.
- [ ] **Step 6:** Commit: `feat: auto snapshot frequency on the dashboard`.

---

### Task 13: Warnings for failed price and NAV sources (backend)

**Files:**
- Create: `backend/user_warnings.py`
- Modify: `backend/main.py` (middleware, CORS `expose_headers`, call sites), `backend/exchange_service.py` (live or fallback flag)
- Test: `backend/tests/test_source_warnings.py` (create)

**Interfaces:**
- Produces:
  - `user_warnings.warn(message: str) -> None`, `user_warnings.start() -> token`, `user_warnings.collected() -> List[str]`, `user_warnings.stop(token)`;
  - the `X-Warnings` response header (a JSON array of strings);
  - `exchange_service.last_rate_was_live() -> bool`.
- Consumes: the call sites in `main.py` for mutual funds (incl. SIP pricing from Task 9), NPS (Task 5), equities and the USD rate.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_source_warnings.py`. Use these cases. Adapt payload field names to the real models where noted, since equities may need more fields.

```python
"""A failed price or NAV source is reported to the UI in the X-Warnings response header."""
import json
from datetime import date

import pytest

import exchange_service
import nav_service
import nps_service
import stock_service

E = "TEST PENSION FUND SCHEME E - TIER I"


def warnings_of(resp):
    raw = resp.headers.get("x-warnings")
    return json.loads(raw) if raw else []


def fund(name, **extra):
    return {"fund_name": name, "amc": "Test AMC", "category": "equity", "units": 10, "invested_amount": 1000, **extra}


@pytest.fixture
def sources_down(monkeypatch):
    async def none(*args, **kwargs):
        return None

    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", none)
    monkeypatch.setattr(nav_service, "fetch_history", none)
    monkeypatch.setattr(nps_service, "fetch_history", none)
    monkeypatch.setattr(nps_service, "list_schemes", none)
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)


def test_no_header_when_nothing_went_wrong(client, auth_headers):
    resp = client.get("/api/assets", headers=auth_headers)
    assert resp.status_code == 200 and "x-warnings" not in resp.headers


def test_mutual_fund_nav_unavailable_on_save(client, auth_headers, sources_down):
    resp = client.post("/api/mutual-funds", json=fund("Test Fund"), headers=auth_headers)
    assert resp.status_code == 201
    assert any("Test Fund" in w and "mfapi.in" in w for w in warnings_of(resp))


def test_mutual_fund_list_refresh_names_the_funds_it_missed(client, auth_headers, sources_down):
    for name in ("Fund One", "Fund Two"):
        client.post("/api/mutual-funds", json=fund(name, current_nav=100), headers=auth_headers)
    found = warnings_of(client.get("/api/mutual-funds?refresh_nav=true", headers=auth_headers))
    assert len(found) == 1 and "Fund One" in found[0] and "Fund Two" in found[0]


def test_single_fund_refresh_failure_warns(client, auth_headers, sources_down):
    created = client.post("/api/mutual-funds", json=fund("Test Fund", current_nav=100), headers=auth_headers).json()
    resp = client.post(f"/api/mutual-funds/{created['id']}/refresh-nav", headers=auth_headers)
    assert any("Test Fund" in w for w in warnings_of(resp))


def test_sip_installments_unpriced_warns(client, auth_headers, sources_down, frozen_today):
    frozen_today["date"] = date(2026, 6, 10)
    resp = client.post("/api/mutual-funds", json=fund(
        "Sip Fund", current_nav=100, sip_amount=1000, sip_frequency="monthly", sip_day=5,
        sip_start_date="2026-04-05", holdings_date="2026-04-01"), headers=auth_headers)
    assert any("SIP" in w and "Sip Fund" in w for w in warnings_of(resp))


def test_nps_save_without_navs_warns(client, auth_headers, sources_down):
    resp = client.post("/api/assets", json={
        "name": "My NPS", "category": "nps", "value": 1000, "valuation_date": "2026-03-31",
        "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100}]}, headers=auth_headers)
    assert resp.status_code == 201
    assert any("npsnav.in" in w and "My NPS" in w for w in warnings_of(resp))


def test_nps_refresh_failure_warns_with_the_502(client, auth_headers, sources_down):
    asset = client.post("/api/assets", json={
        "name": "My NPS", "category": "nps", "value": 1000, "valuation_date": "2026-03-31",
        "nps_schemes": [{"scheme_code": "SM900001", "scheme_name": E, "allocation_pct": 100}]},
        headers=auth_headers).json()
    resp = client.post(f"/api/assets/{asset['id']}/refresh-nav", headers=auth_headers)
    assert resp.status_code == 502 and any("npsnav.in" in w for w in warnings_of(resp))


def test_nps_scheme_list_failure_warns(client, auth_headers, sources_down):
    resp = client.get("/api/nps/schemes", headers=auth_headers)
    assert resp.status_code == 502 and any("scheme list" in w for w in warnings_of(resp))


def test_stock_price_unavailable_warns(client, auth_headers, sources_down):
    # Use the real equity create payload (see EquityCreate): a symbol, market and quantity are needed.
    resp = client.post("/api/equities", json={"symbol": "TESTCO", "market": "NSE", "quantity": 5,
                                              "avg_buy_price": 100}, headers=auth_headers)
    assert any("TESTCO" in w for w in warnings_of(resp))


def test_usd_rate_unavailable_warns(client, auth_headers, monkeypatch):
    async def none():
        return None

    for name in ("_try_exchange_rate_api", "_try_frankfurter_api", "_try_fawazahmed_api"):
        monkeypatch.setattr(exchange_service, name, none)
    monkeypatch.setattr(exchange_service, "_cached_rate", None)
    monkeypatch.setattr(exchange_service, "_cache_timestamp", 0)
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)
    client.post("/api/equities", json={"symbol": "TESTUS", "market": "NASDAQ", "quantity": 1, "avg_buy_price": 10,
                                       "current_price": 12}, headers=auth_headers)
    resp = client.get("/api/dashboard", headers=auth_headers)
    assert any("USD" in w for w in warnings_of(resp))


def test_identical_warnings_are_sent_once():
    import user_warnings
    token = user_warnings.start()
    try:
        user_warnings.warn("same")
        user_warnings.warn("same")
        assert user_warnings.collected() == ["same"]
    finally:
        user_warnings.stop(token)


def test_warn_outside_a_request_is_ignored():
    import user_warnings
    user_warnings.warn("nobody is listening")  # must not raise


def test_header_is_exposed_to_browsers(client, auth_headers):
    resp = client.get("/api/assets", headers={**auth_headers, "Origin": "http://localhost:5173"})
    assert "x-warnings" in resp.headers.get("access-control-expose-headers", "").lower()
```

- [ ] **Step 2:** Run the new tests. Expected: FAIL (`ModuleNotFoundError: No module named 'user_warnings'`).

- [ ] **Step 3: Collector** — `backend/user_warnings.py`:

```python
"""Warnings for the user collected while handling one request, e.g. a NAV source that couldn't be reached.

The middleware in main.py starts a list per request and sends what was collected in the X-Warnings header.
A list (not a tuple) is stored so that code running in a copied context (a thread or a child task) appends to
the same list.
"""
from contextvars import ContextVar, Token
from typing import List, Optional

_current: ContextVar[Optional[List[str]]] = ContextVar("user_warnings", default=None)


def start() -> Token:
    return _current.set([])


def stop(token: Token) -> None:
    _current.reset(token)


def warn(message: str) -> None:
    """Add a warning for this request; repeats are kept once, and outside a request it does nothing."""
    collected = _current.get()
    if collected is not None and message not in collected:
        collected.append(message)


def collected() -> List[str]:
    return list(_current.get() or [])
```

- [ ] **Step 4: Middleware and CORS** in `backend/main.py`. Import `json` and `user_warnings`. In the `CORSMiddleware` arguments, add `expose_headers=["X-Warnings"]`. Then add:

```python
@app.middleware("http")
async def send_user_warnings(request, call_next):
    """Warnings collected while handling the request (e.g. an unreachable NAV source) go back in X-Warnings."""
    token = user_warnings.start()
    try:
        response = await call_next(request)
        found = user_warnings.collected()
        if found:
            response.headers["X-Warnings"] = json.dumps(found, ensure_ascii=True)
        return response
    finally:
        user_warnings.stop(token)
```

Register it so the CORS middleware still wraps it: FastAPI applies the last-added middleware outermost. Check that the CORS test passes, and say in the report how the order works.

- [ ] **Step 5: Exchange rate.** In `backend/exchange_service.py`:
- add a module flag `_last_live = True`;
- in `fetch_usd_to_inr`, set it to `True` when it returns a fresh-cache or live rate, and to `False` when it falls back (stale cache or `FALLBACK_RATE`);
- add `def last_rate_was_live() -> bool: return _last_live`.

In `main.py`, wherever the dashboard or totals fetch the rate (`valuation.usd_rate_if_needed` / `fetch_usd_to_inr`), call `user_warnings.warn("Couldn't fetch the USD→INR rate; US stock values use the last known rate.")` after a rate was actually fetched and `not exchange_service.last_rate_was_live()`. Do not warn when no rate was needed.

- [ ] **Step 6: Call sites** in `backend/main.py`, with the wording from spec Part E:
- `_process_mutual_fund_data`: when it tried to fetch the NAV (no `current_nav`) and got None.
- `get_mutual_funds` with `refresh_nav`: collect the names of the funds whose fetch failed. After the loop, issue one warning naming them.
- `refresh_fund_nav`: on failure.
- SIP (Task 9's `_sip_changes` / refresh paths): when an active SIP couldn't be priced. Use the fund name.
- NPS: `_nps_changes` when pricing failed (use the asset name); `refresh_asset_nav` before raising the 502; `get_nps_schemes` before raising the 502.
- Equities: everywhere `stock_service.fetch_stock_price` returns None: create, single refresh, the lookup endpoint, and the list refresh (one warning naming the symbols).

Keep each message to one sentence. Write the rupee and arrow characters as they are; `ensure_ascii` escapes them in the header.

- [ ] **Step 7:** Run the new tests, then the whole suite, and report the count. Existing tests that assert exact headers are unaffected; if one breaks, explain why.
- [ ] **Step 8:** Commit: `feat: warn when a price or NAV source can't be reached`.

---

### Task 14: Frontend — dismissible warning toasts

**Files:**
- Create: `frontend/src/utils/notices.js`, `frontend/src/components/Notices.jsx`
- Modify: `frontend/src/api.js` (response interceptor), `frontend/src/App.jsx` (mount `<Notices />` once)

**Interfaces:**
- Consumes: the `X-Warnings` header (a JSON array of strings) on any API response, successful or not.

- [ ] **Step 1: Notice hub** — `frontend/src/utils/notices.js`:

```js
// A tiny hub for warnings shown as dismissible toasts: the API client publishes, <Notices /> listens.
const listeners = new Set();

export function publishWarnings(messages) {
  messages.forEach((message) => listeners.forEach((listener) => listener(message)));
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
```

- [ ] **Step 2: Interceptor** in `frontend/src/api.js`. Read the existing interceptors first. Add the warning surfacing to the existing response interceptor rather than adding a second one that could change the order of the 401 handling.

```js
import { publishWarnings } from './utils/notices';

// Warnings about unreachable price or NAV sources come back in the X-Warnings header (a JSON array).
const surfaceWarnings = (response) => {
  const raw = response?.headers?.['x-warnings'];
  if (!raw) return;
  try {
    const messages = JSON.parse(raw);
    if (Array.isArray(messages)) publishWarnings(messages.filter((m) => typeof m === 'string' && m));
  } catch {
    // a malformed header is ignored
  }
};
```

Call `surfaceWarnings(response)` in the success handler and `surfaceWarnings(error.response)` in the error handler, before the existing logic.

- [ ] **Step 3: Toasts** — `frontend/src/components/Notices.jsx`:

```jsx
import { useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { subscribe } from '../utils/notices';

const SHOW_FOR_MS = 15000;
let nextId = 0;

// Warnings flashed in the top-right corner; each can be dismissed and hides on its own after 15 seconds.
export default function Notices() {
  const [notices, setNotices] = useState([]);

  useEffect(() => subscribe((message) => {
    setNotices((list) => {
      if (list.some((n) => n.message === message)) return list;
      const id = ++nextId;
      setTimeout(() => setNotices((current) => current.filter((n) => n.id !== id)), SHOW_FOR_MS);
      return [...list, { id, message }];
    });
  }), []);

  const dismiss = (id) => setNotices((list) => list.filter((n) => n.id !== id));

  if (notices.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-[60] w-[calc(100%-2rem)] max-w-sm space-y-2" aria-live="polite">
      {notices.map((n) => (
        <div
          key={n.id}
          role="status"
          className="flex items-start gap-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/60 text-amber-800 dark:text-amber-100 px-4 py-3 shadow-lg"
        >
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-sm flex-1">{n.message}</p>
          <button
            type="button"
            onClick={() => dismiss(n.id)}
            aria-label="Dismiss"
            className="p-1 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-800/60"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}
```

`setTimeout` inside the state updater can run twice in React StrictMode (development only). The second timer just removes an already-removed id, which is harmless. If the project uses StrictMode, note it in the report.

- [ ] **Step 4:** Mount `<Notices />` once in `frontend/src/App.jsx`, inside the providers and outside the routes, so it shows on every page.
- [ ] **Step 5:** Build → `✓ built`. In the report, trace three flows:
  - a 502 from an NPS refresh carrying the header shows one toast;
  - three identical warnings show one toast;
  - dismiss removes it, and it also disappears after 15 s.
- [ ] **Step 6:** Commit: `feat: dismissible warning toasts for unreachable price and NAV sources`.

---

### Task 15: Browser check (controller)

The controller runs this check; there is no subagent.

**Setup:**
- Start a throwaway backend on a free port with `CREATE_DEMO_DATA=false`, a generated `SECRET_KEY` and a temp `DATA_FILE`.
- Set `NPS_NAV_API_URL=http://127.0.0.1:<stub port>/api`, pointing at a local static stub. The stub serves `/api/latest` and `/api/historical/SM9000{01,02,03}` in the documented formats, with made-up names (`TEST PENSION FUND SCHEME E/C/G - TIER I`) and made-up NAVs.
- Start Vite with the /tmp config: proxy to the backend, `cacheDir` under /tmp.

**Checks:**
1. The Liability form: the hint under EMI / tenure sits below the inputs. The hint's `getBoundingClientRect().top` is ≥ both inputs' `bottom`. Do the same for one Assets and one Bank Accounts hint.
2. Add an NPS asset:
   - set the balance, a balance date three months back, an employer contribution, and an own contribution in a month inside that window;
   - add two schemes from the datalist at 60/40;
   - the save succeeds, and the card shows units × NAV = value per scheme plus "Contributions priced up to <today>".
3. Edit it: the rows are prefilled. Set the allocations to 50/40 and the form refuses with "Allocations must add up to 100%". Fix them and save.
4. Stop the stub, then press Refresh NAV: an error message appears and the card keeps its numbers. Restart the stub and refresh: it works.
5. The dashboard's asset-class allocation shows equity and debt from the schemes.
6. Privacy mode masks the units and the amounts on the card.
7. Mutual fund SIP, using the real mfapi.in, which is reachable from this machine:
   - create a fund with units from three months back and a monthly SIP;
   - the card shows the SIP line, the totals include the installments, and "priced to <today>" appears;
   - edit and change the SIP amount: the units, invested amount and as-of fields move to today's totals and show the hint;
   - stopping the SIP sends nulls.
8. Logo:
   - the sidebar, the mobile header (at phone width), Login and Register show the new image, and no 💰 remains;
   - the tab's favicon request for `/favicon.png` returns 200.
9. Auto snapshot:
   - the dashboard shows the "Auto snapshot" selector (Monthly) and "Next automatic snapshot: 1 <next month>";
   - switching to Weekly saves, and the caption moves to 7 days after the latest snapshot;
   - the setting survives a reload;
   - at phone width the header wraps without overflowing.
10. Source warnings:
    - with the NPS stub stopped, press Refresh NAV: one amber toast names npsnav.in, the per-card error also shows, the × dismisses the toast, and it hides on its own after about 15 s;
    - with the stub stopped, open the NPS form: the scheme-list toast appears;
    - a response without problems shows no toast.

Stop every server and delete the temp files afterwards.

---

## After the plan

Final whole-branch review → one fix wave → scoped re-review. Then the controller squashes `origin/main..feat/nps-schemes` into the single commit of `feat/networth-gaps`:
- tree = the final tree, parent = `origin/main`, the existing message plus an NPS paragraph;
- force-push with lease from the current remote SHA;
- reset local `main` to it with `--keep`.
