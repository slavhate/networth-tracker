# Safe Restore and NYSE Support — Design Spec

**Date:** 2026-10-13
**Branch:** `feat/safe-restore-nyse` (from `main` at `a4b6092`)
**Context:** Self-hosted FastAPI + React app; all data in one JSON file (`data/data.json`) rewritten on every save. This is Round 1 of 4 in the "close the gaps" work (R2: valuation module, FD/RD, loan amortization, revaluation; R3: Indian asset types; R4: asset-class allocation and automatic snapshots).

---

## 1. Goal

1. **Restore replaces, safely.** Restoring a backup puts the account back into exactly the state in the backup file. Today `POST /api/import` appends to whatever is there (restoring into the same account doubles everything), skips snapshots, writes unvalidated fields straight into `data.json`, and can fail halfway.
2. **NYSE stocks** can be added and are valued in USD like NASDAQ stocks.
3. **US stock values are converted to INR everywhere they are totalled**, including the print report, which today adds dollar values to rupee values.

**Decisions (agreed):**
- Restore is **replace-only**: the user's current items, snapshots and goal are deleted and replaced by the backup's.
- The whole file is validated first; if anything is invalid, nothing is written.
- A confirm dialog shows what's in the file and what will be deleted, with a **"Download my current data first"** checkbox, on by default.
- `POST /api/restore` replaces `POST /api/import`; the old endpoint is removed (the sidebar is its only caller).

**Out of scope:**
- Merge/append restore.
- Restoring user account fields (password, 2FA settings) — a backup holds financial data only, and restore never touches the user record.
- Encrypting backups.
- Locking against concurrent writes in general (the app's load-modify-save pattern is unchanged; see §3.3 for what the atomic write does and does not cover).

---

## 2. Backup File Format

Unchanged. `GET /api/export` keeps producing:

```json
{
  "export_date": "2026-10-13T10:15:00",
  "user_id": "…",
  "assets": [], "liabilities": [], "bank_accounts": [], "insurances": [],
  "mutual_funds": [], "equities": [], "snapshots": [],
  "goal": { … } | null
}
```

Restore accepts any file in this shape:
- The top level must be a JSON object, else `400 "Backup must be a JSON object"`.
- It must contain at least one of the eight section keys (`assets` … `goal`), else `400 "This file doesn't look like a Net Worth Tracker backup"`.
- A missing section counts as empty (so its current items are deleted). The confirm dialog makes this visible (§5).
- Each list section must be a JSON array, else `400 "<section> must be a list"`.
- `export_date` and `user_id` are ignored by the server.

---

## 3. Backend

### 3.1 Endpoint (`main.py`)

`POST /api/restore` — multipart upload with field `file`, same as today's import; requires auth.

1. Read the upload; over 10 MB → `413 "Backup file too large (max 10MB)"`.
2. Decode as UTF-8 JSON; failure → `400 "Invalid JSON file"`.
3. Check the shape (§2).
4. Validate every item (§3.2). The first failure → `400` with its location, e.g. `"assets[3].value: Input should be a valid number"`. Nothing is written.
5. Call `db.replace_user_data(user_id, cleaned)` (§3.3).
6. Return `200`:

```json
{
  "status": "success",
  "restored": {
    "assets": 14, "liabilities": 7, "bank_accounts": 4, "insurances": 4,
    "mutual_funds": 6, "equities": 6, "snapshots": 12, "goal": true
  }
}
```

`POST /api/import` and its handler are deleted.

### 3.2 Validation (`restore.py`, new)

A new module `backend/restore.py` holds the parsing and validation so `main.py` only wires the endpoint. Each item is validated with the model already used for creating that kind of item:

| Section | Model | Notes |
|---|---|---|
| `assets` | `AssetCreate` | |
| `liabilities` | `LiabilityCreate` | |
| `bank_accounts` | `BankAccountCreate` | |
| `insurances` | `InsuranceCreate` | |
| `mutual_funds` | `MutualFundCreate` | |
| `equities` | `EquityRestore` (new: `EquityCreate` + `current_price: Optional[float] = Field(None, ge=0)`) | keeps the last known price; `db.create_equity` recomputes invested amount, value and gain |
| `snapshots` | `SnapshotRestore` (new: `total_assets: float`, `total_liabilities: float`, `timestamp: str`) | `timestamp` must parse with `datetime.fromisoformat`, else the error names it; `net_worth` is recomputed as assets − liabilities |
| `goal` | `GoalCreate` | `null` or missing → no goal |

- Validation uses `model_validate(item)`; Pydantic's default `extra="ignore"` drops unknown fields. `id`, `user_id`, `created_at`, `updated_at` and computed fields (e.g. an equity's `gain_loss`) are not in these models, so they are dropped too.
- The cleaned value is `model.model_dump(mode="json")` (enums become plain strings, as the create endpoints store them).
- An item that is not a JSON object fails with `"<section>[i]: must be an object"`.
- Error location format: `"<section>[<index>].<field path>: <pydantic msg>"`; for `goal`: `"goal.<field>: <msg>"`.

