# NPS Contributions, Scheme Holdings and Form Hint Fix — Design Spec

**Date:** 2026-10-15
**Branch:** `feat/nps-schemes` from local `main` at `2a255af` (the single commit on `feat/networth-gaps`); the finished work is squashed into that branch's single commit.
**Context:** Today an NPS account is a plain value (optionally grown by a yearly rate). Real NPS accounts get a monthly employer contribution from salary and the subscriber's own yearly contribution, and the money sits in pension fund schemes whose NAVs are published daily. Separately, the hint under the EMI/tenure fields in the liability form overlaps the inputs. Built on the recommended options without check-ins; choices are recorded as **Decisions**.

---

## 1. Goal

1. **NPS contributions:** an employer contribution per month and the subscriber's own contribution per year.
2. **NPS investment options:** the schemes an account holds, with the % of new money each receives and, optionally, the units held; the account is valued from the schemes' NAVs, fetched online.
3. **Form hint fix:** hints under form fields no longer overlap the inputs above them.

**Out of scope:** annuity or maturity projections, tax calculations, allocation changes over time (one current allocation applies to all contributions), auto-choice glide paths, NAV charts, withdrawals.

---

## 2. Contributions (`valuation.py`)

Fields on an NPS asset: `monthly_contribution` (existing; labelled "Employer contribution ₹/month" for NPS), `yearly_contribution` (new, ₹/year, `ge=0, le=MAX_AMOUNT`), `yearly_contribution_month` (new, 1–12; March when not set).

`nps_contributions(asset, after, through)` returns `(date, amount)` pairs in date order:
- the employer contribution on the 1st of every month with `after < date ≤ through`;
- the own contribution on the 1st of the chosen month each year with `after < date ≤ through`.

`after` is the "Balance as of" date (`valuation_date`), so contributions count from the month after the balance date, the same rule as EPF/PPF.

**Decision:** contributions land on the 1st of the month. NPS invests a salary contribution within days of payday; a fixed day keeps the value deterministic and testable.

**Value without NAVs** (no schemes, or NAVs not available): the balance grown at `annual_change_rate` from the balance date, plus each contribution grown at the same rate from its own date; with no rate, at cost. An NPS asset with no contributions behaves exactly as today.

---

## 3. Investment Options (Schemes)

### 3.1 Data

`nps_schemes`: a list of 1–10 entries, each:

| Field | Rule |
|---|---|
| `scheme_code` | `^SM\d{6}$` (the NPS scheme code) |
| `scheme_name` | 1–150 characters |
| `allocation_pct` | 0–100; the share of new contributions |
| `units` | optional, `> 0`, `≤ MAX_UNITS`; units held on the balance date (from the statement) |

Rules: codes are unique; allocations add up to 100 (±0.01); units are given for every scheme or for none (422 "Enter units for every scheme or for none").

NPS fields are read only for category `nps`; when an asset moves to another category the form sends nulls for them (the Round 3 pattern for quantity fields).

Kept by the server (never accepted from create/update input): per scheme `nav`, `nav_date`, `base_units`, `contribution_units`; on the asset `nps_priced_through` (the date contributions have been converted to units up to).

### 3.2 Pricing

Pricing turns the inputs into units using NAV history:
- `base_units` = the entered `units`, or `balance × allocation_pct / 100 / NAV on or before the balance date`;
- `contribution_units` = Σ over contributions in `(balance date, today]` of `amount × allocation_pct / 100 / NAV on or before the contribution date`;
- `nav`, `nav_date` = the latest NAV on or before today;
- `nps_priced_through` = today.

Units and NAVs are rounded to 4 decimals. Pricing is all-or-nothing: if any scheme has no history, no NAV on or before the balance date, or derived units/value beyond `MAX_UNITS`/`MAX_AMOUNT`, the asset is left unpriced (no derived fields).

The arithmetic is a pure function in `valuation.py` taking the NAV histories as input; fetching lives in a new `nps_service.py`.

