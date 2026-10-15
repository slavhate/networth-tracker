# Asset-Class Allocation and Automatic Snapshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allocation by asset class; snapshots that store a breakdown and are taken automatically once a month; month-over-month change and allocation history on the dashboard.

**Architecture:** `valuation.portfolio_totals` adds `assets_by_class` from a category → class mapping. Snapshots store the three breakdown maps; the dashboard endpoint takes the month's snapshot on first visit. The frontend adds a class view to the allocation pie, a change line on the net-worth card, and a stacked allocation-history chart.

**Tech Stack:** FastAPI 0.115, Pydantic 2.10, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3 + Recharts 2. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-14-allocation-and-snapshots-design.md`. Read it before starting any task.

## Global Constraints

- **Branch / worktree:** `feat/allocation-snapshots` from local `main` at `7fe32fe`. Local commits only.
- **Environment:** Python/Node only in WSL; use the controller's helper scripts.
- **Expected totals:** 332 before; 335 after Task 1; 345 after Task 2.
- **Tests never touch the network** (`offline_markets`); dates frozen with `frozen_today` (default 2026-10-14).
- **No hardcoded credentials, secrets or personal data**; fake test data. **No new dependencies.**
- **Commits:** use the command in your dispatch's working rules.

## Review Focus

1. A snapshot taken this month by "Save Snapshot" must stop the automatic one (Task 2 tests it).
2. Old snapshots without a breakdown keep rendering (history chart) and are skipped by the allocation-history chart (Task 3; controller checks).
3. Classes always sum to total assets within rounding, including NPS/hybrid splits (Task 1 tests the split).
4. Privacy mode masks the month-over-month amount and percentage (controller checks).
5. Restore accepts backups with and without breakdowns, and rejects bad values (Task 2 tests it).

---

### Task 1: Asset classes in the totals

**Files:** Modify `backend/valuation.py`, `backend/models.py` (`DashboardMetrics`); Test `backend/tests/test_valuation.py` (append 3)

**Interfaces:** Produces `valuation.ASSET_CLASSES`, the class maps, and `portfolio_totals(...)["assets_by_class"]`; `DashboardMetrics.assets_by_class: dict = {}`. Tasks 2–3 rely on the key name and class keys.

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_valuation.py`:

```python
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
```

(Check of the first case — equity: NPS 50 + ESOP 30 + equity fund 40 + hybrid 10 + stock 25 = 155; debt: EPF 200 + NPS 50 + FD 20 + hybrid 10 + liquid 5 = 285; cash: 100 + savings 10; other: vehicles 70.)

- [ ] **Step 2: Run; FAIL** (`KeyError: 'assets_by_class'`).

- [ ] **Step 3: Implement** — in `backend/valuation.py`, add above the "Totals" section:

```python
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
```

Then rewrite `portfolio_totals` so each item's value is computed once and added both to its category/bucket and to its classes:

```python
def portfolio_totals(assets: List[Dict], liabilities: List[Dict], bank_accounts: List[Dict],
                     mutual_funds: List[Dict], equities: List[Dict], usd_to_inr: Optional[float],
                     on: date) -> Dict:
    assets_by_category: Dict[str, float] = {}
    by_class: Dict[str, float] = {}
    for asset in assets:
        value = asset_current_value(asset, on)
        assets_by_category[asset["category"]] = assets_by_category.get(asset["category"], 0) + value
        _add_to_classes(by_class, ASSET_CATEGORY_CLASSES.get(asset["category"], _OTHER), value)

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
        value = fund.get("current_value") or 0
        buckets["mutual_funds"] += value
        _add_to_classes(by_class, MUTUAL_FUND_CLASSES.get(fund.get("category"), _OTHER), value)
    for name, total in buckets.items():
        if total > 0:
            assets_by_category[name] = total
```

and keep the liability loop and the return as they are, adding to the returned dict:

```python
        "assets_by_class": {c: round(by_class[c], 2) for c in ASSET_CLASSES if by_class.get(c, 0) > 0},
```

`models.DashboardMetrics` gains `assets_by_class: dict = {}`.

- [ ] **Step 4:** test_valuation.py, then the full suite — `335 passed` (the existing totals tests must still pass unchanged).
- [ ] **Step 5: Commit** — `feat: allocation by asset class in the portfolio totals`.

---

### Task 2: Snapshots with a breakdown, taken automatically each month

**Files:** Modify `backend/database.py`, `backend/models.py`, `backend/main.py` (snapshot route, dashboard, startup demo data), `README.md`; Test `backend/tests/test_allocation_snapshots.py` (create, 9 tests)

