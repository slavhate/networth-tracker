# Safe Restore and NYSE Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restoring a backup replaces the account's data exactly and safely, NYSE stocks are supported, and US stock values are converted to INR wherever they are totalled.

**Architecture:**
- `backend/restore.py` (new) parses and validates a backup file with the existing Pydantic create models and returns cleaned sections; it never touches storage.
- `database.replace_user_data` swaps one user's rows in a single load/save, reusing row builders pulled out of the existing `create_*` helpers; `save_data` becomes an atomic temp-file-and-rename write.
- `POST /api/restore` wires the two together and replaces `POST /api/import`. The sidebar gets a confirm dialog (`RestoreDialog.jsx`) that shows what will be replaced and downloads the current data first.
- A `USD_MARKETS` set (`NASDAQ`, `NYSE`) replaces every `== "NASDAQ"` check in backend and frontend; the print report converts US holdings to INR.

**Tech Stack:** FastAPI 0.115, Pydantic 2.10, pytest 8.3.4, React 18 + Vite 5 + Tailwind 3. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-safe-restore-nyse-design.md`. Read it before starting any task.

## Global Constraints

- **Branch:** `feat/safe-restore-nyse` (from `main` at `a4b6092`), worktree at `<worktree>` (`/mnt/c/<path-to>/networth-tracker-wt/safe-restore` in WSL).
- **Environment:** Python and Node exist only inside WSL `Ubuntu-24.04`. The backend virtualenv is `~/.venvs/networth-tracker` (has `requirements-dev.txt`). From Git Bash, wrap commands as `MSYS_NO_PATHCONV=1 wsl -d Ubuntu-24.04 -- bash -lc '<command>'`; put anything with nested quotes in a script file.
- **Backend test command:** `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`.
  - `tests/conftest.py` pins `TZ=Asia/Kolkata` automatically.
  - To run one file, replace `tests` with its path; for one test, append `::test_name`.
  - Expected totals: 94 before this work; 96 after Task 1; 101 after Task 2; 109 after Task 3; 127 after Task 4; 135 after Task 5.
- **Frontend build command:** `cd frontend && npm install && npm run build` (no frontend test framework exists).
- **Tests never touch the network.** Any test that creates equities or mutual funds or reads the dashboard uses the `offline_markets` fixture (Task 2), which fixes USD→INR at 80 and makes stock prices and NAVs unavailable.
- **No new dependencies** (backend or frontend).
- **Error contract** (exact strings, from spec §6):
  - 413 `"Backup file too large (max 10MB)"`
  - 400 `"Invalid JSON file"` (not UTF-8, not JSON, or contains `NaN`/`Infinity`/a number too large for a float)
  - 400 `"Backup must be a JSON object"`
  - 400 `"This file doesn't look like a Net Worth Tracker backup"`
  - 400 `"<section> must be a list"`
  - 400 `"<section>[<i>]: must be an object"` / `"goal: must be an object"`
  - 400 `"<section>[<i>].<field>: <pydantic message>"` / `"goal.<field>: <pydantic message>"`
- **Restore response:** `{"status": "success", "restored": {"assets": n, "liabilities": n, "bank_accounts": n, "insurances": n, "mutual_funds": n, "equities": n, "snapshots": n, "goal": bool}}`.
- **Commits:**
  - Commit with the repository's configured no-reply identity.
  - Every message ends with a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Style:** follow existing patterns. Backend uses module-level functions, `db.` helpers and `HTTPException`. Frontend uses Tailwind component classes (`card`, `input`, `label`, `btn-primary`, `btn-secondary`, `btn-danger`) with `dark:` variants.

## Additions to the Spec (found while planning)

These are required for the spec's own guarantees and are called out so the reviewer can check them:

1. **Export includes every snapshot** (Task 3 and Task 5). `GET /api/export` calls `get_snapshots_by_user`, which returns only the 30 most recent. With replace-only restore, restoring your own backup would silently delete older history. Export now passes `limit=None`; the dashboard keeps its 30.
2. **Print report debt-to-asset ratio** (Task 6). The backend already returns a percentage (e.g. `25.5`); the report multiplies it by 100 again and prints `2550.0%`. One-line fix in the file Task 6 already edits.

## Review Focus

1. A backup containing `NaN`, `Infinity` or `1e400`: expect `400 "Invalid JSON file"`, never a stored value that makes every page's JSON unparseable (Task 4 tests it).
2. A user with more than 30 snapshots restores their own backup: expect all snapshots back (Task 3 and Task 5 test it).
3. Restoring the same file twice: expect no duplicates (Task 5 tests it).
4. A file that isn't valid JSON, or is a JSON array: expect the sidebar error "Invalid JSON file" for the first, and the server's "Backup must be a JSON object" shown inside the dialog for the second (Task 8 checks both by hand).
5. The dialog can't load current data (backend stopped): expect "Couldn't load your current data" and a disabled **Replace my data** button (Task 8 checks it by hand).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `backend/database.py` | modify | atomic `save_data`; `_new_*_row` builders; `replace_user_data`; `get_snapshots_by_user(limit=None)` |
| `backend/models.py` | modify | `StockMarket.NYSE`; `USD_MARKETS`; `EquityRestore`; `SnapshotRestore` |
| `backend/restore.py` | create | parse + validate a backup file; `RestoreError`; `LIST_SECTIONS` |
| `backend/stock_service.py` | modify | NYSE symbol mapping |
| `backend/main.py` | modify | `USD_MARKETS` checks; INR equities summary; `POST /api/restore`; remove `/api/import`; export all snapshots |
| `backend/tests/conftest.py` | modify | `offline_markets` fixture |
| `backend/tests/test_atomic_save.py` | create | Task 1 |
| `backend/tests/test_us_markets.py` | create | Task 2 |
| `backend/tests/test_replace_user_data.py` | create | Task 3 |
| `backend/tests/test_restore_parse.py` | create | Task 4 |
| `backend/tests/test_restore_api.py` | create | Task 5 |
| `frontend/src/pages/Equities.jsx` | modify | NYSE option; `isUsdMarket` |
| `frontend/src/utils/reportGenerator.js` | modify | INR conversion for US holdings; ratio fix |
| `frontend/src/utils/download.js` | create | `downloadJson(data, filename)` |
| `frontend/src/components/RestoreDialog.jsx` | create | confirm dialog, pre-restore download, restore call |
| `frontend/src/components/Layout.jsx` | modify | open the dialog; use `downloadJson`; result message |
| `frontend/src/api.js` | modify | `exportAPI.import` → `exportAPI.restore` (`/api/restore`) |
| `README.md` | modify | NYSE (Task 2); restore (Task 5) |

---

### Task 1: Atomic `save_data`

**Files:**
- Modify: `backend/database.py:45-50` (`save_data`)
- Test: `backend/tests/test_atomic_save.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces: `save_data(data: Dict[str, Any]) -> None` — same signature; now writes `<DATA_FILE>.tmp` then `os.replace`s it over `DATA_FILE`; on any exception removes the temp file and re-raises.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_atomic_save.py`:

```python
import json
import os

import pytest


@pytest.fixture
def data_file(tmp_path, monkeypatch):
    from config import settings

    path = tmp_path / "data.json"
    monkeypatch.setattr(settings, "DATA_FILE", str(path))
    return path


def test_save_writes_the_file_and_leaves_no_temp_file(data_file):
    import database as db

    db.save_data({"users": [], "assets": [{"id": "a"}]})

    assert json.loads(data_file.read_text())["assets"] == [{"id": "a"}]
    assert os.listdir(data_file.parent) == ["data.json"]