**When pricing runs:**
- **On save:** create, or an update that changes `value`, `valuation_date`, `monthly_contribution`, `yearly_contribution`, `yearly_contribution_month`, `nps_schemes` or `category` (to NPS). If NAVs can't be fetched, the asset is saved unpriced. Saving never fails because NAVs are unavailable.
- **On refresh:** `POST /api/assets/{id}/refresh-nav` prices again. If NAVs can't be fetched it returns 502 "Couldn't fetch NPS NAVs right now" and leaves the stored data unchanged (still consistent, just older). A non-NPS asset or one without schemes gets 400.

**Decision:** a failed save clears derived fields because the inputs changed and the old units no longer match them. A failed refresh keeps them because they still match the inputs.

### 3.3 Value

- **Priced:** Σ (`base_units` + `contribution_units`) × `nav`, plus contributions in `(nps_priced_through, today]` at cost.
- **Unpriced:** §2's value without NAVs.

`asset_view` adds per scheme `current_units` and `current_value` when priced.

### 3.4 Asset class

A scheme's class comes from its name: `SCHEME E` → equity, `SCHEME C`/`SCHEME G` → debt, `SCHEME A` → other (case-insensitive, any spacing). Anything else (government, Lite, Vatsalya, tax-saver schemes) keeps today's 50/50 equity/debt split.

Weights: when priced, each scheme's current value, with the at-cost tail split by allocation %; when unpriced, the allocation %. No schemes: 50/50 as today.

### 3.5 NAV source

