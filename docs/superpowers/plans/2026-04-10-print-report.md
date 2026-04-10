# Print-Friendly HTML Report Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Print Report" button to the sidebar that generates and downloads a self-contained HTML file with the user's complete financial snapshot across all sections.

**Architecture:** Two file changes only — a new `reportGenerator.js` utility that fetches all data and assembles the HTML, and a button wired into the existing `Layout.jsx` sidebar. No backend changes, no new npm dependencies.

**Tech Stack:** React 18, Vite, Tailwind CSS (sidebar only), vanilla HTML/CSS in generated report, lucide-react icons, existing axios API layer

**Project root:** `c:/Users/slavhate/networth-tracker`

---

### Task 1: Create `frontend/src/utils/reportGenerator.js`

**Files:**
- Create: `frontend/src/utils/reportGenerator.js`

- [ ] **Step 1: Create the file with the complete implementation**

Create `frontend/src/utils/reportGenerator.js` with the full contents below. This is a single exported async function plus all its helpers — no class, no state.

```javascript
import {
  assetsAPI,
  liabilitiesAPI,
  bankAccountsAPI,
  mutualFundsAPI,
  equitiesAPI,
  insurancesAPI,
  dashboardAPI,
  goalAPI,
} from '../api';

// ─── Formatters ──────────────────────────────────────────────────────────────

const MASK = '₹ ••••••';

function fmt(value, isPrivate) {
  if (isPrivate) return MASK;
  if (value == null || isNaN(value)) return '₹0';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function fmtNum(value, decimals = 2) {
  if (value == null || isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

function fmtCat(str) {
  if (!str) return '—';
  return str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function maskAccount(accountNumber) {
  if (!accountNumber) return '—';
  const s = String(accountNumber);
  return '••••' + s.slice(-4);
}

function sumField(arr, key) {
  return arr.reduce((acc, item) => acc + (Number(item[key]) || 0), 0);
}

// ─── CSS ─────────────────────────────────────────────────────────────────────

function buildCSS() {
  return `
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #fff; color: #111827;
      max-width: 900px; margin: 0 auto; padding: 32px 24px;
    }
    .report-header { text-align: center; padding: 0 0 28px; border-bottom: 2px solid #e2e8f0; margin-bottom: 32px; }
    .report-header h1 { font-size: 22px; font-weight: 700; color: #1e293b; }
    .report-header .date { font-size: 13px; color: #64748b; margin-top: 6px; }

    .summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 36px; }
    .summary-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }
    .summary-card .label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #64748b; }
    .summary-card .value { font-size: 17px; font-weight: 700; color: #1e293b; margin-top: 6px; word-break: break-all; }

    .goal-card { border: 1px solid #bfdbfe; border-radius: 8px; padding: 20px; margin-bottom: 36px; background: #eff6ff; }
    .goal-card .section-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #3b82f6; margin-bottom: 8px; }
    .goal-name { font-size: 17px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
    .goal-meta { font-size: 12px; color: #64748b; margin-bottom: 14px; }
    .progress-bg { height: 10px; background: #dbeafe; border-radius: 5px; overflow: hidden; margin-bottom: 6px; }
    .progress-fill { height: 100%; background: #3b82f6; border-radius: 5px; }
    .progress-pct { font-size: 12px; color: #3b82f6; font-weight: 600; }

    .section { margin-bottom: 36px; }
    .section-header {
      background: #1e293b; color: #fff;
      padding: 9px 14px; border-radius: 6px 6px 0 0;
      font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;
    }
    table { width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-top: none; }
    th {
      background: #f1f5f9; padding: 9px 12px; text-align: left;
      font-size: 10px; font-weight: 700; color: #475569;
      text-transform: uppercase; letter-spacing: 0.4px;
      border-bottom: 1px solid #e2e8f0;
    }
    th.num, td.num { text-align: right; }
    td { padding: 9px 12px; font-size: 13px; border-bottom: 1px solid #f1f5f9; color: #374151; }
    tr:last-child td { border-bottom: none; }
    tr:nth-child(even) td { background: #f8fafc; }
    tr.total td { font-weight: 700; background: #f1f5f9 !important; border-top: 2px solid #cbd5e1; color: #1e293b; }
    tr.no-data td { color: #94a3b8; font-style: italic; text-align: center; padding: 20px; }

    .footer { text-align: center; padding: 24px 0 0; border-top: 1px solid #e2e8f0; margin-top: 36px; font-size: 11px; color: #94a3b8; }

    @media (max-width: 600px) {
      .summary-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media print {
      body { padding: 0; max-width: 100%; }
      .section { page-break-before: always; }
      .report-header, .summary-grid, .goal-card { page-break-inside: avoid; }
      .footer { page-break-before: avoid; }
    }
  `;
}

// ─── Section Builders ────────────────────────────────────────────────────────

function buildHeader(dateStr) {
  return `
    <div class="report-header">
      <h1>Net Worth Financial Report</h1>
      <div class="date">${dateStr}</div>
    </div>`;
}

function buildSummaryCards(metrics, isPrivate) {
  const ratio = metrics.debt_to_asset_ratio != null
    ? (metrics.debt_to_asset_ratio * 100).toFixed(1) + '%'
    : '0.0%';
  return `
    <div class="summary-grid">
      <div class="summary-card">
        <div class="label">Net Worth</div>
        <div class="value">${fmt(metrics.net_worth, isPrivate)}</div>
      </div>
      <div class="summary-card">
        <div class="label">Total Assets</div>
        <div class="value">${fmt(metrics.total_assets, isPrivate)}</div>
      </div>
      <div class="summary-card">
        <div class="label">Total Liabilities</div>
        <div class="value">${fmt(metrics.total_liabilities, isPrivate)}</div>
      </div>
      <div class="summary-card">
        <div class="label">Debt-to-Asset Ratio</div>
        <div class="value">${isPrivate ? '••••' : ratio}</div>
      </div>
    </div>`;
}

function buildGoalCard(goal, netWorth, isPrivate) {
  if (!goal) return '';
  const target = goal.target_amount;
  const pct = target > 0 ? Math.min(100, (netWorth / target) * 100) : 0;
  const barWidth = isPrivate ? 0 : Math.min(100, pct);
  const pctLabel = isPrivate ? '••••' : pct.toFixed(1) + '%';
  return `
    <div class="goal-card">
      <div class="section-label">Net Worth Goal</div>
      <div class="goal-name">${goal.name || 'Net Worth Goal'}</div>
      <div class="goal-meta">Target: ${fmt(target, isPrivate)} &nbsp;·&nbsp; Current: ${fmt(netWorth, isPrivate)}</div>
      <div class="progress-bg"><div class="progress-fill" style="width:${barWidth}%"></div></div>
      <div class="progress-pct">${pctLabel} complete</div>
    </div>`;
}

function buildAssetsSection(assets, isPrivate) {
  const rows = assets.length === 0
    ? `<tr class="no-data"><td colspan="3">No entries</td></tr>`
    : assets.map((a) => `
        <tr>
          <td>${a.name}</td>
          <td>${fmtCat(a.category)}</td>
          <td class="num">${fmt(a.value, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="2">Total Assets</td>
          <td class="num">${fmt(sumField(assets, 'value'), isPrivate)}</td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Assets</div>
      <table>
        <thead><tr><th>Name</th><th>Category</th><th class="num">Value</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildLiabilitiesSection(liabilities, isPrivate) {
  const rows = liabilities.length === 0
    ? `<tr class="no-data"><td colspan="4">No entries</td></tr>`
    : liabilities.map((l) => `
        <tr>
          <td>${l.name}</td>
          <td>${fmtCat(l.category)}</td>
          <td class="num">${fmt(l.amount, isPrivate)}</td>
          <td class="num">${l.interest_rate != null ? l.interest_rate + '%' : '—'}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="2">Total Liabilities</td>
          <td class="num">${fmt(sumField(liabilities, 'amount'), isPrivate)}</td>
          <td></td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Liabilities</div>
      <table>
        <thead><tr><th>Name</th><th>Category</th><th class="num">Amount</th><th class="num">Interest Rate</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildBankAccountsSection(accounts, isPrivate) {
  const rows = accounts.length === 0
    ? `<tr class="no-data"><td colspan="4">No entries</td></tr>`
    : accounts.map((a) => `
        <tr>
          <td>${a.bank_name}</td>
          <td>${fmtCat(a.account_type)}</td>
          <td>${maskAccount(a.account_number)}</td>
          <td class="num">${fmt(a.balance, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="3">Total Balance</td>
          <td class="num">${fmt(sumField(accounts, 'balance'), isPrivate)}</td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Bank Accounts</div>
      <table>
        <thead><tr><th>Bank</th><th>Type</th><th>Account No.</th><th class="num">Balance</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildMutualFundsSection(funds, isPrivate) {
  const mfTotal = funds.reduce(
    (acc, f) => acc + (f.current_value != null ? f.current_value : (f.invested_amount || 0)),
    0
  );
  const rows = funds.length === 0
    ? `<tr class="no-data"><td colspan="5">No entries</td></tr>`
    : funds.map((f) => `
        <tr>
          <td>${f.fund_name}</td>
          <td class="num">${fmtNum(f.units, 3)}</td>
          <td class="num">${fmtNum(f.avg_nav)}</td>
          <td class="num">${f.current_nav != null ? fmtNum(f.current_nav) : '—'}</td>
          <td class="num">${fmt(f.current_value != null ? f.current_value : f.invested_amount, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="4">Total Value</td>
          <td class="num">${fmt(mfTotal, isPrivate)}</td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Mutual Funds</div>
      <table>
        <thead><tr><th>Fund Name</th><th class="num">Units</th><th class="num">Avg NAV</th><th class="num">Current NAV</th><th class="num">Current Value</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildEquitiesSection(equities, isPrivate) {
  const rows = equities.length === 0
    ? `<tr class="no-data"><td colspan="6">No entries</td></tr>`
    : equities.map((e) => `
        <tr>
          <td>
            <strong>${e.symbol}</strong>
            ${e.company_name ? `<br><small style="color:#64748b;font-size:11px">${e.company_name}</small>` : ''}
          </td>
          <td>${e.market}</td>
          <td class="num">${e.quantity}</td>
          <td class="num">${fmtNum(e.avg_buy_price)}</td>
          <td class="num">${e.current_price != null ? fmtNum(e.current_price) : '—'}</td>
          <td class="num">${fmt(e.current_value, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="5">Total Value</td>
          <td class="num">${fmt(sumField(equities, 'current_value'), isPrivate)}</td>
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

function buildInsurancesSection(insurances, isPrivate) {
  const rows = insurances.length === 0
    ? `<tr class="no-data"><td colspan="5">No entries</td></tr>`
    : insurances.map((ins) => `
        <tr>
          <td>${ins.policy_name}</td>
          <td>${fmtCat(ins.insurance_type)}</td>
          <td>${ins.provider}</td>
          <td class="num">${fmt(ins.premium, isPrivate)}</td>
          <td>${fmtCat(ins.premium_frequency)}</td>
        </tr>`).join('');
  return `
    <div class="section">
      <div class="section-header">Insurances</div>
      <table>
        <thead><tr><th>Policy Name</th><th>Type</th><th>Insurer</th><th class="num">Premium</th><th>Frequency</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildFooter(timestamp) {
  return `<div class="footer">Generated by Net Worth Tracker &nbsp;·&nbsp; ${timestamp}</div>`;
}

// ─── Main Export ─────────────────────────────────────────────────────────────

export async function generateReport(isPrivate) {
  const [
    dashRes,
    assetsRes,
    liabRes,
    bankRes,
    mfRes,
    eqRes,
    insRes,
    goalRes,
  ] = await Promise.all([
    dashboardAPI.getMetrics(),
    assetsAPI.getAll(),
    liabilitiesAPI.getAll(),
    bankAccountsAPI.getAll(),
    mutualFundsAPI.getAll(),
    equitiesAPI.getAll(),
    insurancesAPI.getAll(),
    goalAPI.get().catch(() => ({ data: null })), // 404 when no goal set — treat as null
  ]);

  const metrics = dashRes.data;
  const assets = assetsRes.data;
  const liabilities = liabRes.data;
  const accounts = bankRes.data;
  const funds = mfRes.data;
  const equities = eqRes.data;
  const insurances = insRes.data;
  const goal = goalRes.data;

  const now = new Date();
  const dateStr = now.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
  const timestamp = now.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Net Worth Report · ${dateStr}</title>
  <style>${buildCSS()}</style>
</head>
<body>
  ${buildHeader(dateStr)}
  ${buildSummaryCards(metrics, isPrivate)}
  ${buildGoalCard(goal, metrics.net_worth, isPrivate)}
  ${buildAssetsSection(assets, isPrivate)}
  ${buildLiabilitiesSection(liabilities, isPrivate)}
  ${buildBankAccountsSection(accounts, isPrivate)}
  ${buildMutualFundsSection(funds, isPrivate)}
  ${buildEquitiesSection(equities, isPrivate)}
  ${buildInsurancesSection(insurances, isPrivate)}
  ${buildFooter(timestamp)}
</body>
</html>`;

  return html;
}
```

- [ ] **Step 2: Verify the file was created correctly**

```bash
ls frontend/src/utils/reportGenerator.js
```

Expected: file exists (no error).

---

### Task 2: Update `frontend/src/components/Layout.jsx`

**Files:**
- Modify: `frontend/src/components/Layout.jsx`

- [ ] **Step 1: Add `Printer` to the lucide-react import**

In `frontend/src/components/Layout.jsx`, find line 7 (`import {`) and add `Printer` to the icon list. Replace:

```javascript
import { 
  LayoutDashboard, 
  Wallet, 
  CreditCard, 
  LogOut, 
  Menu,
  X,
  Sun,
  Moon,
  Landmark,
  Shield,
  TrendingUp,
  BarChart3,
  Eye,
  EyeOff,
  Clock,
  Download,
  Upload,
  User,
  AlertCircle,
  CheckCircle
} from 'lucide-react';
```

With:

```javascript
import { 
  LayoutDashboard, 
  Wallet, 
  CreditCard, 
  LogOut, 
  Menu,
  X,
  Sun,
  Moon,
  Landmark,
  Shield,
  TrendingUp,
  BarChart3,
  Eye,
  EyeOff,
  Clock,
  Download,
  Upload,
  User,
  AlertCircle,
  CheckCircle,
  Printer
} from 'lucide-react';
```

- [ ] **Step 2: Add `generateReport` import**

After the `import { exportAPI } from '../api';` line (line 5), add:

```javascript
import { generateReport } from '../utils/reportGenerator';
```

- [ ] **Step 3: Add `reporting` and `printError` state**

After the existing state declarations (after line 51 `const fileInputRef = useRef(null);`), add:

```javascript
  const [reporting, setReporting] = useState(false);
  const [printError, setPrintError] = useState(null);
```

- [ ] **Step 4: Add `handlePrintReport` function**

After the `handleExport` function (after line 76's closing `}`), add:

```javascript
  const handlePrintReport = async () => {
    try {
      setReporting(true);
      setPrintError(null);
      const html = await generateReport(privacyMode);
      const blob = new Blob([html], { type: 'text/html' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `networth-report-${new Date().toISOString().slice(0, 10)}.html`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Print report failed:', err);
      setPrintError('Report generation failed. Please try again.');
      setTimeout(() => setPrintError(null), 4000);
    } finally {
      setReporting(false);
    }
  };
```

- [ ] **Step 5: Add the Print Report button and error display to the sidebar**

Find the `{/* Backup & Restore Row */}` block in the JSX (around line 267). Add the print error message and button **between** the Backup/Restore grid and the Logout button. Replace:

```jsx
              {/* Backup & Restore Row */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleExport}
                  disabled={exporting}
                  className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800 transition-colors duration-150 disabled:opacity-50"
                  title="Export data for backup"
                >
                  <Download className={`w-3.5 h-3.5 ${exporting ? 'animate-bounce' : ''}`} />
                  <span>{exporting ? 'Saving...' : 'Backup'}</span>
                </button>
                <button
                  onClick={handleRestoreClick}
                  disabled={importing}
                  className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-medium bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/50 border border-green-200 dark:border-green-800 transition-colors duration-150 disabled:opacity-50"
                  title="Restore data from backup"
                >
                  <Upload className={`w-3.5 h-3.5 ${importing ? 'animate-spin' : ''}`} />
                  <span>{importing ? 'Restoring...' : 'Restore'}</span>
                </button>
              </div>
              
              {/* Logout */}
```

With:

```jsx
              {/* Backup & Restore Row */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleExport}
                  disabled={exporting}
                  className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800 transition-colors duration-150 disabled:opacity-50"
                  title="Export data for backup"
                >
                  <Download className={`w-3.5 h-3.5 ${exporting ? 'animate-bounce' : ''}`} />
                  <span>{exporting ? 'Saving...' : 'Backup'}</span>
                </button>
                <button
                  onClick={handleRestoreClick}
                  disabled={importing}
                  className="flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-medium bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/50 border border-green-200 dark:border-green-800 transition-colors duration-150 disabled:opacity-50"
                  title="Restore data from backup"
                >
                  <Upload className={`w-3.5 h-3.5 ${importing ? 'animate-spin' : ''}`} />
                  <span>{importing ? 'Restoring...' : 'Restore'}</span>
                </button>
              </div>

              {/* Print Error Message */}
              {printError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400">
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="truncate">{printError}</span>
                </div>
              )}

              {/* Print Report */}
              <button
                onClick={handlePrintReport}
                disabled={reporting}
                className="w-full flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg text-xs font-medium bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50 border border-purple-200 dark:border-purple-800 transition-colors duration-150 disabled:opacity-50"
                title="Download print-friendly HTML report"
              >
                <Printer className={`w-3.5 h-3.5 ${reporting ? 'animate-pulse' : ''}`} />
                <span>{reporting ? 'Generating...' : 'Print Report'}</span>
              </button>
              
              {/* Logout */}
```

- [ ] **Step 6: Commit**

```bash
cd c:/Users/slavhate/networth-tracker
git add frontend/src/utils/reportGenerator.js frontend/src/components/Layout.jsx
git commit -m "feat: add print-friendly HTML report export"
```

---

### Task 3: Verify in Browser

- [ ] **Step 1: Start the frontend dev server**

```bash
cd c:/Users/slavhate/networth-tracker/frontend
npm run dev
```

Expected: Vite dev server starts, app available at http://localhost:5173

- [ ] **Step 2: Log in and click Print Report**

Open http://localhost:5173, log in with demo/password123.

In the sidebar, scroll to the bottom — you should see a purple "Print Report" button below the Backup/Restore row.

Click it. Expected: button shows "Generating..." briefly, then browser downloads `networth-report-YYYY-MM-DD.html`.

- [ ] **Step 3: Open the downloaded file and verify all sections**

Open the downloaded `.html` file in a browser. Verify:
- Header shows today's date
- Summary strip shows 4 cards: Net Worth, Total Assets, Total Liabilities, Debt-to-Asset Ratio
- Goal card appears (if a goal is set in the demo data)
- All 6 data sections appear: Assets, Liabilities, Bank Accounts, Mutual Funds, Equities, Insurances
- Each section has a dark header band and a data table
- Sections with data show rows and a bold subtotal row at the bottom
- Footer shows generation timestamp

- [ ] **Step 4: Test privacy mode**

Back in the app, click the Privacy toggle (amber "Privacy On" button in the sidebar) to enable privacy mode.

Click Print Report again. Open the downloaded file.

Expected: all currency values show `₹ ••••••`, debt ratio shows `••••`, progress bar is empty (0%), percentage shows `••••`.

- [ ] **Step 5: Test browser print**

With the report HTML file open, press Ctrl+P (or Cmd+P on Mac).

Expected: clean print preview — no sidebar or browser chrome visible in the report, each section starts on a new page.

- [ ] **Step 6: Build and push Docker image**

Once verified working in dev, rebuild the frontend Docker image and push:

```bash
cd /mnt/c/Users/slavhate/networth-tracker
docker build -t shri32msi/networth-tracker:frontend --build-arg VITE_API_URL= ./frontend
docker push shri32msi/networth-tracker:frontend
```

Expected: build succeeds, image pushed to Docker Hub.
