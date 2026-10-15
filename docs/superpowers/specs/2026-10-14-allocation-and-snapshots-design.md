# Asset-Class Allocation and Automatic Snapshots — Design Spec

**Date:** 2026-10-14
**Branch:** `feat/allocation-snapshots` (from local `main` at `7fe32fe`, which includes Rounds 1–3)
**Context:** Round 4 of 4. The dashboard pie groups by where money sits (each asset category, plus "equities", "bank accounts", "mutual funds" buckets), so a debt fund and an FD never show up as debt. Snapshots are only saved when the user clicks "Save Snapshot" and store three totals, so history has holes and allocation over time can't be shown. Built on the recommended options without check-ins; choices are recorded as **Decisions**.

---

## 1. Goal

1. **Allocation by asset class:** Equity, Debt, Gold, Real Estate, Cash, Other — next to today's by-holding view.
2. **Automatic monthly snapshots** that store the breakdown (by category, by liability category, by asset class).
3. **Change over time:** month-over-month net-worth change on the dashboard and an allocation-history chart.

**Out of scope:** target allocation / rebalancing hints (Tier 2 #9, not selected), back-filling months the app wasn't opened, per-fund look-through of hybrid/NPS allocations.

---

## 2. Asset-Class Mapping (`valuation.py`)

Classes, in display order: `equity`, `debt`, `gold`, `real_estate`, `cash`, `other`.

| Holding | Class |
|---|---|
| Asset `cash` | cash |
| Asset `real_estate` | real_estate |
| Asset `epf`, `ppf`, `bonds`, `retirement` | debt |
| Asset `gold`, `sgb` | gold |
| Asset `esop_rsu` | equity |
| Asset `nps` | ½ equity, ½ debt |
| Asset `investments`, `vehicles`, `crypto`, `other`, any unknown | other |
| Bank `savings`, `current`, `salary` | cash |
| Bank `fd`, `rd` | debt |
| Mutual fund `equity`, `elss`, `index` | equity |
| Mutual fund `debt`, `liquid` | debt |
| Mutual fund `hybrid` | ½ equity, ½ debt |
| Mutual fund `other`, unknown | other |
| Stocks (all markets, INR value) | equity |

**Decisions:** NPS and hybrid funds split 50/50 (their real mix varies; an even split beats calling them all equity or all debt). The generic "Investments" category maps to Other because its contents are unknown — users can re-categorise. "Other retirement" maps to debt (EPF-like schemes).

`portfolio_totals` adds `assets_by_class`: class → INR value (2 decimals), only classes with a value > 0, in display order. Item values are the same computed values used for the other totals, so the classes sum to `total_assets` (within rounding).

`DashboardMetrics` gains `assets_by_class: dict = {}`.

---

## 3. Snapshots

**Stored breakdown:** every new snapshot (manual or automatic) also stores `assets_by_category`, `liabilities_by_category` and `assets_by_class` from `portfolio_totals`. Older snapshots keep working without them.

- `database.create_snapshot(user_id, total_assets, total_liabilities, breakdown=None, timestamp=None)`; `_new_snapshot_row` copies the breakdown keys when given.
- `NetWorthSnapshot` (response) gains the three as `Optional[dict] = None`.
- Backups: export already returns stored rows; `SnapshotRestore` accepts the three as optional `{str: float}` maps with values `ge=0, le=1e300` (non-finite rejected by `InputModel`); `replace_user_data` keeps them.

**Automatic monthly snapshot (Decision):** taken when the dashboard is opened and the user has no snapshot dated in the current calendar month (manual ones count). Timestamp `YYYY-MM-DDT00:00:00` of `valuation.today()`. Skipped for an empty account (no assets and no liabilities). No background scheduler — the app stores everything in one JSON file and a timer writing concurrently with requests could lose updates; the first visit each month is enough for a personal tracker. "Save Snapshot" stays for extra points.

**Demo data:** a new demo user gets six synthetic monthly snapshots (first day of each of the previous six months) with a breakdown, so the history and allocation charts have something to show. The current month's snapshot is added by the first dashboard visit.

---

## 4. Frontend

- `utils/assetClasses.js`: classes with labels and fixed chart colours; `assetClassLabel(key)`.
- **Dashboard allocation card:** a two-button toggle "By asset class" / "By holding" (default by asset class; the choice is remembered in `localStorage`, read/written inside try/catch). By asset class uses `assets_by_class` and class colours; by holding is today's pie.
- **Net worth card:** under the value, "▲ ₹X (Y%) since Mon YYYY" (▼ when lower), comparing with the latest snapshot from an earlier calendar month; hidden when there isn't one. Privacy mode masks the amount and the percentage.
- **Net worth history:** x-axis labels include the year ("14 Oct 26"); the empty-state text explains that a snapshot is saved automatically once a month.
- **Allocation history:** a stacked area chart of `assets_by_class` across snapshots that have it (oldest → newest), shown once there are at least two; otherwise a one-line hint.
- **Print report:** an "Asset Allocation" table (class, value, share %) after the summary cards.

---

## 5. Testing

- Valuation: the mapping table (incl. the 50/50 splits and unknown → other), ordering, empty portfolio → `{}`.
- API: dashboard returns `assets_by_class`; manual snapshot stores the breakdown; first dashboard visit in a month creates exactly one snapshot, a second visit doesn't, the next month does; a manual snapshot that month prevents the automatic one; empty account → none; export/restore keeps the breakdown; restore rejects a negative or non-finite breakdown value; demo history (six snapshots with `assets_by_class`).
- Frontend: build; controller checks the toggle, MoM line, history labels, allocation history, report table and privacy masking in the browser.

---

## 6. Documentation

README: allocation by asset class (with the mapping and the 50/50 note), automatic monthly snapshots, month-over-month change, allocation history.