[npsnav.in](https://npsnav.in) API: free, no key, data sourced from the NPS CRA. Its data licence (CC BY-NC 4.0) allows personal, non-commercial use; the UI and README credit it. Endpoints:
- `/api/latest`: every scheme with its latest NAV (`Scheme Code`, `Scheme Name`, `PFM Name`, `NAV`, `Last Updated`);
- `/api/historical/{code}`: `{"data": [{"date", "nav"}…]}`.

Base URL from setting `NPS_NAV_API_URL` (default `https://npsnav.in/api`), so a mirror or a local stub can be used. In-memory cache for 6 hours (like mutual-fund NAVs), 10 s timeout.

The parser is tolerant: dates `DD-MM-YYYY` (documented) or `YYYY-MM-DD`; NAV a number or numeric string; rows that don't parse, or aren't finite and positive, are skipped.

`GET /api/nps/schemes` returns `[{scheme_code, scheme_name, pfm_name, nav, nav_date}]` sorted by name, or 502 when the list can't be fetched.

### 3.6 Backup and restore

Export already returns stored rows. Restore accepts the input fields plus the derived ones (bounded: NAV ≤ `MAX_AMOUNT`, units ≤ `MAX_UNITS`, ISO dates) through an `AssetRestore` model. Restore makes no network calls.

### 3.7 Demo data

The demo NPS asset gets:
- an employer contribution, an own yearly contribution in March, and a balance date;
- three UTI Tier I schemes (E/C/G direct plans, 75/15/10) without units.

It stays unpriced until the first refresh, because startup makes no network calls.

---

## 4. Frontend

- `assetCategories.js`: NPS gets `kind: 'nps'`.
- **NPS form fields:**
  - Balance (₹) and Balance as of (statement date);
  - Employer contribution ₹/month;
  - Own contribution ₹/year, with a month select (default March);
  - Expected return % per year, used only while NAVs aren't available.
- **Investment options editor:**
  - Each row has a scheme picker, % of new money and units (optional), plus remove. "Add scheme" allows up to 10 rows.
  - The running total of % is shown; save is blocked unless it is 100 and units are given for all rows or none.
  - The picker searches the list from `GET /api/nps/schemes` (case-insensitive substring) and shows the fund manager and latest NAV.
  - If the list can't be loaded, existing rows stay and a short note says so.
  - The hint explains that statement units are most accurate, that without units the balance is split by % at the balance date's NAV, and that contributions start the month after the balance date. It also credits npsnav.in.
- **Asset card (NPS with schemes):**
  - One line per scheme: name, %, units, NAV with its date, and value.
  - A "Refresh NAV" button, and "NAV not available yet" while unpriced.
- **Background refresh:** after the Assets page loads, NPS assets with schemes that are unpriced or priced before today are refreshed one at a time. Failures are silent; the card keeps its last state.
- **Hint fix:** the hints use `!-mt-2` (a forced negative top margin that pulls them into the inputs above). Replace it with `!mt-1` in `Liabilities.jsx` (2), `Assets.jsx` (1) and `BankAccounts.jsx` (1).

**Decision:** no automatic re-anchoring for NPS. Unlike EPF/PPF, the NPS form does not move the balance to today when a contribution changes. With statement units, re-anchoring would need today's units per scheme. The hint tells the user to update the balance, its date and the units from their latest statement when contributions change.

**Decision:** the Assets page refreshes stale NPS assets in the background after loading. The dashboard and snapshots use the stored NAVs, as mutual funds do.

---

## 5. Testing

- **Valuation:**
  - the contribution schedule (balance date on the 1st and on the 31st, month select, year rollover);
  - value without NAVs, with and without a rate;
  - priced value with the at-cost tail;
  - class shares;
  - pricing from histories (entered vs derived units, all-or-nothing, no NAV before the balance date).
- **Models:** allocation ≠ 100, duplicate codes, a bad code, more than 10 schemes, mixed units, month 0 and 13.
- **API (NPS service mocked):**
  - create prices; a fetch failure saves unpriced;
  - a name-only update keeps derived fields; a contribution change reprices;
  - refresh succeeds, returns 502 on failure, 400 for non-NPS;
  - the scheme list returns 200, or 502 on failure;
  - restore round-trips derived fields;
  - the demo asset.
- **Frontend:** the build passes. The controller runs a browser check against a local stub NAV server with made-up scheme codes and names.

---

## 6. Documentation

README:
- NPS contributions and investment options;
- how the value is worked out;
- the NAV source and credit;
- `NPS_NAV_API_URL` in the environment table.

## 7. Constraints

- No hardcoded credentials or personal data.
- Test data and demo data use made-up or generic values only.
- No new dependencies (`httpx` is already used).

---

# Part B — Mutual Fund SIPs

**Context:** A mutual fund holding is a fixed number of units today. A SIP (systematic investment plan) adds an installment on a schedule, and each installment buys units at that day's NAV. The fund's `sip_amount` field exists but nothing uses it. The user asked for the SIP amount, its frequency and, for monthly SIPs, the date each month it is credited, with the fund's amount worked out from them.

## B1. Fields (mutual fund)

| Field | Rule |
|---|---|
| `sip_amount` | existing; `≥ 0`; empty or 0 means no SIP |
| `sip_frequency` | `weekly`, `monthly` or `quarterly`; `monthly` when not set |
| `sip_day` | 1–31; the day of the month a monthly or quarterly installment lands; clamped to the month's last day |
| `sip_start_date` | the first installment date |
| `sip_end_date` | optional; no installment after it |
| `holdings_date` | the date `units` and `invested_amount` were accurate (from a statement); installments after it add to the holding |

Validation: `sip_end_date` on or after `sip_start_date` (422 "SIP end date must be on or after its start date").

Write-time defaults when `sip_amount > 0`:
- `holdings_date` = today;
- `sip_start_date` = `holdings_date`;
- `sip_frequency` = `monthly`;
- `sip_day` = the start date's day (for monthly and quarterly).

Kept by the server: `sip_units`, `sip_invested` and `sip_priced_through` (the date installments have been converted to units up to).

## B2. Schedule and value (`valuation.py`, pure)

`sip_installments(fund, after, through)` returns `(date, amount)` pairs for installments in `(after, through]`, on or after `sip_start_date` and on or before `sip_end_date`:
- weekly: every 7 days from the start date;
- monthly: on `sip_day` every month from the start month;
- quarterly: on `sip_day` every third month from the start month.

`sip_price(fund, history, on)`: every installment in `(holdings_date, on]` buys `amount / NAV on or before its date`. It returns:
- `sip_units`, rounded to 4 decimals;
- `sip_invested`, the sum of those installments;
- `sip_priced_through` = `on`;
- `current_nav` = the latest NAV on or before `on`;
- `current_value` = (`units` + `sip_units`) × `current_nav`.

It is all-or-nothing: None if any installment or `on` has no NAV, or a result passes `MAX_UNITS`/`MAX_AMOUNT`.

`fund_view(fund, on)`, for a fund with an active SIP (`sip_amount > 0` and a `holdings_date`):
- **Priced:**
  - value = (`units` + `sip_units`) × `current_nav` + installments after `sip_priced_through` at cost;
  - `total_units` = `units` + `sip_units`;
  - `total_invested` = `invested_amount` + `sip_invested` + those later installments.
- **Unpriced:**
  - value = the stored `current_value` + installments after `holdings_date` at cost;
  - `total_invested` = `invested_amount` + those installments;
  - `total_units` = `units`.
- **No SIP:** stored values, with `total_units` = `units` and `total_invested` = `invested_amount`.

The mutual-fund list, the summary, the dashboard totals and the asset classes all use `fund_view`.

## B3. NAVs and when pricing runs

NAV history comes from mfapi.in (`/mf/{scheme_code}`, already used for the latest NAV; the response's `data` holds the full history in the same `{"date": "DD-MM-YYYY", "nav": "…"}` shape the NPS parser reads). `nav_service.fetch_history(scheme_code)` caches it like the latest NAV. A fund without a `scheme_code` resolves one through the existing name search.

- **On save:** create, or an update that changes the SIP fields, `holdings_date`, `units`, `fund_name` or `scheme_code`. If NAVs can't be fetched, the derived fields are cleared and installments count at cost. Saving never fails because of NAVs.
- **On refresh:** the existing list refresh (`?refresh_nav=true`) and `POST /api/mutual-funds/{id}/refresh-nav` also price the SIP. A failure leaves the stored SIP pricing as it was.
- **Stopping a SIP:** setting `sip_amount` to null or 0 clears the derived fields. SIP fields are clearable in updates.
- **Backups:** export and restore keep the SIP and derived fields (a `MutualFundRestore` model with bounds). Restore makes no network calls.

**Decision:** an installment counts on its scheduled day, at the NAV on or before that day. Real allotment can be a business day later; the difference is small and the value stays deterministic.

## B4. Frontend (Mutual Funds page)

- **Form:** a "SIP (optional)" section with:
  - SIP amount;
  - frequency (Weekly / Monthly / Quarterly);
  - "SIP date (day of month)" for monthly and quarterly;
  - first SIP date and last SIP date (optional);
  - "Units and invested amount as of" (`holdings_date`, default today).
  The hint explains that each installment after that date buys units at its day's NAV (mfapi.in) and counts at cost until NAVs are fetched.
- **Card:** a SIP line ("SIP ₹X monthly on the 5th since …"). Invested and Units show `total_invested` and `total_units`.
- **Summary:** totals use `total_invested` and `current_value`.

## B5. Testing

- **Valuation:**
  - the schedule for each frequency;
  - day clamping (31st in February);
  - start and end bounds;
  - pricing, including all-or-nothing;
  - views priced, unpriced and without a SIP.
- **API (NAV service mocked):**
  - create prices; a failure saves unpriced;
  - a name-only edit keeps the pricing; a SIP change prices again;
  - both refresh paths;
  - stopping a SIP clears the derived fields;
  - the summary and the dashboard include installments;
  - restore round-trips;
  - the end-date validation.

---

# Part C — Logo and Favicon

The user's icon (a gradient rounded square with a rising chart, coins and a sprout) replaces the 💰 emoji logo:
- in the mobile header;
- in the sidebar;
- on the Login and Register pages.

It is also the favicon and the Apple touch icon.

Assets in `frontend/public/` are cropped from the supplied image to the visible rounded square, with transparent corners:
- `logo.png` (256 px);
- `favicon.png` (64 px);
- `favicon-32.png`;
- `apple-touch-icon.png` (180 px).

`index.html` links them (PNG icon at 32 and 64, apple-touch-icon) instead of `/vite.svg`, which is deleted. In the UI the image is shown at the logo's current size (`w-10 h-10` sidebar, `w-8 h-8` mobile header, `w-16 h-16` login and register) with the alt text "NetWorth Tracker". The emoji's coloured tile is no longer needed, since the icon carries its own background.

---

# Part D — Automatic Snapshot Frequency

**Context:** An automatic snapshot is saved the first time the dashboard is opened in a calendar month. Nothing on screen says so except an empty-state hint. The user asked for the frequency to be called out on the UI, and for a short list of frequencies to choose from.

## D1. Frequencies

| Option | Label | A snapshot is due when |
|---|---|---|
| `weekly` | Weekly | the latest snapshot is 7 or more days old (or there is none) |
| `fortnightly` | Every 2 weeks | the latest snapshot is 14 or more days old |
| `monthly` (default) | Monthly | there is none yet in the current calendar month (today's behaviour) |
| `quarterly` | Quarterly | there is none yet in the current calendar quarter (Jan–Mar, Apr–Jun, Jul–Sep, Oct–Dec) |

Manual snapshots count. The snapshot is still taken when the dashboard is opened (no background scheduler, as Round 4 decided). Empty accounts are still skipped. Snapshots dated after today don't count.

**Decision:** weekly and every-2-weeks count days from the latest snapshot; monthly and quarterly follow the calendar, so month-over-month comparisons and the history chart keep calendar points. 14 days is used rather than 15, so the cadence lines up with weeks.

## D2. Storage and API

- Each user's choice is stored as `snapshot_frequency` on the user record. It defaults to `monthly` when missing.
- It is a preference, not portfolio data, so it is not part of backups (like the 2FA settings).
- `valuation.next_snapshot_date(frequency, timestamps, on)` returns the first day on or after `on` when a snapshot is due. `valuation.snapshot_due(...)` is that date ≤ `on`. Both are pure.
- `GET /api/settings/snapshots` returns `{frequency, next_snapshot_on}`. `PUT /api/settings/snapshots` takes `{frequency}`; any other value gets 422.
- The dashboard response gains `snapshot_frequency` and `next_snapshot_on`, worked out after this visit's automatic snapshot.

## D3. Frontend (dashboard)

- **Selector:** next to "Save Snapshot", a small "Auto snapshot" selector with Weekly / Every 2 weeks / Monthly / Quarterly. Changing it saves straight away.
- **Caption:** below it, "Next automatic snapshot: <date>, saved when you open the dashboard on or after that day."
- **Empty-state hint:** names the chosen frequency.
- **Mobile:** the layout wraps cleanly.

## D4. Testing

- **Valuation:**
  - due and next date for each frequency;
  - day boundaries (6 vs 7 days, 13 vs 14);
  - quarter boundaries (31 Mar → 1 Apr);
  - year rollover;
  - future snapshots ignored.
- **API:**
  - the default is monthly;
  - PUT then GET returns the new value; a bad value gets 422;
  - one user's setting doesn't change another's;
  - the dashboard takes a weekly snapshot at 7 days but not at 6;
  - the dashboard returns the frequency and next date;
  - login is required.

---

# Part E — Warnings When a Price or NAV Source Fails

**Context:** Several features read outside sources:
- mutual fund NAVs and SIP NAV history (mfapi.in);
- NPS NAVs and the scheme list (npsnav.in);
- stock prices;
- the USD→INR rate.

Today a failure is mostly silent: values quietly fall back (purchase NAV, last price, at-cost contributions, the last known rate). The user asked for a dismissible warning in the UI whenever a source can't be reached or returns unusable data.

## E1. Backend: warnings travel with the response

- **Collector:** a request-scoped collector (`user_warnings.py`, built on a context variable) offers `warn(message)`. A middleware starts an empty list per request. If any warnings were added, it puts them on the response as `X-Warnings: <JSON array of strings>`, whatever the status code. Identical messages are sent once.
- **CORS:** `X-Warnings` is listed in `expose_headers`, so a cross-origin frontend can read it.
- **Messages:** plain English and short. Each names what failed, the source, and what the app does instead. They are encoded with `json.dumps(..., ensure_ascii=True)`, so the header stays ASCII.
- **Where warnings are raised** (only when a fetch was attempted and failed, never when cached data was used):

| Situation | Message (shape) |
|---|---|
| A mutual fund's NAV can't be fetched while saving | "Couldn't fetch the latest NAV for {fund} from mfapi.in; its value uses the purchase NAV until a refresh works." |
| Mutual fund list refresh (`?refresh_nav=true`): some funds failed | "Couldn't refresh the NAV for {n} fund(s) from mfapi.in: {names}. Their values use the last fetched NAV." |
| Single fund refresh failed | "Couldn't fetch the latest NAV for {fund} from mfapi.in; its value uses the last fetched NAV." |
| SIP installments can't be priced (on save or single-fund refresh) | "Couldn't price the SIP installments of {fund} with NAVs from mfapi.in; they count at cost until a refresh works." The list refresh sends one message naming at most 5 funds (not repeating funds already named in its NAV message). The whole header is kept under 2,000 bytes, ending with "…and N more warnings". |
| An NPS save couldn't price its schemes | "Couldn't fetch NPS NAVs from npsnav.in for {asset}; its contributions count at cost until a refresh works." |
| NPS refresh failed (the 502) | "Couldn't fetch NPS NAVs from npsnav.in right now; values use the last fetched NAVs." |
| NPS scheme list unavailable (the 502) | "Couldn't load the NPS scheme list from npsnav.in right now." |
| A stock price can't be fetched (create, refresh, list refresh, lookup) | "Couldn't fetch the price of {symbol}; its value uses the last known price." For the list refresh, one message naming the symbols. |
| The USD→INR rate can't be fetched from any source | "Couldn't fetch the USD→INR rate; US stock values use the last known rate." |

- **Live or fallback:** `exchange_service` reports whether the rate it returned came from a live source (or a fresh cache) or from the fallback. The app warns only for the fallback.

**Decision:** warnings travel in a response header rather than in each body, so no response shape changes and the frontend handles them in one place.

## E2. Frontend: dismissible toasts

- **API client:** an axios response interceptor reads `x-warnings` on successful and failed responses. It parses the JSON (malformed values are ignored) and publishes each message to a small notice hub (`utils/notices.js`).
- **Toasts:** a `<Notices />` component mounted once at the app root shows them as amber warning toasts stacked in the top-right corner, above modals. Each has an icon, the message and a dismiss (×) button. A message already on screen isn't shown twice.
- **Duration:** each toast hides on its own after 15 seconds unless dismissed sooner. The region is `aria-live="polite"` and works in dark mode.
- **Background refresh:** the NPS background refresh needs no extra code. Its failed requests carry the warning header, and repeats collapse into one toast.

**Decision:** toasts disappear after 15 s ("flash") and can be dismissed at any time. Per-card messages, such as the NPS refresh error on its card, stay where they are.

## E3. Testing

- **Backend:** for each source, a failure gives a response carrying the matching warning, and a success gives no header. Duplicate messages are sent once. The header is exposed to browsers on a CORS request.
- **Frontend:** the build. The controller's browser check stops a source and sees a toast, which can then be dismissed.