def test_failed_save_keeps_the_previous_file_and_removes_the_temp_file(data_file):
    import database as db

    db.save_data({"users": [], "assets": []})
    before = data_file.read_text()

    with pytest.raises(TypeError):
        db.save_data({"users": [], "assets": [object()]})  # not JSON-serialisable: json.dump raises mid-write

    assert data_file.read_text() == before
    assert os.listdir(data_file.parent) == ["data.json"]
```

- [ ] **Step 2: Run the tests to verify the second one fails**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests/test_atomic_save.py -q`
Expected: `test_failed_save_keeps_the_previous_file_and_removes_the_temp_file` FAILS (the in-place write truncated `data.json`); the first test passes.

- [ ] **Step 3: Make `save_data` atomic**

In `backend/database.py`, replace the whole `save_data` function with:

```python
def save_data(data: Dict[str, Any]) -> None:
    """Save data to JSON file atomically: write a temp file, then swap it into place"""
    data_file = get_data_file_path()
    os.makedirs(os.path.dirname(data_file), exist_ok=True)
    tmp_file = data_file + ".tmp"
    try:
        with open(tmp_file, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, data_file)
    except BaseException:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        raise
```

- [ ] **Step 4: Run the full suite**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`
Expected: `96 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/tests/test_atomic_save.py
git commit -m "fix: write data.json atomically so a failed save can't corrupt it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: NYSE market and INR conversion for every US market (backend)

**Files:**
- Modify: `backend/models.py:262-265` (`StockMarket`)
- Modify: `backend/stock_service.py:26-37` (`get_yahoo_symbol`)
- Modify: `backend/main.py` — `from models import (...)` block (lines 10-21); dashboard and snapshot equity totals (both `== "NASDAQ"` occurrences); `get_equities_summary`
- Modify: `backend/tests/conftest.py` (add fixture)
- Modify: `README.md`
- Test: `backend/tests/test_us_markets.py` (create)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `models.StockMarket.NYSE` (value `"NYSE"`).
  - `models.USD_MARKETS: frozenset[str]` = `{"NASDAQ", "NYSE"}`.
  - Pytest fixture `offline_markets` (in `conftest.py`): USD→INR fixed at `80.0`; `stock_service.fetch_stock_price` returns `None`; `nav_service.fetch_nav_by_fund_name` returns `None`. Task 5 uses it.

- [ ] **Step 1: Add the `offline_markets` fixture**

Append to `backend/tests/conftest.py`:

```python


@pytest.fixture
def offline_markets(monkeypatch):
    """No network: stock prices and NAVs are unavailable and USD→INR is fixed at 80."""
    import exchange_service
    import nav_service
    import stock_service

    async def fixed_rate():
        return 80.0

    async def no_nav(fund_name):
        return None

    monkeypatch.setattr(exchange_service, "fetch_usd_to_inr", fixed_rate)
    monkeypatch.setattr(nav_service, "fetch_nav_by_fund_name", no_nav)
    monkeypatch.setattr(stock_service, "fetch_stock_price", lambda symbol, market: None)
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_us_markets.py`:

```python
import pytest

import stock_service

pytestmark = pytest.mark.usefixtures("offline_markets")


def add_equity(client, headers, symbol, market, quantity, price):
    resp = client.post("/api/equities", headers=headers, json={
        "symbol": symbol, "market": market, "quantity": quantity, "avg_buy_price": price,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_nyse_symbol_has_no_suffix():
    assert stock_service.get_yahoo_symbol("ko", "NYSE") == "KO"


def test_nyse_equity_can_be_added(client, auth_headers):
    equity = add_equity(client, auth_headers, "KO", "NYSE", 10, 60)

    assert equity["market"] == "NYSE"
    assert equity["current_value"] == 600


def test_dashboard_converts_us_markets_only(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)      # $600 -> ₹48,000
    add_equity(client, auth_headers, "AAPL", "NASDAQ", 1, 100)  # $100 -> ₹8,000
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)     # ₹2,000
    add_equity(client, auth_headers, "INFY", "BSE", 1, 500)     # ₹500

    metrics = client.get("/api/dashboard", headers=auth_headers).json()

    assert metrics["assets_by_category"]["equities"] == 58500
    assert metrics["total_assets"] == 58500


def test_snapshot_converts_us_markets(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)

    snapshot = client.post("/api/snapshot", headers=auth_headers).json()

    assert snapshot["total_assets"] == 50000


def test_equities_summary_converts_us_markets(client, auth_headers):
    add_equity(client, auth_headers, "KO", "NYSE", 10, 60)
    add_equity(client, auth_headers, "TCS", "NSE", 2, 1000)

    summary = client.get("/api/equities-summary", headers=auth_headers).json()

    assert summary["total_invested"] == 50000
    assert summary["total_current_value"] == 50000
    assert summary["total_gain"] == 0
```