`restore.py` exposes one function:

```python
def parse_backup(raw: bytes) -> dict
    # returns {"assets": [...], ..., "snapshots": [...], "goal": dict | None}
    # raises RestoreError(status_code, detail)
```

### 3.3 Storage (`database.py`)

**New: `replace_user_data(user_id: str, cleaned: dict) -> None`**
- One `load_data()`.
- For each of the seven list collections (`assets`, `liabilities`, `bank_accounts`, `insurances`, `mutual_funds`, `equities`, `snapshots`) and `goals`, drop rows with this `user_id`.
- Append new rows built the same way the existing `create_*` helpers build them: fresh `generate_id()`, this `user_id`, `created_at`/`updated_at` = now. Equities get the computed fields exactly as `create_equity` computes them, with a missing **or `null`** `current_price` falling back to `avg_buy_price` (today `create_equity` only handles a missing key; `null` would crash the multiplication). Snapshots keep the backup's `timestamp` (the history must keep its dates) and get a fresh id.
- One `save_data()`.
- To avoid duplicating row-building, the row-building part of each `create_*` helper is pulled into a small `_new_<kind>_row(user_id, data)` function that both `create_*` and `replace_user_data` call. Behaviour of `create_*` is unchanged.

**Changed: `save_data` writes atomically.**
- Write JSON to `<DATA_FILE>.tmp` in the same directory, `flush()` + `os.fsync()`, then `os.replace(tmp, DATA_FILE)`.
- If writing the temp file raises, the temp file is removed and the exception re-raised; `DATA_FILE` is untouched.
- A crash mid-write now leaves the previous complete file instead of a truncated one. This applies to every save in the app.
- It does not serialise concurrent requests; two requests that load before either saves can still lose one update, exactly as today.

### 3.4 NYSE (`models.py`, `stock_service.py`, `main.py`)

- `StockMarket` gains `NYSE = "NYSE"`.
- `models.py` gains `USD_MARKETS = frozenset({"NASDAQ", "NYSE"})` next to the enum.
- `stock_service.get_yahoo_symbol`: NYSE returns the bare symbol (Yahoo uses no suffix for US listings), same branch as NASDAQ.
- `main.py`: the dashboard and snapshot totals use `e.get("market") in USD_MARKETS` instead of `== "NASDAQ"`.
- `GET /api/equities-summary` today adds USD and INR values raw; it fetches the rate and converts USD-market holdings, same as the dashboard. (Its frontend helper exists but no page calls it; fixed for correctness.)

---

## 4. NYSE and USD in the Frontend

- `Equities.jsx`: `MARKETS` gains `{ value: 'NYSE', label: 'NYSE (US)' }` (same green style as NASDAQ). A local `isUsdMarket(market)` replaces the four `=== 'NASDAQ'` checks (currency formatting, privacy mask, invested total, current total).
- `reportGenerator.js`:
  - Fetch the rate with the existing `exchangeAPI.getRate()` alongside the other calls; on failure fall back to `83.5` (the same default `Equities.jsx` uses).
  - In the Equities table, a US holding's value column shows the INR amount with the USD amount underneath in small text (`$1,850.00`).
  - The equities total converts US holdings to INR before summing.

---

## 5. Restore in the Frontend

### 5.1 Flow (`Layout.jsx`, new `components/RestoreDialog.jsx`)

