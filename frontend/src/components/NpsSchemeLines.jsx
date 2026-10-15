import { RefreshCw } from 'lucide-react';
import { formatDate } from '../utils/dates';

// An NPS asset's schemes on its card: units × NAV and value when priced, otherwise the allocation only.
export default function NpsSchemeLines({ asset, formatCurrency, privacyMode, refreshing, refreshError, onRefresh }) {
  const priced = Boolean(asset.nps_priced_through);
  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {asset.nps_schemes.map((s) => (
          <div key={s.scheme_code} className="text-xs text-gray-500 dark:text-gray-400">
            <div className="flex items-baseline gap-2">
              <span className="min-w-0 flex-1 truncate font-medium text-gray-600 dark:text-gray-300" title={s.scheme_name}>
                {s.scheme_name}
              </span>
              <span className="shrink-0 tabular-nums">{s.allocation_pct}%</span>
            </div>
            {priced && s.current_units != null && (
              <div className="tabular-nums text-gray-400 dark:text-gray-500">
                {privacyMode ? '••' : s.current_units.toLocaleString('en-IN', { maximumFractionDigits: 4 })} units × ₹{s.nav}
                {s.nav_date ? ` (${formatDate(s.nav_date)})` : ''} = {formatCurrency(s.current_value)}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
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
      {refreshError && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">{refreshError}</p>
      )}
    </div>
  );
}