- [ ] **Step 3: Run them to verify they fail**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests/test_us_markets.py -q`
Expected: the four API tests FAIL (NYSE is rejected with 422; the summary adds raw USD). `test_nyse_symbol_has_no_suffix` passes already (the fallback branch returns the bare symbol); it pins the behaviour.

- [ ] **Step 4: Add NYSE and `USD_MARKETS` to `models.py`**

Replace the `StockMarket` enum in `backend/models.py` with:

```python
class StockMarket(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"

# US listings are priced in USD and converted to INR wherever values are totalled
USD_MARKETS = frozenset({StockMarket.NASDAQ.value, StockMarket.NYSE.value})
```

- [ ] **Step 5: Map NYSE symbols in `stock_service.py`**

In `get_yahoo_symbol`, replace:

```python
    elif market == "NASDAQ":
        return symbol  # NASDAQ symbols don't need suffix
```

with:

```python
    elif market in ("NASDAQ", "NYSE"):
        return symbol  # US listings don't need a suffix
```

- [ ] **Step 6: Use `USD_MARKETS` in `main.py`**

1. In the `from models import (...)` block, change the last line `    Goal, GoalCreate, GoalUpdate` to:

```python
    Goal, GoalCreate, GoalUpdate,
    USD_MARKETS
```

2. The dashboard (`get_dashboard`) and the snapshot route (`create_snapshot`) contain the same block. In **both**, replace:

```python
    # Convert NASDAQ equities from USD to INR
    total_equities = sum(
        e["current_value"] * usd_to_inr if e.get("market") == "NASDAQ" else e["current_value"] 
        for e in equities
    )
```

(note the trailing space after the first `e["current_value"]`) with:

```python
    # Convert US-market equities from USD to INR
    total_equities = sum(
        e["current_value"] * usd_to_inr if e.get("market") in USD_MARKETS else e["current_value"]
        for e in equities
    )
```

3. Replace the whole `get_equities_summary` route with:

```python
@app.get("/api/equities-summary")
async def get_equities_summary(user_id: str = Depends(get_user_id)):
    """Get equities summary in INR (US-market holdings converted at the live rate)"""
    equities = db.get_equities_by_user(user_id)
    usd_to_inr = await exchange_service.fetch_usd_to_inr()

    def in_inr(equity: dict, amount: float) -> float:
        return amount * usd_to_inr if equity.get("market") in USD_MARKETS else amount

    total_invested = sum(in_inr(e, e["invested_amount"]) for e in equities)
    total_current = sum(in_inr(e, e["current_value"]) for e in equities)
    total_gain = total_current - total_invested
    return {
        "total_invested": total_invested,
        "total_current_value": total_current,
        "total_gain": total_gain,
        "gain_percent": (total_gain / total_invested * 100) if total_invested > 0 else 0,
        "holding_count": len(equities)
    }
```

- [ ] **Step 7: Run the full suite**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`
Expected: `101 passed`.

- [ ] **Step 8: Update the README for NYSE**

In `README.md` make these replacements (exact text):
- `  - Live price fetching from NSE, BSE, and NASDAQ via Yahoo Finance` → `  - Live price fetching from NSE, BSE, NASDAQ and NYSE via Yahoo Finance`
- `  - USD to INR conversion for NASDAQ stocks` → `  - USD to INR conversion for US (NASDAQ and NYSE) stocks`
- `- **USD Support** - For NASDAQ-listed stocks` → `- **USD Support** - For US-listed (NASDAQ and NYSE) stocks`
- `For US stocks (NASDAQ), the value is automatically converted` → `For US stocks (NASDAQ and NYSE), the value is automatically converted`
- `  - Yahoo Finance - Live stock prices (NSE, BSE, NASDAQ)` → `  - Yahoo Finance - Live stock prices (NSE, BSE, NASDAQ, NYSE)`
- In the "Stock Market Integration" table, after the `| NASDAQ (US) | ...` row add: `| NYSE (US) | \`SYMBOL\` | USD | KO |`

- [ ] **Step 9: Commit**

```bash
git add backend/models.py backend/stock_service.py backend/main.py backend/tests/conftest.py backend/tests/test_us_markets.py README.md
git commit -m "feat: support NYSE stocks and convert every US market to INR

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Row builders and `replace_user_data` (database)

**Files:**
- Modify: `backend/database.py` — `create_asset`, `create_liability`, `get_snapshots_by_user`, `create_snapshot`, `create_bank_account`, `create_insurance`, `create_mutual_fund`, `create_equity`, `create_or_update_goal`; add `_new_row`, `_new_equity_row`, `_new_snapshot_row`, `_new_goal_row`, `replace_user_data`
- Test: `backend/tests/test_replace_user_data.py` (create)

**Interfaces:**
- Consumes: atomic `save_data` (Task 1).
- Produces:
  - `replace_user_data(user_id: str, cleaned: Dict) -> None`. `cleaned` has keys `assets`, `liabilities`, `bank_accounts`, `insurances`, `mutual_funds`, `equities`, `snapshots` (lists of plain dicts) and `goal` (dict or `None`) — exactly what `restore.parse_backup` (Task 4) returns. Snapshot dicts have `total_assets`, `total_liabilities`, `timestamp`. Equity dicts may have `current_price: None`.
  - `get_snapshots_by_user(user_id: str, limit: Optional[int] = 30) -> List[Dict]`; `limit=None` returns all, newest first. Task 5 uses it in export.

- [ ] **Step 1: Write characterization tests for the existing create helpers, plus the failing new tests**

Create `backend/tests/test_replace_user_data.py`:

```python
import pytest

import database as db

EMPTY = {
    "assets": [], "liabilities": [], "bank_accounts": [], "insurances": [],
    "mutual_funds": [], "equities": [], "snapshots": [], "goal": None,
}


@pytest.fixture(autouse=True)
def data_file(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "DATA_FILE", str(tmp_path / "data.json"))


def backup(**sections):
    return {**EMPTY, **sections}


def test_create_helpers_still_build_the_same_rows():
    asset = db.create_asset("me", {"name": "Cash", "value": 5, "category": "cash", "description": None})
    assert asset["user_id"] == "me" and asset["value"] == 5 and len(asset["id"]) == 36

    equity = db.create_equity("me", {"symbol": "infy", "market": "NSE", "quantity": 4, "avg_buy_price": 10.0})
    assert equity["symbol"] == "INFY"
    assert equity["current_price"] == 10.0
    assert equity["invested_amount"] == 40.0 and equity["gain_loss"] == 0

    snapshot = db.create_snapshot("me", 10, 4)
    assert snapshot["net_worth"] == 6

    goal = db.create_or_update_goal("me", {})
    assert goal["target_amount"] == 100000000 and goal["name"] == "Net Worth Goal"


def test_replaces_only_this_users_rows():
    db.create_asset("me", {"name": "Old car", "value": 1, "category": "vehicles", "description": None})
    db.create_asset("other", {"name": "Their flat", "value": 2, "category": "real_estate", "description": None})
    db.create_snapshot("me", 10, 5)
    db.create_or_update_goal("me", {"target_amount": 5})
    db.create_or_update_goal("other", {"target_amount": 7})

    db.replace_user_data("me", backup(assets=[
        {"name": "New flat", "value": 3, "category": "real_estate", "description": None},
    ]))

    assert [a["name"] for a in db.get_assets_by_user("me")] == ["New flat"]
    assert [a["name"] for a in db.get_assets_by_user("other")] == ["Their flat"]
    assert db.get_snapshots_by_user("me") == []
    assert db.get_goal_by_user("me") is None
    assert db.get_goal_by_user("other")["target_amount"] == 7


def test_rows_get_a_fresh_id_and_this_user():
    db.replace_user_data("me", backup(liabilities=[
        {"name": "Loan", "amount": 100, "category": "mortgage", "interest_rate": 8.5, "description": None},
    ]))

    [row] = db.get_liabilities_by_user("me")
    assert row["user_id"] == "me"
    assert len(row["id"]) == 36
    assert row["created_at"] == row["updated_at"]


def test_snapshots_keep_their_timestamp_and_recompute_net_worth():
    db.replace_user_data("me", backup(snapshots=[
        {"total_assets": 100.0, "total_liabilities": 30.0, "timestamp": "2025-01-31T10:00:00"},
    ]))

    [snapshot] = db.get_snapshots_by_user("me")
    assert snapshot["timestamp"] == "2025-01-31T10:00:00"
    assert snapshot["net_worth"] == 70.0


def test_equity_values_are_recomputed_and_a_null_price_uses_the_average():
    db.replace_user_data("me", backup(equities=[
        {"symbol": "tcs", "company_name": None, "market": "NSE", "quantity": 2,
         "avg_buy_price": 100.0, "current_price": 150.0, "notes": None},
        {"symbol": "KO", "company_name": None, "market": "NYSE", "quantity": 3,
         "avg_buy_price": 50.0, "current_price": None, "notes": None},
    ]))

    by_symbol = {e["symbol"]: e for e in db.get_equities_by_user("me")}
    assert by_symbol["TCS"]["current_value"] == 300.0
    assert by_symbol["TCS"]["gain_loss"] == 100.0
    assert by_symbol["KO"]["current_price"] == 50.0
    assert by_symbol["KO"]["current_value"] == 150.0


def test_goal_is_restored():
    db.replace_user_data("me", backup(goal={"target_amount": 100000000.0, "name": "10 Cr"}))

    assert db.get_goal_by_user("me")["name"] == "10 Cr"


def test_replace_saves_exactly_once(monkeypatch):
    saves = []
    real_save = db.save_data
    monkeypatch.setattr(db, "save_data", lambda data: (saves.append(1), real_save(data)))

    db.replace_user_data("me", backup(
        assets=[{"name": "A", "value": 1, "category": "cash", "description": None}],
        snapshots=[{"total_assets": 1.0, "total_liabilities": 0.0, "timestamp": "2025-01-01T00:00:00"}],
    ))

    assert len(saves) == 1


def test_snapshot_limit_none_returns_every_snapshot_newest_first():
    for day in range(1, 36):
        db.create_snapshot("me", day, 0)

    assert len(db.get_snapshots_by_user("me")) == 30
    every = db.get_snapshots_by_user("me", limit=None)
    assert len(every) == 35
    assert every[0]["timestamp"] >= every[-1]["timestamp"]
```

- [ ] **Step 2: Run them to verify the new ones fail**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests/test_replace_user_data.py -q`
Expected: the six `replace_user_data` tests FAIL with `AttributeError: module 'database' has no attribute 'replace_user_data'`. `test_create_helpers_still_build_the_same_rows` and `test_snapshot_limit_none_returns_every_snapshot_newest_first` already pass (`snapshots[:None]` returns everything); they pin behaviour the refactor must keep and Task 5 relies on.

- [ ] **Step 3: Add the row builders**

In `backend/database.py`, directly after `get_timestamp()`, add:

```python
# Row builders shared by the create_* helpers and replace_user_data
def _new_row(user_id: str, fields: Dict) -> Dict:
    now = get_timestamp()
    return {"id": generate_id(), "user_id": user_id, **fields, "created_at": now, "updated_at": now}

def _new_equity_row(user_id: str, equity_data: Dict) -> Dict:
    quantity = equity_data["quantity"]
    avg_price = equity_data["avg_buy_price"]
    current_price = equity_data.get("current_price")
    if current_price is None:
        current_price = avg_price
    invested = quantity * avg_price
    current_value = quantity * current_price
    gain_loss = current_value - invested
    return _new_row(user_id, {
        "symbol": equity_data["symbol"].upper(),
        "company_name": equity_data.get("company_name"),
        "market": equity_data["market"],
        "quantity": quantity,
        "avg_buy_price": avg_price,
        "current_price": current_price,
        "invested_amount": invested,
        "current_value": current_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": (gain_loss / invested * 100) if invested > 0 else 0,
        "notes": equity_data.get("notes"),
    })

def _new_snapshot_row(user_id: str, total_assets: float, total_liabilities: float, timestamp: str) -> Dict:
    return {
        "id": generate_id(),
        "user_id": user_id,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "timestamp": timestamp,
    }

def _new_goal_row(user_id: str, goal_data: Dict) -> Dict:
    return _new_row(user_id, {
        "target_amount": goal_data.get("target_amount", 100000000),  # Default 10 crore
        "name": goal_data.get("name", "Net Worth Goal"),
    })
```

- [ ] **Step 4: Make the create helpers use them**

In `backend/database.py`:

1. `create_asset`: replace the `asset = {...}` literal with `asset = _new_row(user_id, asset_data)`.
2. `create_liability`: replace the `liability = {...}` literal with `liability = _new_row(user_id, liability_data)`.
3. `create_bank_account`: replace the `account = {...}` literal with `account = _new_row(user_id, account_data)`.
4. `create_insurance`: replace the `insurance = {...}` literal with `insurance = _new_row(user_id, insurance_data)`.
5. `create_mutual_fund`: replace the `fund = {...}` literal with `fund = _new_row(user_id, fund_data)`.
6. `create_snapshot`: replace the `snapshot = {...}` literal with `snapshot = _new_snapshot_row(user_id, total_assets, total_liabilities, get_timestamp())`.
7. `create_equity`: replace the whole body with:

```python
def create_equity(user_id: str, equity_data: Dict) -> Dict:
    data = load_data()
    equity = _new_equity_row(user_id, equity_data)
    data["equities"].append(equity)
    save_data(data)
    return equity
```

8. `create_or_update_goal`: replace the `goal = {...}` literal in the "Create new goal" branch with `goal = _new_goal_row(user_id, goal_data)`.

- [ ] **Step 5: Allow `limit=None` in `get_snapshots_by_user`**

Replace the function with:

```python
def get_snapshots_by_user(user_id: str, limit: Optional[int] = 30) -> List[Dict]:
    """Newest first; limit=None returns every snapshot"""
    data = load_data()
    snapshots = [s for s in data["snapshots"] if s["user_id"] == user_id]
    snapshots.sort(key=lambda x: x["timestamp"], reverse=True)
    return snapshots if limit is None else snapshots[:limit]
```

- [ ] **Step 6: Add `replace_user_data`**

Add at the end of `backend/database.py`:

```python
# Restore
def replace_user_data(user_id: str, cleaned: Dict) -> None:
    """Replace all of a user's financial data (items, snapshots, goal) with `cleaned`, in a single save"""
    data = load_data()
    for collection in ("assets", "liabilities", "bank_accounts", "insurances",
                       "mutual_funds", "equities", "snapshots", "goals"):
        data[collection] = [row for row in data[collection] if row["user_id"] != user_id]

    for collection in ("assets", "liabilities", "bank_accounts", "insurances", "mutual_funds"):
        data[collection].extend(_new_row(user_id, item) for item in cleaned[collection])
    data["equities"].extend(_new_equity_row(user_id, item) for item in cleaned["equities"])
    data["snapshots"].extend(
        _new_snapshot_row(user_id, s["total_assets"], s["total_liabilities"], s["timestamp"])
        for s in cleaned["snapshots"]
    )
    if cleaned["goal"] is not None:
        data["goals"].append(_new_goal_row(user_id, cleaned["goal"]))
    save_data(data)
```

- [ ] **Step 7: Run the full suite**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`
Expected: `109 passed`.

- [ ] **Step 8: Commit**

```bash
git add backend/database.py backend/tests/test_replace_user_data.py
git commit -m "feat: add replace_user_data for restore and share row builders

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Parse and validate a backup (`restore.py`)

**Files:**
- Create: `backend/restore.py`
- Modify: `backend/models.py` — add `EquityRestore` after `EquityUpdate`, `SnapshotRestore` after `NetWorthSnapshot`; add `field_validator` to the pydantic import
- Test: `backend/tests/test_restore_parse.py` (create)

**Interfaces:**
- Consumes: `AssetCreate`, `LiabilityCreate`, `BankAccountCreate`, `InsuranceCreate`, `MutualFundCreate`, `EquityCreate`, `GoalCreate` from `models.py` (existing).
- Produces:
  - `models.EquityRestore(EquityCreate)` with `current_price: Optional[float] = Field(None, ge=0)`.
  - `models.SnapshotRestore` with `total_assets: float`, `total_liabilities: float`, `timestamp: str` (must parse with `datetime.fromisoformat`).
  - `restore.RestoreError(Exception)` with attributes `status_code: int`, `detail: str`.
  - `restore.LIST_SECTIONS: Dict[str, Type[BaseModel]]` — ordered keys `assets`, `liabilities`, `bank_accounts`, `insurances`, `mutual_funds`, `equities`, `snapshots`.
  - `restore.parse_backup(raw: bytes) -> Dict[str, Any]` — returns every `LIST_SECTIONS` key (list of dicts) plus `goal` (dict or `None`); raises `RestoreError`. This is the input of `db.replace_user_data` (Task 3).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_restore_parse.py`:

```python
import json

import pytest

from restore import RestoreError, parse_backup

ASSET = {"name": "Flat", "value": 100, "category": "real_estate"}


def raw(obj):
    return json.dumps(obj).encode("utf-8")


def error_of(data: bytes):
    with pytest.raises(RestoreError) as exc:
        parse_backup(data)
    return exc.value.status_code, exc.value.detail


def test_missing_sections_are_empty_and_goal_is_none():
    cleaned = parse_backup(raw({"assets": [ASSET]}))

    assert cleaned["assets"] == [{"name": "Flat", "value": 100.0, "category": "real_estate", "description": None}]
    for section in ("liabilities", "bank_accounts", "insurances", "mutual_funds", "equities", "snapshots"):
        assert cleaned[section] == []
    assert cleaned["goal"] is None


def test_unknown_and_server_assigned_fields_are_dropped():
    item = {**ASSET, "id": "x", "user_id": "someone", "created_at": "t", "updated_at": "t", "hacked": True}

    [asset] = parse_backup(raw({"assets": [item]}))["assets"]

    assert set(asset) == {"name", "value", "category", "description"}


def test_equity_keeps_current_price_and_market_is_a_plain_string():
    equity = {"symbol": "KO", "market": "NYSE", "quantity": 3, "avg_buy_price": 50,
              "current_price": 61.5, "gain_loss": 999}

    [cleaned] = parse_backup(raw({"equities": [equity]}))["equities"]

    assert cleaned["current_price"] == 61.5
    assert cleaned["market"] == "NYSE"
    assert "gain_loss" not in cleaned


def test_goal_is_cleaned():
    cleaned = parse_backup(raw({"goal": {"target_amount": 5, "id": "g", "user_id": "u"}}))

    assert cleaned["goal"] == {"target_amount": 5.0, "name": "Net Worth Goal"}


def test_snapshot_needs_an_iso_timestamp():
    code, detail = error_of(raw({"snapshots": [
        {"total_assets": 1, "total_liabilities": 0, "timestamp": "last tuesday"},
    ]}))

    assert code == 400
    assert detail.startswith("snapshots[0].timestamp: ")


@pytest.mark.parametrize("data, expected", [
    (b"\xff\xfe not utf8", "Invalid JSON file"),
    (b"{not json", "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": NaN, "category": "cash"}]}', "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": Infinity, "category": "cash"}]}', "Invalid JSON file"),
    (b'{"assets": [{"name": "x", "value": 1e400, "category": "cash"}]}', "Invalid JSON file"),
    (b"[]", "Backup must be a JSON object"),
    (b'{"export_date": "2026-01-01"}', "This file doesn't look like a Net Worth Tracker backup"),
    (b'{"assets": {}}', "assets must be a list"),
    (b'{"assets": [5]}', "assets[0]: must be an object"),
    (b'{"goal": 5}', "goal: must be an object"),
])
def test_bad_files_are_rejected_with_a_clear_message(data, expected):
    assert error_of(data) == (400, expected)


