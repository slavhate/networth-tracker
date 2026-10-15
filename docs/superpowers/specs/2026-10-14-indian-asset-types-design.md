# Indian Asset Types — Design Spec

**Date:** 2026-10-14
**Branch:** `feat/indian-assets` (from local `main` at `02dbffd`, which includes Rounds 1–2)
**Context:** Round 3 of 4. Assets today have generic categories (cash, investments, real estate, vehicles, retirement, crypto, other); EPF, PPF, NPS, gold and the like end up in "Retirement" or "Other". Round 2 added `valuation.py` (values as of today) and the yearly change rate on assets. The user asked for this round to be built on the recommended options without check-ins; choices are recorded as **Decisions**.

---

## 1. Goal

1. **Indian asset categories:** EPF, PPF, NPS, Gold, Sovereign Gold Bonds (SGB), Bonds, ESOP/RSU — selectable on the Assets page, shown with proper labels on the page, the dashboard pie and the print report.
2. **EPF and PPF balances grow by themselves** from a balance on a date, a monthly contribution and the published interest rate.
3. **Gold, SGB and ESOP/RSU** can be entered as quantity × price (grams or units), so updating the price is one field.

**Decision:** these stay **assets with categories** on the Assets page (not new pages like Mutual Funds/Equities). Each category reveals only the fields it needs. Round 4's asset-class mapping builds on these categories.

**Out of scope:** live gold or NPS NAV prices (no reliable keyless API; prices stay manual), PPF 15-year maturity / extension rules, the ₹1.5 lakh PPF yearly cap, EPF interest on contributions above the tax-free limit, VPF as a separate category (enter it as EPF), migrating existing "Retirement"/"Other" rows (users re-categorise them).

---

## 2. Categories

`AssetCategory` gains: `epf` (EPF), `ppf` (PPF), `nps` (NPS), `gold` (Gold), `sgb` (Sovereign Gold Bonds), `bonds` (Bonds), `esop_rsu` (ESOP / RSU). Existing values stay. Labels live in one frontend module used by the Assets page, the dashboard pie and the report.

| Kind | Categories | Fields shown in the form |
|---|---|---|
| Provident fund | `epf`, `ppf` | Balance, Balance as of, Monthly contribution, Interest rate (% p.a.) |
| Quantity × price | `gold`, `sgb`, `esop_rsu` | Quantity (grams for gold/SGB, units for ESOP/RSU), Price per gram/unit, Price as of, Yearly change % (optional) |
| Plain | everything else (incl. `nps`, `bonds`) | Value, Value as of, Yearly change % (optional) — as today |

---

## 3. Data Model (`models.py`)

`AssetBase` and `AssetUpdate` gain (same bounds on both, `InputModel` base kept):

| Field | Type / rule |
|---|---|
| `monthly_contribution` | `Optional[float]`, `ge=0, le=MAX_AMOUNT` |
| `interest_rate` | `Optional[float]`, `ge=0, le=100` (% per year; provident funds) |
| `quantity` | `Optional[float]`, `gt=0, le=MAX_UNITS` |
| `unit_price` | `Optional[float]`, `ge=0, le=MAX_AMOUNT` |

All four join `ASSET_CLEARABLE` (a PUT may clear them with null).

