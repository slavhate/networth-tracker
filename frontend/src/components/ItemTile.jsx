import { Children } from 'react';
import { Edit2, Trash2 } from 'lucide-react';
import { formatShortINR } from '../utils/indianNumbers';

// The tile the Assets, Liabilities, Bank Accounts and Insurance pages show each item in. A tile is as tall as its
// content; grid rows stretch every tile to the tallest one in the row, and the amount block sits at the bottom,
// so amounts line up across a row.
export function ItemTileGrid({ children }) {
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">{children}</div>;
}

export function TileAction({ label, onClick, danger = false, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`p-2 rounded-lg text-gray-400 dark:text-gray-500 transition-colors ${danger
        ? 'hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600 dark:hover:text-red-400'
        : 'hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200'}`}
    >
      {children}
    </button>
  );
}

export default function ItemTile({
  icon: Icon,
  iconColor,
  title,
  subtitle,
  badges,
  actions,
  onEdit,
  onDelete,
  itemLabel,
  amount,
  amountValue,
  amountLabel,
  amountClassName = 'text-gray-900 dark:text-white',
  privacyMode,
  footer,
  children,
}) {
  // The tile shows the short lakh/crore figure (₹40.5 Lakh); `amount` (the full figure, or the privacy mask) is the
  // hover text. In privacy mode the mask is shown and there is no hover text.
  const shown = privacyMode ? amount : formatShortINR(amountValue);
  const fullAmount = privacyMode ? undefined : amount;
  return (
    <div className="card !p-5 h-full min-w-0 flex hover:shadow-md transition-shadow">
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-start justify-between gap-2">
          <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 ${iconColor}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex items-center -mr-2 -mt-1">
            {actions}
            <TileAction label={`Edit ${itemLabel}`} onClick={onEdit}>
              <Edit2 className="w-4 h-4" />
            </TileAction>
            <TileAction label={`Delete ${itemLabel}`} onClick={onDelete} danger>
              <Trash2 className="w-4 h-4" />
            </TileAction>
          </div>
        </div>

        <h3 className="mt-3 font-semibold text-gray-900 dark:text-white leading-snug line-clamp-2 break-words" title={title}>
          {title}
        </h3>
        {subtitle && (
          <div
            className="mt-0.5 text-sm text-gray-500 dark:text-gray-400 truncate"
            title={typeof subtitle === 'string' ? subtitle : undefined}
          >
            {subtitle}
          </div>
        )}
        {badges && <div className="mt-2 flex flex-wrap gap-1.5">{badges}</div>}

        {Children.toArray(children).length > 0 && (
          <div className="mt-3 space-y-1.5 text-xs text-gray-500 dark:text-gray-400 break-words">{children}</div>
        )}

        <div className="mt-auto pt-4">
          <div className="border-t border-gray-100 dark:border-gray-700 pt-3">
            {amountLabel && (
              <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">{amountLabel}</p>
            )}
            <p className={`text-2xl font-bold tabular-nums leading-tight ${amountClassName}`} title={fullAmount}>{shown}</p>
            {footer && <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{footer}</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