**Interfaces:** Consumes `portfolio_totals(...)["assets_by_class"]` (Task 1). Produces snapshot rows/responses with optional `assets_by_category`, `liabilities_by_category`, `assets_by_class`; `database.SNAPSHOT_BREAKDOWN`; `database.create_snapshot(user_id, total_assets, total_liabilities, breakdown=None, timestamp=None)`. Task 3 reads the snapshot fields.

- [ ] **Step 1: Failing tests** — `backend/tests/test_allocation_snapshots.py`:

```python
import json
from datetime import date

import pytest

import database as db

pytestmark = pytest.mark.usefixtures("offline_markets")


def add_asset(client, headers, **body):
    resp = client.post("/api/assets", headers=headers, json={"name": "Test asset", "category": "cash", "value": 1000, **body})
    assert resp.status_code == 201, resp.text


def snapshots(client, headers):
    return client.get("/api/export", headers=headers).json()["snapshots"]


def test_dashboard_reports_assets_by_class(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    add_asset(client, auth_headers, category="gold", value=500)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert metrics["assets_by_class"] == {"gold": 500, "cash": 1000}


def test_a_manual_snapshot_stores_the_breakdown(client, auth_headers, frozen_today):
    add_asset(client, auth_headers, category="ppf", value=2000)
    snapshot = client.post("/api/snapshot", headers=auth_headers).json()
    assert snapshot["assets_by_class"] == {"debt": 2000}
    assert snapshot["assets_by_category"] == {"ppf": 2000}
    assert snapshot["liabilities_by_category"] == {}


def test_the_first_dashboard_visit_each_month_saves_one_snapshot(client, auth_headers, frozen_today):
    add_asset(client, auth_headers)
    client.get("/api/dashboard", headers=auth_headers)
    client.get("/api/dashboard", headers=auth_headers)
    [first] = snapshots(client, auth_headers)
    assert first["timestamp"] == "2026-10-14T00:00:00"
    assert first["assets_by_class"] == {"cash": 1000}

    frozen_today["date"] = date(2026, 11, 2)
    metrics = client.get("/api/dashboard", headers=auth_headers).json()
    assert sorted(s["timestamp"] for s in snapshots(client, auth_headers)) == ["2026-10-14T00:00:00", "2026-11-02T00:00:00"]
    assert metrics["net_worth_history"][0]["timestamp"] == "2026-11-02T00:00:00"


def test_a_manual_snapshot_this_month_stops_the_automatic_one(client, auth_headers, frozen_today, monkeypatch):
    add_asset(client, auth_headers)
    monkeypatch.setattr(db, "get_timestamp", lambda: "2026-10-05T10:00:00")
    client.post("/api/snapshot", headers=auth_headers)
    client.get("/api/dashboard", headers=auth_headers)
    assert [s["timestamp"] for s in snapshots(client, auth_headers)] == ["2026-10-05T10:00:00"]


def test_an_empty_account_gets_no_automatic_snapshot(client, auth_headers, frozen_today):
    client.get("/api/dashboard", headers=auth_headers)
    assert snapshots(client, auth_headers) == []


def test_export_and_restore_keep_the_breakdown(client, auth_headers, frozen_today):
    add_asset(client, auth_headers, category="gold", value=500)
    client.get("/api/dashboard", headers=auth_headers)
    backup = client.get("/api/export", headers=auth_headers).json()
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    [restored] = snapshots(client, auth_headers)
    assert restored["assets_by_class"] == {"gold": 500}


def test_a_backup_without_breakdowns_still_restores(client, auth_headers, frozen_today):
    backup = {"snapshots": [{"total_assets": 10, "total_liabilities": 0, "timestamp": "2025-01-01T00:00:00"}]}
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 200
    [restored] = snapshots(client, auth_headers)
    assert "assets_by_class" not in restored or restored["assets_by_class"] is None


@pytest.mark.parametrize("bad", [-1, "inf"])
def test_restore_rejects_bad_breakdown_values(client, auth_headers, frozen_today, bad):
    backup = {"snapshots": [{"total_assets": 10, "total_liabilities": 0, "timestamp": "2025-01-01T00:00:00",
                             "assets_by_class": {"cash": bad}}]}
    resp = client.post("/api/restore", headers=auth_headers,
                       files={"file": ("backup.json", json.dumps(backup).encode(), "application/json")})
    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("snapshots[0].assets_by_class.cash: ")


def test_demo_user_gets_six_months_of_history(client, monkeypatch, frozen_today):
    import asyncio

    import main
    from config import settings

    monkeypatch.setattr(settings, "CREATE_DEMO_DATA", True)
    asyncio.run(main.startup_event())
    history = db.get_snapshots_by_user(db.get_user_by_username("demo")["id"], limit=None)
    assert [s["timestamp"][:7] for s in sorted(history, key=lambda s: s["timestamp"])] == [
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    assert all(s["assets_by_class"] and s["total_assets"] > s["total_liabilities"] for s in history)
```

