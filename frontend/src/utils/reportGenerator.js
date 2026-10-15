import {
  assetsAPI,
  liabilitiesAPI,
  bankAccountsAPI,
  mutualFundsAPI,
  equitiesAPI,
  insurancesAPI,
  dashboardAPI,
  goalAPI,
  exchangeAPI,
} from '../api';
import { DEFAULT_USD_TO_INR, isUsdMarket } from './markets';
import { amountInWords } from './indianNumbers';
import { categoryLabel } from './assetCategories';
import { ASSET_CLASSES, assetClassLabel } from './assetClasses';

// ─── Formatters ──────────────────────────────────────────────────────────────

const MASK = '₹ ••••••';
const USD_MASK = '$ ••••••';

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

function fmtNum(value, decimals = 2) {
  if (value == null || isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

// Units, quantities and per-unit prices: hidden in a private report, since units x price gives the value
const NUM_MASK = '••';

function fmtNumPrivate(value, isPrivate, decimals = 2) {
  return isPrivate ? NUM_MASK : fmtNum(value, decimals);
}

function fmtCat(str) {
  if (!str) return '—';
  return escapeHtml(str.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()));
}

// Deposits read as their abbreviations; other account types as their category label.
function fmtAccountType(type) {
  if (type === 'fd' || type === 'rd') return type.toUpperCase();
  return fmtCat(type);
}

function maskAccount(accountNumber) {
  if (!accountNumber) return '—';
  const s = String(accountNumber);
  // A number of 4 characters or fewer would be shown whole
  return s.length <= 4 ? '••••' : '••••' + s.slice(-4);
}

function sumField(arr, key) {
  return arr.reduce((acc, item) => acc + (Number(item[key]) || 0), 0);
}

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
    .summary-card .words { font-size: 11px; color: #64748b; margin-top: 2px; }

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

// The amount in lakh/crore words under a full amount (e.g. ₹12.5 Lakh); nothing in a private report or below ₹1,000
function wordsLine(value, isPrivate) {
  const words = isPrivate ? '' : amountInWords(value);
  return words ? `<div class="words">${escapeHtml(words)}</div>` : '';
}

function buildSummaryCards(metrics, isPrivate) {
  const ratio = metrics.debt_to_asset_ratio != null
    ? metrics.debt_to_asset_ratio.toFixed(1) + '%'
    : '0.0%';
  return `
    <div class="summary-grid">
      <div class="summary-card">
        <div class="label">Net Worth</div>
        <div class="value">${fmt(metrics.net_worth, isPrivate)}</div>
        ${wordsLine(metrics.net_worth, isPrivate)}
      </div>
      <div class="summary-card">
        <div class="label">Total Assets</div>
        <div class="value">${fmt(metrics.total_assets, isPrivate)}</div>
        ${wordsLine(metrics.total_assets, isPrivate)}
      </div>
      <div class="summary-card">
        <div class="label">Total Liabilities</div>
        <div class="value">${fmt(metrics.total_liabilities, isPrivate)}</div>
        ${wordsLine(metrics.total_liabilities, isPrivate)}
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
      <div class="goal-name">${escapeHtml(goal.name) || 'Net Worth Goal'}</div>
      <div class="goal-meta">Target: ${fmt(target, isPrivate)}${!isPrivate && amountInWords(target) ? ` (${escapeHtml(amountInWords(target))})` : ''} &nbsp;·&nbsp; Current: ${fmt(netWorth, isPrivate)}${!isPrivate && amountInWords(netWorth) ? ` (${escapeHtml(amountInWords(netWorth))})` : ''}</div>
      <div class="progress-bg"><div class="progress-fill" style="width:${barWidth}%"></div></div>
      <div class="progress-pct">${pctLabel} complete</div>
    </div>`;
}

// One row per class present in metrics.assets_by_class, in display order; any unknown key follows the known classes.
function buildAllocationSection(metrics, isPrivate) {
  const byClass = metrics.assets_by_class || {};
  const knownKeys = ASSET_CLASSES.map((c) => c.key);
  const keys = [...knownKeys.filter((k) => k in byClass), ...Object.keys(byClass).filter((k) => !knownKeys.includes(k))];
  const entries = keys.map((key) => ({ key, value: Number(byClass[key]) || 0 }));
  const total = entries.reduce((acc, e) => acc + e.value, 0);
  const share = (value) => (isPrivate ? '••••' : (total === 0 ? '—' : (value / total * 100).toFixed(1) + '%'));
  const rows = entries.length === 0
    ? `<tr class="no-data"><td colspan="3">No entries</td></tr>`
    : entries.map((e) => `
        <tr>
          <td>${escapeHtml(assetClassLabel(e.key))}</td>
          <td class="num">${fmt(e.value, isPrivate)}</td>
          <td class="num">${share(e.value)}</td>
        </tr>`).join('');
  return `
    <div class="section">
      <div class="section-header">Asset Allocation</div>
      <table>
        <thead><tr><th>Class</th><th class="num">Value</th><th class="num">Share</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildAssetsSection(assets, isPrivate) {
  const rows = assets.length === 0
    ? `<tr class="no-data"><td colspan="3">No entries</td></tr>`
    : assets.map((a) => `
        <tr>
          <td>${escapeHtml(a.name)}</td>
          <td>${escapeHtml(categoryLabel(a.category))}</td>
          <td class="num">${fmt(a.current_value, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="2">Total Assets</td>
          <td class="num">${fmt(sumField(assets, 'current_value'), isPrivate)}</td>
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
    ? `<tr class="no-data"><td colspan="5">No entries</td></tr>`
    : liabilities.map((l) => `
        <tr>
          <td>${escapeHtml(l.name)}</td>
          <td>${fmtCat(l.category)}</td>
          <td class="num">${fmt(l.outstanding, isPrivate)}</td>
          <td class="num">${l.interest_rate != null ? l.interest_rate + '%' : '—'}</td>
          <td class="num">${l.emi != null ? fmt(l.emi, isPrivate) : '—'}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="2">Total Liabilities</td>
          <td class="num">${fmt(sumField(liabilities, 'outstanding'), isPrivate)}</td>
          <td></td>
          <td></td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Liabilities</div>
      <table>
        <thead><tr><th>Name</th><th>Category</th><th class="num">Outstanding</th><th class="num">Interest Rate</th><th class="num">EMI</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function buildBankAccountsSection(accounts, isPrivate) {
  const rows = accounts.length === 0
    ? `<tr class="no-data"><td colspan="4">No entries</td></tr>`
    : accounts.map((a) => `
        <tr>
          <td>${escapeHtml(a.bank_name)}</td>
          <td>${fmtAccountType(a.account_type)}</td>
          <td>${escapeHtml(maskAccount(a.account_number))}</td>
          <td class="num">${fmt(a.current_value, isPrivate)}</td>
        </tr>`).join('') + `
        <tr class="total">
          <td colspan="3">Total Value</td>
          <td class="num">${fmt(sumField(accounts, 'current_value'), isPrivate)}</td>
        </tr>`;
  return `
    <div class="section">
      <div class="section-header">Bank Accounts</div>
      <table>
        <thead><tr><th>Bank</th><th>Type</th><th>Account No.</th><th class="num">Value</th></tr></thead>
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
          <td>${escapeHtml(f.fund_name)}</td>
          <td class="num">${fmtNumPrivate(f.units, isPrivate, 3)}</td>
          <td class="num">${fmtNumPrivate(f.avg_nav, isPrivate)}</td>
          <td class="num">${isPrivate ? NUM_MASK : f.current_nav != null ? fmtNum(f.current_nav) : '—'}</td>
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

function buildEquitiesSection(equities, usdToInr, isPrivate) {
  const isUsd = (e) => isUsdMarket(e.market);
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
          <td class="num">${isPrivate ? NUM_MASK : escapeHtml(e.quantity)}</td>
          <td class="num">${isUsd(e) ? fmtUsd(e.avg_buy_price, isPrivate) : fmtNumPrivate(e.avg_buy_price, isPrivate)}</td>
          <td class="num">${isPrivate ? NUM_MASK : e.current_price != null ? (isUsd(e) ? fmtUsd(e.current_price, false) : fmtNum(e.current_price)) : '—'}</td>
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

function buildInsurancesSection(insurances, isPrivate) {
  const rows = insurances.length === 0
    ? `<tr class="no-data"><td colspan="6">No entries</td></tr>`
    : insurances.map((ins) => `
        <tr>
          <td>${escapeHtml(ins.policy_name)}</td>
          <td>${fmtCat(ins.insurance_type)}</td>
          <td>${escapeHtml(ins.provider)}</td>
          <td class="num">${fmt(ins.sum_assured, isPrivate)}</td>
          <td class="num">${fmt(ins.premium, isPrivate)}</td>
          <td>${fmtCat(ins.premium_frequency)}</td>
        </tr>`).join('');
  return `
    <div class="section">
      <div class="section-header">Insurances</div>
      <table>
        <thead><tr><th>Policy Name</th><th>Type</th><th>Insurer</th><th class="num">Coverage</th><th class="num">Premium</th><th>Frequency</th></tr></thead>
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
    rateRes,
  ] = await Promise.all([
    dashboardAPI.getMetrics(),
    assetsAPI.getAll(),
    liabilitiesAPI.getAll(),
    bankAccountsAPI.getAll(),
    mutualFundsAPI.getAll(),
    equitiesAPI.getAll(),
    insurancesAPI.getAll(),
    goalAPI.get().catch(() => ({ data: null })), // 404 when no goal set — treat as null
    exchangeAPI.getRate().catch(() => ({ data: null })), // fall back to the default rate
  ]);

  const metrics = dashRes.data;
  const assets = assetsRes.data;
  const liabilities = liabRes.data;
  const accounts = bankRes.data;
  const funds = mfRes.data;
  const equities = eqRes.data;
  const insurances = insRes.data;
  const goal = goalRes.data;
  const usdToInr = rateRes.data?.usd_to_inr || DEFAULT_USD_TO_INR;

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
  ${buildAllocationSection(metrics, isPrivate)}
  ${buildAssetsSection(assets, isPrivate)}
  ${buildLiabilitiesSection(liabilities, isPrivate)}
  ${buildBankAccountsSection(accounts, isPrivate)}
  ${buildMutualFundsSection(funds, isPrivate)}
  ${buildEquitiesSection(equities, usdToInr, isPrivate)}
  ${buildInsurancesSection(insurances, isPrivate)}
  ${buildFooter(timestamp)}
</body>
</html>`;

  return html;
}