def test_invalid_item_names_its_section_index_and_field():
    bad = {**ASSET, "value": "lots"}

    code, detail = error_of(raw({"assets": [ASSET, ASSET, ASSET, bad]}))

    assert code == 400
    assert detail.startswith("assets[3].value: Input should be a valid number")


def test_invalid_goal_names_its_field():
    code, detail = error_of(raw({"goal": {"target_amount": -5}}))

    assert code == 400
    assert detail.startswith("goal.target_amount: ")


def test_file_over_10mb_is_413():
    assert error_of(b" " * (10 * 1024 * 1024 + 1)) == (413, "Backup file too large (max 10MB)")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests/test_restore_parse.py -q`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'restore'`.

- [ ] **Step 3: Add the restore models**

In `backend/models.py`:

1. Change the first line `from pydantic import BaseModel, Field` to `from pydantic import BaseModel, Field, field_validator`.
2. Directly after the `NetWorthSnapshot` class, add:

```python
class SnapshotRestore(BaseModel):
    """A snapshot as stored in a backup file"""
    total_assets: float
    total_liabilities: float
    timestamp: str

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_iso(cls, value: str) -> str:
        datetime.fromisoformat(value)  # raises ValueError for anything that isn't an ISO date-time
        return value
```

3. Directly after the `EquityUpdate` class, add:

```python
class EquityRestore(EquityCreate):
    """An equity as stored in a backup file: the create fields plus the last known price"""
    current_price: Optional[float] = Field(None, ge=0)
```

- [ ] **Step 4: Create `backend/restore.py`**

```python
"""Parse and validate a backup file for restore. Nothing here touches storage."""
import json
import math
from typing import Any, Dict, Type

from pydantic import BaseModel, ValidationError

from models import (
    AssetCreate, LiabilityCreate, BankAccountCreate, InsuranceCreate,
    MutualFundCreate, EquityRestore, SnapshotRestore, GoalCreate,
)

MAX_BACKUP_BYTES = 10 * 1024 * 1024

# Backup sections holding a list of items, and the model each item must satisfy
LIST_SECTIONS: Dict[str, Type[BaseModel]] = {
    "assets": AssetCreate,
    "liabilities": LiabilityCreate,
    "bank_accounts": BankAccountCreate,
    "insurances": InsuranceCreate,
    "mutual_funds": MutualFundCreate,
    "equities": EquityRestore,
    "snapshots": SnapshotRestore,
}


class RestoreError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"{text} is too large")
    return value


def _reject_constant(name: str):
    raise ValueError(f"{name} is not valid JSON")


def _clean(model: Type[BaseModel], item: Any, where: str) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise RestoreError(400, f"{where}: must be an object")
    try:
        return model.model_validate(item).model_dump(mode="json")
    except ValidationError as e:
        first = e.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        raise RestoreError(400, f"{where}.{field}: {first['msg']}" if field else f"{where}: {first['msg']}")


def parse_backup(raw: bytes) -> Dict[str, Any]:
    """Return every LIST_SECTIONS key (list of clean dicts) plus "goal" (clean dict or None).

    Raises RestoreError on the first problem, so the caller can reject the file before writing anything.
    """
    if len(raw) > MAX_BACKUP_BYTES:
        raise RestoreError(413, "Backup file too large (max 10MB)")
    try:
        backup = json.loads(raw.decode("utf-8"), parse_float=_finite_float, parse_constant=_reject_constant)
    except ValueError:  # covers UnicodeDecodeError and json.JSONDecodeError
        raise RestoreError(400, "Invalid JSON file")
    if not isinstance(backup, dict):
        raise RestoreError(400, "Backup must be a JSON object")
    if not any(key in backup for key in (*LIST_SECTIONS, "goal")):
        raise RestoreError(400, "This file doesn't look like a Net Worth Tracker backup")

    cleaned: Dict[str, Any] = {}
    for section, model in LIST_SECTIONS.items():
        items = backup.get(section, [])
        if not isinstance(items, list):
            raise RestoreError(400, f"{section} must be a list")
        cleaned[section] = [_clean(model, item, f"{section}[{i}]") for i, item in enumerate(items)]

    goal = backup.get("goal")
    cleaned["goal"] = None if goal is None else _clean(GoalCreate, goal, "goal")
    return cleaned
```

- [ ] **Step 5: Run the full suite**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`
Expected: `127 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/restore.py backend/models.py backend/tests/test_restore_parse.py
git commit -m "feat: validate backup files before restore

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `POST /api/restore` endpoint

**Files:**
- Modify: `backend/main.py` — imports; `export_user_data` (snapshots line); delete `import_user_data` (the whole `@app.post("/api/import")` route); add `restore_user_data`
- Modify: `README.md`
- Test: `backend/tests/test_restore_api.py` (create)

**Interfaces:**
- Consumes: `restore.parse_backup`, `restore.RestoreError`, `restore.LIST_SECTIONS` (Task 4); `db.replace_user_data`, `db.get_snapshots_by_user(..., limit=None)` (Task 3); `offline_markets` fixture (Task 2).
- Produces: `POST /api/restore` (multipart field `file`, auth required) → the restore response in Global Constraints. Task 7's frontend calls it.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_restore_api.py`:

```python
import json

import pytest

import database as db

pytestmark = pytest.mark.usefixtures("offline_markets")

CONTENT_SECTIONS = ("assets", "liabilities", "bank_accounts", "insurances", "mutual_funds", "equities", "snapshots")
SERVER_FIELDS = {"id", "user_id", "created_at", "updated_at"}


def restore(client, headers, backup):
    body = backup if isinstance(backup, bytes) else json.dumps(backup).encode("utf-8")
    return client.post("/api/restore", headers=headers, files={"file": ("backup.json", body, "application/json")})


def export(client, headers):
    resp = client.get("/api/export", headers=headers)
    assert resp.status_code == 200
    return resp.json()


def content(backup):
    """Section contents without server-assigned fields, in a stable order, for comparing two exports."""
    def strip(row):
        return {k: v for k, v in row.items() if k not in SERVER_FIELDS}

    out = {section: sorted((strip(r) for r in backup[section]), key=json.dumps) for section in CONTENT_SECTIONS}
    out["goal"] = strip(backup["goal"]) if backup["goal"] else None
    return out


def seed(client, headers):
    for path, body in [
        ("/api/assets", {"name": "Flat", "value": 5000000, "category": "real_estate"}),
        ("/api/liabilities", {"name": "Home loan", "amount": 2000000, "category": "mortgage", "interest_rate": 8.5}),
        ("/api/bank-accounts", {"bank_name": "HDFC", "account_number": "12345678", "account_type": "savings", "balance": 50000}),
        ("/api/insurances", {"policy_name": "Term", "provider": "HDFC Life", "insurance_type": "term",
                             "sum_assured": 10000000, "premium": 12000}),
        ("/api/mutual-funds", {"fund_name": "Index", "amc": "UTI", "category": "index", "invested_amount": 80000,
                               "units": 650, "current_nav": 141.5}),
        ("/api/equities", {"symbol": "KO", "market": "NYSE", "quantity": 10, "avg_buy_price": 60}),
        ("/api/snapshot", None),
        ("/api/goal", {"target_amount": 100000000, "name": "10 Cr"}),
    ]:
        resp = client.post(path, headers=headers, json=body)
        assert resp.status_code in (200, 201), (path, resp.text)


def login_as_other(client):
    client.post("/api/auth/register", json={"username": "other", "password": PASSWORD, "email": "o@example.com"})
    token = client.post("/api/auth/login", data={"username": "other", "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_restoring_your_own_export_round_trips(client, auth_headers):
    seed(client, auth_headers)
    before = export(client, auth_headers)

    resp = restore(client, auth_headers, before)

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "success", "restored": {
        "assets": 1, "liabilities": 1, "bank_accounts": 1, "insurances": 1,
        "mutual_funds": 1, "equities": 1, "snapshots": 1, "goal": True,
    }}
    after = export(client, auth_headers)
    assert content(after) == content(before)
    assert {a["id"] for a in after["assets"]}.isdisjoint({a["id"] for a in before["assets"]})


def test_restoring_twice_does_not_duplicate(client, auth_headers):
    seed(client, auth_headers)
    backup = export(client, auth_headers)

    restore(client, auth_headers, backup)
    restore(client, auth_headers, backup)

    after = export(client, auth_headers)
    assert len(after["assets"]) == 1
    assert len(after["snapshots"]) == 1


def test_export_and_restore_keep_more_than_30_snapshots(client, auth_headers):
    user_id = db.get_user_by_username("tester")["id"]
    for day in range(1, 36):
        db.create_snapshot(user_id, day, 0)
    backup = export(client, auth_headers)
    assert len(backup["snapshots"]) == 35

    restore(client, auth_headers, backup)

    assert len(export(client, auth_headers)["snapshots"]) == 35


def test_goal_null_removes_the_goal(client, auth_headers):
    seed(client, auth_headers)

    resp = restore(client, auth_headers, {"assets": [], "goal": None})

    assert resp.status_code == 200
    assert export(client, auth_headers)["goal"] is None


def test_restore_leaves_other_users_alone(client, auth_headers):
    other = login_as_other(client)
    seed(client, other)
    before = export(client, other)

    restore(client, auth_headers, {"assets": []})

    assert content(export(client, other)) == content(before)


def test_rejected_backup_changes_nothing(client, auth_headers):
    seed(client, auth_headers)
    before = export(client, auth_headers)

    resp = restore(client, auth_headers, {"assets": [
        {"name": "ok", "value": 1, "category": "cash"},
        {"name": "bad", "value": "lots", "category": "cash"},
    ]})

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("assets[1].value: ")
    assert content(export(client, auth_headers)) == content(before)


def test_restore_requires_login(client):
    assert restore(client, {}, {"assets": []}).status_code == 401


def test_old_import_endpoint_is_gone(client, auth_headers):
    resp = client.post("/api/import", headers=auth_headers, files={"file": ("b.json", b"{}", "application/json")})

    assert resp.status_code in (404, 405)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests/test_restore_api.py -q`
Expected: every test except `test_restore_requires_login` FAILS (`/api/restore` is 404 or 405; `/api/import` still exists; export returns only 30 snapshots). `test_restore_requires_login` may fail with 404/405 too, since the route does not exist yet.

- [ ] **Step 3: Wire the endpoint in `main.py`**

1. Below `import nav_service` add `import restore`.
2. Delete `import json` (line 7); after removing the import route it has no other user. Confirm with `grep -n "json\." backend/main.py` → no output.
3. In `export_user_data`, change `"snapshots": db.get_snapshots_by_user(user_id),` to `"snapshots": db.get_snapshots_by_user(user_id, limit=None),`.
4. Delete the whole `@app.post("/api/import")` route (`import_user_data`, from the decorator through its final `return {...}`).
5. In its place, add:

```python
@app.post("/api/restore")
async def restore_user_data(file: UploadFile = File(...), user_id: str = Depends(get_user_id)):
    """Replace all of the current user's data with a backup file. Nothing is written unless the whole file is valid."""
    try:
        cleaned = restore.parse_backup(await file.read())
    except restore.RestoreError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    db.replace_user_data(user_id, cleaned)
    counts = {section: len(cleaned[section]) for section in restore.LIST_SECTIONS}
    return {"status": "success", "restored": {**counts, "goal": cleaned["goal"] is not None}}
```

- [ ] **Step 4: Run the full suite**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q`
Expected: `135 passed`.

- [ ] **Step 5: Update the README for restore**

In `README.md`:
- Replace `- **Data Export/Backup** - Download all your financial data as JSON for backup purposes` with `- **Backup & Restore** - Download all your financial data as JSON. Restore replaces everything in your account with a backup, after showing what will change and offering to download your current data first. The whole file is validated before anything is written.`
- In the "Dashboard & Goals" API table, after the `| GET | \`/api/export\` | Export all user data as JSON backup |` row add: `| POST | \`/api/restore\` | Replace all your data with a backup file (multipart field \`file\`) |`
- Replace `- Import payload size limit (10MB)` with `- Restore upload size limit (10MB); every item is validated before anything is written`

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_restore_api.py README.md
git commit -m "feat: replace /api/import with a validated, replace-only /api/restore

Export now includes every snapshot so a restore keeps the full history.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: NYSE and INR totals in the frontend (Equities page, print report)

**Files:**
- Modify: `frontend/src/pages/Equities.jsx` (lines 16-46, 190-202)
- Modify: `frontend/src/utils/reportGenerator.js` (imports; formatters; `buildSummaryCards`; `buildEquitiesSection`; `generateReport`)

**Interfaces:**
- Consumes: market value `"NYSE"` (Task 2); `exchangeAPI.getRate()` → `{ data: { usd_to_inr: number } }` (existing).
- Produces: nothing other tasks use.

- [ ] **Step 1: Equities page**

In `frontend/src/pages/Equities.jsx`:

1. In `MARKETS`, after the NASDAQ entry add:

```js
  { value: 'NYSE', label: 'NYSE (US)', color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400' },
```

2. After `const DEFAULT_USD_TO_INR = 83.5;` add:

```js

// US listings are priced in USD and converted to INR for totals
const USD_MARKETS = ['NASDAQ', 'NYSE'];
const isUsdMarket = (market) => USD_MARKETS.includes(market);
```

3. In `formatCurrencyRaw`, change `if (market === 'NASDAQ') {` to `if (isUsdMarket(market)) {`.
4. In `formatCurrency`, change `if (privacyMode) return market === 'NASDAQ' ? '$ ••••••' : '₹ ••••••';` to `if (privacyMode) return isUsdMarket(market) ? '$ ••••••' : '₹ ••••••';`.
5. Replace the totals block:

```js
  // Calculate totals in INR (convert NASDAQ USD to INR)
  const totalInvestedINR = equities.reduce((sum, e) => {
    const amount = e.market === 'NASDAQ' ? e.invested_amount * usdToInr : e.invested_amount;
    return sum + amount;
  }, 0);
  const totalCurrentValueINR = equities.reduce((sum, e) => {
    const amount = e.market === 'NASDAQ' ? e.current_value * usdToInr : e.current_value;
    return sum + amount;
  }, 0);
```

with:

```js
  // Calculate totals in INR (convert US-market USD to INR)
  const totalInvestedINR = equities.reduce((sum, e) => {
    const amount = isUsdMarket(e.market) ? e.invested_amount * usdToInr : e.invested_amount;
    return sum + amount;
  }, 0);
  const totalCurrentValueINR = equities.reduce((sum, e) => {
    const amount = isUsdMarket(e.market) ? e.current_value * usdToInr : e.current_value;
    return sum + amount;
  }, 0);
```

6. Check nothing else hard-codes it: `grep -n "'NASDAQ'" frontend/src/pages/Equities.jsx` → only the `MARKETS` entry and `USD_MARKETS`.

- [ ] **Step 2: Print report**

In `frontend/src/utils/reportGenerator.js`:

1. Add `exchangeAPI,` after `goalAPI,` in the import list at the top.
2. After `const MASK = '₹ ••••••';` add:

```js
const USD_MASK = '$ ••••••';
const DEFAULT_USD_TO_INR = 83.5; // same fallback as the Equities page
const USD_MARKETS = ['NASDAQ', 'NYSE'];
```

3. After the `fmt` function add:

```js
function fmtUsd(value, isPrivate) {
  if (isPrivate) return USD_MASK;
  if (value == null || isNaN(value)) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}
```

4. In `buildSummaryCards`, the backend's ratio is already a percentage. Change `? (metrics.debt_to_asset_ratio * 100).toFixed(1) + '%'` to `? metrics.debt_to_asset_ratio.toFixed(1) + '%'`.
5. Replace the whole `buildEquitiesSection` function with:

```js
function buildEquitiesSection(equities, usdToInr, isPrivate) {
  const isUsd = (e) => USD_MARKETS.includes(e.market);
  const valueInInr = (e) => (isUsd(e) ? (Number(e.current_value) || 0) * usdToInr : Number(e.current_value) || 0);
  const rows = equities.length === 0
    ? `<tr class="no-data"><td colspan="6">No entries</td></tr>`
    : equities.map((e) => `
        <tr>
          <td>
            <strong>${escapeHtml(e.symbol)}</strong>
            ${e.company_name ? `<br><small style="color:#64748b;font-size:11px">${escapeHtml(e.company_name)}</small>` : ''}
          </td>
          <td>${escapeHtml(e.market)}</td>
          <td class="num">${e.quantity}</td>
          <td class="num">${fmtNum(e.avg_buy_price)}</td>
          <td class="num">${e.current_price != null ? fmtNum(e.current_price) : '—'}</td>
          <td class="num">
            ${fmt(valueInInr(e), isPrivate)}
            ${isUsd(e) ? `<br><small style="color:#64748b;font-size:11px">${fmtUsd(e.current_value, isPrivate)}</small>` : ''}
          </td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="5">Total Value</td>
          <td class="num">${fmt(equities.reduce((acc, e) => acc + valueInInr(e), 0), isPrivate)}</td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Equities</div>
      <table>
        <thead><tr><th>Symbol</th><th>Market</th><th class="num">Qty</th><th class="num">Avg Buy Price</th><th class="num">Current Price</th><th class="num">Current Value</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}
```

6. In `generateReport`:
   - In the destructuring list, add `rateRes,` after `goalRes,`.
   - In the `Promise.all([...])` array, after the `goalAPI.get()...` line add:

```js
    exchangeAPI.getRate().catch(() => ({ data: null })), // fall back to the default rate
```

   - After `const goal = goalRes.data;` add `const usdToInr = rateRes.data?.usd_to_inr || DEFAULT_USD_TO_INR;`
   - Change `${buildEquitiesSection(equities, isPrivate)}` to `${buildEquitiesSection(equities, usdToInr, isPrivate)}`.

- [ ] **Step 3: Build**

Run: `cd frontend && npm install && npm run build`
Expected: `✓ built in …` with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Equities.jsx frontend/src/utils/reportGenerator.js
git commit -m "feat: NYSE in the Equities page; report converts US holdings to INR

Also fixes the report's debt-to-asset ratio, which multiplied an
already-percent value by 100.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Restore confirm dialog (frontend)

**Files:**
- Create: `frontend/src/utils/download.js`
- Create: `frontend/src/components/RestoreDialog.jsx`
- Modify: `frontend/src/api.js` (the `exportAPI` object)
- Modify: `frontend/src/components/Layout.jsx` (imports; state; `handleExport`; `handleFileChange`; result message; Restore button; render the dialog)

**Interfaces:**
- Consumes: `POST /api/restore` (Task 5); `GET /api/export` (existing).
- Produces:
  - `downloadJson(data: any, filename: string): void` in `utils/download.js`.
  - `exportAPI.restore(file: File)` → axios promise for `POST /api/restore`.
  - `<RestoreDialog file={File} backup={parsed JSON} onClose={() => void} onRestored={(restored) => void} />`, where `restored` is the response's `restored` object.

- [ ] **Step 1: Download helper**

Create `frontend/src/utils/download.js`:

```js
// Save a value as a pretty-printed JSON file through a temporary object URL.
export function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
```

- [ ] **Step 2: API client**

In `frontend/src/api.js`, replace the `exportAPI` object with:

```js
// Backup & Restore API
export const exportAPI = {
  download: () => api.get('/api/export'),
  restore: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/restore', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  }
};
```

- [ ] **Step 3: The dialog**

Create `frontend/src/components/RestoreDialog.jsx`:

```jsx
import { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, X } from 'lucide-react';
import { exportAPI } from '../api';
import { downloadJson } from '../utils/download';

const SECTIONS = [
  { key: 'assets', label: 'Assets' },
  { key: 'liabilities', label: 'Liabilities' },
  { key: 'bank_accounts', label: 'Bank accounts' },
  { key: 'insurances', label: 'Insurances' },
  { key: 'mutual_funds', label: 'Mutual funds' },
  { key: 'equities', label: 'Equities' },
  { key: 'snapshots', label: 'Snapshots' },
];

const countOf = (data, key) => (Array.isArray(data?.[key]) ? data[key].length : 0);

const describeBackupDate = (value) => {
  const date = value ? new Date(value) : null;
  if (!date || isNaN(date)) return 'Backup date unknown';
  return `Backup from ${new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true,
  }).format(date)}`;
};

const filenameTimestamp = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
};