(9 test functions, one parametrized twice → 10 collected. Suite target: 335 + 10 = 345.)

- [ ] **Step 2: Run; FAIL.**

- [ ] **Step 3: Database** — in `backend/database.py`:

```python
# Breakdown maps a snapshot may carry (newer snapshots); older ones have only the totals
SNAPSHOT_BREAKDOWN = ("assets_by_category", "liabilities_by_category", "assets_by_class")
```

`_new_snapshot_row(user_id, total_assets, total_liabilities, timestamp, breakdown=None)` adds `**{k: breakdown[k] for k in SNAPSHOT_BREAKDOWN if breakdown and breakdown.get(k) is not None}` to the row. `create_snapshot(user_id, total_assets, total_liabilities, breakdown=None, timestamp=None)` passes `breakdown` and `timestamp or get_timestamp()` (call `get_timestamp()` at call time so tests can patch it). In `replace_user_data`, pass each cleaned snapshot as the breakdown (`_new_snapshot_row(..., s["timestamp"], s)`).

- [ ] **Step 4: Models** — `NetWorthSnapshot` gains `assets_by_category: Optional[dict] = None`, `liabilities_by_category: Optional[dict] = None`, `assets_by_class: Optional[dict] = None`. `SnapshotRestore` gains the same three as `Optional[Dict[str, Annotated[float, Field(ge=0, le=1e300)]]] = None` (import `Dict`).

- [ ] **Step 5: Endpoints (`main.py`)** —

```python
def _snapshot_breakdown(totals: dict) -> dict:
    return {key: totals[key] for key in db.SNAPSHOT_BREAKDOWN}


def _ensure_monthly_snapshot(user_id: str, totals: dict, on) -> None:
    """One snapshot per calendar month, saved the first time the dashboard is opened that month
    (a manual snapshot that month counts). Empty accounts are skipped."""
    if not totals["total_assets"] and not totals["total_liabilities"]:
        return
    month = on.isoformat()[:7]
    if any(s["timestamp"].startswith(month) for s in db.get_snapshots_by_user(user_id, limit=None)):
        return
    db.create_snapshot(user_id, totals["total_assets"], totals["total_liabilities"],
                       breakdown=_snapshot_breakdown(totals), timestamp=f"{on.isoformat()}T00:00:00")
```

`get_dashboard` calls `_ensure_monthly_snapshot(user_id, totals, on)` right after computing `totals` (before reading the history). `create_snapshot` passes `breakdown=_snapshot_breakdown(totals)`.

- [ ] **Step 6: Demo history** — in `startup_event`, when the demo user is created (same block as the sample assets), add six synthetic monthly snapshots (first day of each of the six previous months, oldest first) with `db.create_snapshot(..., breakdown=..., timestamp=f"{first_day.isoformat()}T00:00:00")`. Use a gentle upward trend, e.g. total assets from ₹1,62,00,000 rising ₹2,00,000 a month and liabilities from ₹71,00,000 falling ₹60,000 a month, with `assets_by_class` split as real_estate 62%, debt 14%, equity 12%, cash 6%, gold 3%, other 3% of total assets (rounded to rupees), `assets_by_category` `{}` and `liabilities_by_category` `{}`. Mark the block with a comment that it is synthetic demo history. Compute the first days with `valuation.add_months(date(on.year, on.month, 1), -k)`.

- [ ] **Step 7: README** — document allocation by asset class (mapping table summary; NPS and hybrid funds split 50/50), automatic monthly snapshots (first dashboard visit each month; Save Snapshot adds extra points), the month-over-month change and the allocation-history chart.

- [ ] **Step 8:** test file, then full suite — `345 passed`. **Step 9: Commit** — `feat: snapshots keep a breakdown and are taken automatically each month`.

---

### Task 3: Dashboard and report

**Files:** Create `frontend/src/utils/assetClasses.js`; Modify `frontend/src/pages/Dashboard.jsx`, `frontend/src/utils/reportGenerator.js`

- [ ] **Step 1: `assetClasses.js`:**

```js
// Asset classes in display order, with labels and fixed chart colours.
export const ASSET_CLASSES = [
  { key: 'equity', label: 'Equity', color: '#0ea5e9' },
  { key: 'debt', label: 'Debt', color: '#22c55e' },
  { key: 'gold', label: 'Gold', color: '#f59e0b' },
  { key: 'real_estate', label: 'Real Estate', color: '#8b5cf6' },
  { key: 'cash', label: 'Cash', color: '#06b6d4' },
  { key: 'other', label: 'Other', color: '#94a3b8' },
];

export const assetClassLabel = (key) => ASSET_CLASSES.find((c) => c.key === key)?.label ?? key;
```