1. The user clicks **Restore** and picks a file (unchanged file picker; non-`.json` names are still rejected client-side).
2. The browser reads and parses the file. Invalid JSON → the sidebar's existing error message ("Invalid JSON file"); no dialog.
3. `RestoreDialog` opens and fetches the current data with `exportAPI.download()` (one request) to count what will be deleted.
4. The dialog shows:
   - "Backup from <export_date, formatted en-IN>" (or "Backup date unknown").
   - A table: section name | in backup | currently in your account. Rows: Assets, Liabilities, Bank accounts, Insurances, Mutual funds, Equities, Snapshots, Goal (Yes/No).
   - Warning text: "Everything currently in your account will be replaced by this backup. This can't be undone."
   - Checkbox **"Download my current data first"**, checked by default.
   - Buttons **Cancel** and **Replace my data** (red).
5. On **Replace my data**:
   - If the checkbox is on, download the already-fetched current data as `networth_pre-restore_<YYYY-MM-DD_HHmmss>.json` (same Blob-download code as Export, extracted into a shared `downloadJson(data, filename)` helper in `utils/download.js`).
   - Call `exportAPI.restore(file)` → `POST /api/restore`.
   - Success: close the dialog, show "Restored N items" in the sidebar message (N = sum of list counts), reload after 2 s (as today).
   - Failure: keep the dialog open and show the server's `detail` in it; nothing on the server changed.
6. While fetching current data or restoring, buttons are disabled and show a spinner.
7. If fetching current data fails, the dialog shows "Couldn't load your current data" and disables **Replace my data**. Restoring without the pre-restore copy and without seeing what will be deleted is not offered.

### 5.2 `api.js`

`exportAPI.import` is renamed `exportAPI.restore` and posts to `/api/restore`.

---

## 6. Error Handling Summary

| Situation | Result |
|---|---|
| File > 10 MB | 413, nothing written |
| Not UTF-8 / not JSON | 400 "Invalid JSON file", nothing written |
| Top level not an object | 400 "Backup must be a JSON object" |
| No known section keys | 400 "This file doesn't look like a Net Worth Tracker backup" |
| Section not a list | 400 "<section> must be a list" |
| Invalid item | 400 "<section>[i].<field>: <msg>", nothing written |
| Crash during save | previous `data.json` intact (atomic replace) |

---

## 7. Testing

Backend (`backend/tests/test_restore.py`, `backend/tests/test_us_markets.py`), using the existing `client` and `auth_headers` fixtures:

- Restore replaces: create items, restore a backup with different items → only the backup's items remain, counts match the response.
- Restoring the user's own fresh export reproduces the same data (round trip; ids differ, content equal).
- Snapshots are restored with their original timestamps and recomputed `net_worth`; goal restored; `goal: null` removes an existing goal.
- Another user's data is untouched by a restore.
- Each 400 case in §6 returns the documented message **and** leaves the user's data unchanged.
- Unknown fields and `id`/`user_id` in the file are not stored.
- Restored equity keeps `current_price` and has recomputed `current_value`/`gain_loss`.
- `/api/import` returns 404/405.
- `save_data` leaves no `.tmp` file behind after a save; if serialisation fails (a non-serialisable value makes `json.dump` raise mid-write) the previous file is intact and no `.tmp` file remains.
- An equity restored with `current_price: null` is valued at its `avg_buy_price`.
- NYSE: `get_yahoo_symbol("KO", "NYSE") == "KO"`; creating an NYSE equity is accepted; dashboard and `/api/equities-summary` convert NYSE and NASDAQ values with a stubbed rate (monkeypatch `exchange_service.fetch_usd_to_inr`) and do not convert NSE/BSE. Stock price fetching is stubbed so tests never hit Yahoo.

Frontend (no test framework in the project): `npm run build` succeeds; manual check in the browser against a dev backend — restore dialog counts, checkbox download, replace, error shown for a corrupted file, NYSE holding added and shown in USD, print report shows INR totals with USD under US holdings.

---

## 8. Documentation

README: the Backup bullet says Restore **replaces** your data and offers a pre-restore download; API table lists `POST /api/restore` (not `/api/import`); the Stock Market table gains an NYSE row; "Live stock prices from NSE, BSE, NASDAQ" → "NSE, BSE, NASDAQ and NYSE".
