import { Plus, Trash2 } from 'lucide-react';

export const MAX_NPS_SCHEMES = 10;
export const emptySchemeRow = () => ({ scheme_code: '', scheme_name: '', allocation_pct: '', units: '' });

const allocationTotal = (rows) => rows.reduce((sum, r) => sum + (parseFloat(r.allocation_pct) || 0), 0);

// The same rule as the API: the allocations may be off from 100 by at most 0.01 (so 33.33 + 33.33 + 33.33 is fine).
const offFromHundred = (total) => Math.round(Math.abs(total - 100) * 1e6) / 1e6 > 0.01;

// Problems that stop the form from saving, or null.
export function schemeRowsError(rows) {
  if (rows.length === 0) return null;
  if (rows.some((r) => !r.scheme_code)) return 'Pick each scheme from the list';
  if (new Set(rows.map((r) => r.scheme_code)).size !== rows.length) return 'Each scheme can be added once';
  if (rows.some((r) => !Number.isFinite(parseFloat(r.allocation_pct)))) return 'Enter the % of new money for each scheme';
  if (offFromHundred(allocationTotal(rows))) return 'Allocations must add up to 100%';
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
  const total = allocationTotal(rows);
  const problem = schemeRowsError(rows);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="label !mb-0">Investment options (Optional)</label>
        {rows.length > 0 && (
          <span
            className={`text-xs font-medium ${offFromHundred(total) ? 'text-red-600 dark:text-red-400' : 'text-green-600 dark:text-green-400'}`}
          >
            Total {Math.round(total * 100) / 100}%
          </span>
        )}
      </div>
      {problem && (
        <p className="text-xs text-red-600 dark:text-red-400">{problem}</p>
      )}
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
            aria-label="Scheme"
            placeholder="Search schemes, e.g., scheme E tier I"
            value={row.scheme_name}
            onChange={(e) => pickByName(index, e.target.value)}
          />
          <div className="grid grid-cols-[1fr_1fr_auto] gap-2 items-center">
            <input
              type="number"
              className="input"
              aria-label="% of new money"
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
              aria-label="Units"
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