- [ ] **Step 2: Allocation toggle** — in `Dashboard.jsx`:
  - state `allocationView`, initialised from `localStorage.getItem('allocationView')` inside try/catch, default `'class'`; on change, set state and `localStorage.setItem` inside try/catch.
  - `assetChartData` becomes, for `'class'`: `ASSET_CLASSES.filter((c) => (metrics?.assets_by_class?.[c.key] || 0) > 0).map((c) => ({ name: c.label, value: metrics.assets_by_class[c.key], color: c.color }))`; for `'holding'`: today's data (with `color` from `COLORS[index % COLORS.length]`). The `<Cell>` uses `entry.color`.
  - In the Asset Allocation card header, a two-button segmented control ("By asset class", "By holding") using `text-xs px-2.5 py-1 rounded-md` with the active button `bg-primary-600 text-white` and the other `text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700`.
- [ ] **Step 3: Month-over-month line** — inside the component, after `formatCurrency`:

```js
  // Latest snapshot from an earlier calendar month (history is newest first)
  const thisMonth = todayIso().slice(0, 7);
  const previousSnapshot = (metrics?.net_worth_history || []).find((s) => s.timestamp.slice(0, 7) < thisMonth);
  const netWorthChange = previousSnapshot ? metrics.net_worth - previousSnapshot.net_worth : null;
  const netWorthChangePercent = previousSnapshot && previousSnapshot.net_worth !== 0
    ? (netWorthChange / Math.abs(previousSnapshot.net_worth)) * 100 : null;
```

  Under the Net Worth value render, when `netWorthChange != null`: `<p className={`text-xs mt-1 ${netWorthChange >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>{netWorthChange >= 0 ? '▲' : '▼'} {formatCurrency(Math.abs(netWorthChange))}{netWorthChangePercent != null && <> ({privacyMode ? '••' : `${Math.abs(netWorthChangePercent).toFixed(1)}%`})</>} since {formatMonthYear(previousSnapshot.timestamp.slice(0, 10))}</p>`. Import `todayIso`, `formatMonthYear` from `../utils/dates`.
- [ ] **Step 4: History labels and empty text** — history `date` label: `new Date(snapshot.timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })`. Empty-state second line: "A snapshot is saved automatically the first time you open the dashboard each month; Save Snapshot adds one now."
- [ ] **Step 5: Allocation history** — import `AreaChart, Area` from recharts. Data:

```js
  const allocationHistory = [...(metrics?.net_worth_history || [])].reverse()
    .filter((s) => s.assets_by_class)
    .map((s) => ({
      date: new Date(s.timestamp).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' }),
      ...Object.fromEntries(ASSET_CLASSES.map((c) => [c.key, s.assets_by_class[c.key] || 0])),
    }));
```

  After the Net Worth History card, a card "Allocation History" (icon `Layers` from lucide-react): when `allocationHistory.length >= 2`, a `ResponsiveContainer` (h-72) with an `AreaChart` whose `<Area>` per class uses `type="monotone" dataKey={c.key} name={c.label} stackId="1" stroke={c.color} fill={c.color} fillOpacity={0.6}`, plus `CartesianGrid`, `XAxis dataKey="date"`, the same `YAxis` tick formatter as the history chart, `Tooltip formatter={(value) => formatCurrency(value)}` and `Legend`; otherwise a centred `text-gray-400` line "Allocation history appears once two monthly snapshots have a breakdown."
- [ ] **Step 6: Report** — in `reportGenerator.js` add `buildAllocationSection(metrics, isPrivate)` (import `ASSET_CLASSES` from `./assetClasses`): a section "Asset Allocation" with a table (Class | Value | Share), one row per class present in `metrics.assets_by_class` (value via `fmt(value, isPrivate)`, share `(value / total * 100).toFixed(1) + '%'` where total is the sum of the class values; '—' when total is 0), no-data row "No entries" when empty. Insert it after the goal card in the HTML.
- [ ] **Step 7: Build** — green; re-read every className you touched. **Step 8: Commit** — `feat: allocation by class, month-over-month change and allocation history`.

---

### Task 4: Browser check (controller)

Throwaway backend + Vite (generated SECRET_KEY, temp DATA_FILE, fresh user with a generated password). Add a few holdings across classes; the dashboard shows the class pie by default and the holding pie after toggling (remembered after reload); one automatic snapshot exists after the first visit; restore a backup containing older monthly snapshots with breakdowns → month-over-month line and allocation history appear; privacy masks the change; the report has the allocation table. Then the full suite and stop the servers.