Write-time rules (`main.py`, create and update; for updates on the row storage will hold, via `_merged`):
- **Quantity × price:** when both `quantity` and `unit_price` are set, `value` is stored as `round(quantity × unit_price, 2)`, overriding any `value` sent. Above `MAX_AMOUNT` → 422 "Quantity × price is above the allowed maximum", nothing written.
- **Dates:** if the row has `annual_change_rate`, `interest_rate` or `monthly_contribution` but no `valuation_date`, `valuation_date` is set to today (generalises Round 2's rule).

---

## 4. Valuation (`valuation.py`)

`asset_current_value(asset, on)`:
- `category in ("epf", "ppf")` and `interest_rate` set → **provident-fund value** below.
- otherwise → Round 2 behaviour (yearly change rate, or the stored value).

**Provident-fund value** (`_provident_fund_value`), modelling how EPFO and PPF compute interest — monthly on the running balance, credited once a year at the end of the financial year (31 March):
- Start: `balance = value` on `valuation_date` (the anchor; it already includes everything up to that date), `accrued = 0`.
- For each calendar month **after** the anchor's month, up to `on`:
  - add `monthly_contribution` on the 1st (the contribution counts for that month's interest, like a PPF deposit made by the 5th);
  - if the whole month has passed (its last day ≤ `on`): `accrued += balance × interest_rate / 1200`;
  - if that month is March and it has passed: `balance += accrued; accrued = 0` (financial-year credit).
- Value = `balance + accrued` (interest earned so far this year counts toward net worth even before it is credited).
- `on <= valuation_date` or no `valuation_date` → `value`.

**Decision:** interest accrued in the anchor's own financial year before the anchor date is not reconstructed (the user's statement balance excludes it); the first credit after the anchor therefore slightly understates. Re-anchoring on each annual statement keeps it exact.

Reference values (tests):
- ₹0 on 2025-03-31, ₹10,000/month, 7.1% → ₹1,24,615.00 on 2026-03-31 (interest 4,615 = 10,000 × 7.1/1200 × 78).
- ₹1,00,000 on 2025-03-31, no contribution, 7.1% → ₹1,07,100 on 2026-03-31; ₹1,14,704.10 on 2027-03-31.
- Same plan on 2025-09-15 → 6 contributions and 5 months' interest: ₹60,887.50.

---

## 5. Frontend

- `frontend/src/utils/assetCategories.js` (new): `ASSET_CATEGORIES` (value, label, icon, colour) for every category; `assetCategoryLabel(value)`; plus `bucketLabel(name)` for the dashboard's non-asset buckets (`equities` → "Equities", `bank_accounts` → "Bank Accounts", `mutual_funds` → "Mutual Funds"), falling back to title-casing.
- **Assets page:** the category list comes from that module; the form shows the field group for the selected kind (§2). Provident funds suggest 8.25% for EPF and 7.1% for PPF while the rate field is empty and untouched (**Decision:** the current EPFO and PPF rates as editable suggestions). Quantity × price shows the computed value live (read-only) and sends quantity and price; fields that don't apply to the selected category are sent as null (clearing stale values when the category changes). List lines: provident funds "₹X on <date> · +₹C/month at R%"; quantity "Q g × ₹P/g" (units for ESOP/RSU); the Round 2 yearly-change line where a rate is set.
- **Dashboard** pie and liability bars use the label helpers instead of title-casing raw keys (so "epf" reads "EPF", "esop_rsu" "ESOP / RSU").
- **Print report:** asset categories use the same labels.

---

## 6. Demo Data

A new demo user's sample assets use the new categories: "EPF Balance" → `epf` with 8.25% and ₹3,600/month from 6 months ago; "PPF Account" → `ppf` with 7.1% and ₹12,500/month from 6 months ago; "NPS Account" → `nps`; "Gold Jewelry" → `gold`, 50 g × ₹10,000/g. Existing demo users are unchanged.

---

## 7. Testing

- Valuation unit tests for the reference values in §4, a mid-month anchor, an anchor on 31 March, no rate (stored value), `on` before the anchor, and that non-provident categories ignore `interest_rate`.
- API tests: new categories accepted; quantity × price stored as value and recomputed on update; the 422 above the maximum with nothing written; clearing the new fields; the date default for provident funds; list/dashboard totals use the provident-fund value; export/restore round-trips the new fields.
- Frontend: build; controller checks the flows in the browser.

---

## 8. Documentation

README: the new categories, how EPF/PPF grow (monthly interest, credited every 31 March), quantity × price holdings.