export default function RestoreDialog({ file, backup, onClose, onRestored }) {
  const [current, setCurrent] = useState(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [downloadFirst, setDownloadFirst] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    exportAPI.download()
      .then((response) => { if (!cancelled) setCurrent(response.data); })
      .catch(() => { if (!cancelled) setLoadFailed(true); });
    return () => { cancelled = true; };
  }, []);

  const handleReplace = async () => {
    setError('');
    setRestoring(true);
    try {
      if (downloadFirst) {
        downloadJson(current, `networth_pre-restore_${filenameTimestamp()}.json`);
      }
      const response = await exportAPI.restore(file);
      onRestored(response.data.restored);
    } catch (err) {
      setError(err.response?.data?.detail || 'Restore failed');
      setRestoring(false);
    }
  };

  const loading = current === null && !loadFailed;
  const canReplace = current !== null && !restoring;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Restore from backup</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{describeBackupDate(backup?.export_date)}</p>
          </div>
          <button
            onClick={onClose}
            disabled={restoring}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm break-words">
              {error}
            </div>
          )}

          {loadFailed ? (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              Couldn't load your current data
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="font-medium pb-2"></th>
                  <th className="font-medium pb-2 text-right">In backup</th>
                  <th className="font-medium pb-2 text-right">In your account now</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-gray-100">
                {SECTIONS.map(({ key, label }) => (
                  <tr key={key}>
                    <td className="py-1">{label}</td>
                    <td className="py-1 text-right">{countOf(backup, key)}</td>
                    <td className="py-1 text-right">{loading ? '…' : countOf(current, key)}</td>
                  </tr>
                ))}
                <tr>
                  <td className="py-1">Goal</td>
                  <td className="py-1 text-right">{backup?.goal ? 'Yes' : 'No'}</td>
                  <td className="py-1 text-right">{loading ? '…' : (current?.goal ? 'Yes' : 'No')}</td>
                </tr>
              </tbody>
            </table>
          )}

          <div className="flex gap-2 bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 px-4 py-3 rounded-lg text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Everything currently in your account will be replaced by this backup. This can't be undone.</span>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={downloadFirst}
              onChange={(e) => setDownloadFirst(e.target.checked)}
              disabled={restoring}
            />
            Download my current data first
          </label>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={restoring} className="btn-secondary flex-1 disabled:opacity-50">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReplace}
              disabled={!canReplace}
              className="btn-danger flex-1 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {(restoring || loading) && <Loader2 className="w-4 h-4 animate-spin" />}
              {restoring ? 'Restoring...' : loading ? 'Loading...' : 'Replace my data'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Layout**

In `frontend/src/components/Layout.jsx`:

1. After `import { generateReport } from '../utils/reportGenerator';` add:

```js
import { downloadJson } from '../utils/download';
import RestoreDialog from './RestoreDialog';
```

2. Replace the two state lines

```js
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
```

with:

```js
  const [restoreResult, setRestoreResult] = useState(null);
  const [pendingRestore, setPendingRestore] = useState(null); // { file, backup } while the confirm dialog is open
```

3. In `handleExport`, replace everything from `const blob = new Blob(` through `window.URL.revokeObjectURL(url);` with:

```js
      downloadJson(response.data, `networth_backup_${new Date().toISOString().slice(0,10)}.json`);
```

4. Replace the whole `handleFileChange` function (from `const handleFileChange = async (e) => {` through its closing `};`, just before `const navItems`) with:

```js
  const showRestoreResult = (success, message) => {
    setRestoreResult({ success, message });
    setTimeout(() => setRestoreResult(null), 3000);
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    // Reset so picking the same file again still fires onChange
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (!file) return;

    if (!file.name.endsWith('.json')) {
      showRestoreResult(false, 'Please select a JSON file');
      return;
    }

    try {
      const backup = JSON.parse(await file.text());
      setPendingRestore({ file, backup });
    } catch {
      showRestoreResult(false, 'Invalid JSON file');
    }
  };

  const handleRestored = (restored) => {
    setPendingRestore(null);
    const total = Object.entries(restored)
      .filter(([key]) => key !== 'goal')
      .reduce((sum, [, count]) => sum + count, 0);
    setRestoreResult({ success: true, message: `Restored ${total} items` });
    updateLastUpdated();
    // Reload so every page picks up the restored data
    setTimeout(() => window.location.reload(), 2000);
  };
```

5. In the sidebar message block (`{/* Import Result Message */}`), rename the comment to `{/* Restore Result Message */}` and replace every `importResult` in that block with `restoreResult` (4 occurrences).
6. On the Restore button: change `disabled={importing}` to `disabled={pendingRestore !== null}`; change `<Upload className={\`w-3.5 h-3.5 ${importing ? 'animate-spin' : ''}\`} />` to `<Upload className="w-3.5 h-3.5" />`; change `<span>{importing ? 'Restoring...' : 'Restore'}</span>` to `<span>Restore</span>`.
7. Render the dialog **outside the sidebar** — the `<aside>` has a CSS `transform`, which would trap a `fixed` dialog inside the 256px sidebar. Directly after the closing `</main>` tag (before the final `</div>`), add:

```jsx

      {pendingRestore && (
        <RestoreDialog
          file={pendingRestore.file}
          backup={pendingRestore.backup}
          onClose={() => setPendingRestore(null)}
          onRestored={handleRestored}
        />
      )}
```

8. Check nothing stale remains: `grep -n "importing\|importResult\|exportAPI.import" frontend/src -r` → no output.

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: `✓ built in …` with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/download.js frontend/src/components/RestoreDialog.jsx frontend/src/api.js frontend/src/components/Layout.jsx
git commit -m "feat: confirm dialog for restore with a pre-restore download

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: End-to-end check in the browser

**Files:** none changed unless a check fails (then fix in the owning task's files and commit with a `fix:` message).

**Interfaces:** consumes everything above.

- [ ] **Step 1: Start a throwaway backend and frontend**

Port 8000 is usually taken by another container on this machine, so use 8001 and a temporary data file. In WSL:

```bash
cd /mnt/c/<path-to>/networth-tracker-wt/safe-restore/backend
DATA_FILE=/tmp/nwt-r1/data.json CREATE_DEMO_DATA=true SECRET_KEY="$(openssl rand -hex 32)" ~/.venvs/networth-tracker/bin/uvicorn main:app --port 8001
```

Frontend: create `/tmp/nwt-r1/vite.config.mjs` (outside the repo) that imports the project config and points the proxy at 8001, and run Vite on 5173:

```js
import base from '/mnt/c/<path-to>/networth-tracker-wt/safe-restore/frontend/vite.config.js';
export default { ...base, root: '/mnt/c/<path-to>/networth-tracker-wt/safe-restore/frontend',
  server: { ...base.server, port: 5173, proxy: { '/api': { target: 'http://localhost:8001', changeOrigin: true } } } };
```

```bash
cd /mnt/c/<path-to>/networth-tracker-wt/safe-restore/frontend && npx vite --config /tmp/nwt-r1/vite.config.mjs
```

Open `http://localhost:5173` in the browser pane and log in as the demo user (its password is printed in the backend log).

- [ ] **Step 2: Check NYSE and the report**
  - Equities → add `KO`, market **NYSE (US)**, qty 10, avg 60. It shows in `$`, and the INR totals card includes it.
  - Sidebar → **Print Report**; open the downloaded HTML. KO's value column shows an INR amount with `$` underneath; the equities total is in INR; Debt-to-Asset Ratio is a sensible percentage (not thousands).

- [ ] **Step 3: Check restore**
  - **Backup** → a file downloads.
  - Add one asset, then **Restore** with that backup file. The dialog shows the backup's date and counts; "In your account now" shows one more asset than "In backup". **Replace my data** → a `networth_pre-restore_*.json` file downloads, then "Restored N items", page reloads, and the extra asset is gone.
  - Restore with a file containing `not json` (named `.json`) → sidebar shows "Invalid JSON file", no dialog.
  - Restore with a file containing `[]` → dialog opens with zeros; **Replace my data** → the dialog shows "Backup must be a JSON object"; data unchanged.
  - Restore with a backup where one asset's `value` is `"lots"` → dialog shows `assets[i].value: …`; data unchanged.
  - Stop the backend, pick a valid backup → dialog shows "Couldn't load your current data" and **Replace my data** is disabled. Restart the backend.
  - Narrow the browser pane to phone width: the dialog sits over the whole screen, not inside the sidebar.

- [ ] **Step 4: Full suite once more and stop the servers**

Run: `cd backend && ~/.venvs/networth-tracker/bin/python -m pytest -p no:cacheprovider tests -q` → `135 passed`. Stop uvicorn and Vite; delete `/tmp/nwt-r1`.
