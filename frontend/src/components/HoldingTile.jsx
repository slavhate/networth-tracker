import { Edit2, Trash2, TrendingUp, TrendingDown } from 'lucide-react';
import { TileAction } from './ItemTile';

// The tile the Equities and Mutual Funds pages show each holding in (laid out by ItemTileGrid): a header with a
// badge, name and the edit/delete actions; the current value with its gain or loss; a band of three stats; and an
// optional footer line. Tiles stretch to the tallest one in their grid row, and the stats band and footer sit at the
// bottom, so they line up across a row. min-w-0 lets the single phone column shrink to the screen: the one-line
// subtitle and footer truncate instead of widening the page.
export default function HoldingTile({
  badge,
  badgeColor,
  title,
  titleHint,
  subtitle,
  subtitleHint,
  titleClamp = false,
  itemLabel,
  onEdit,
  onDelete,
  value,
  valueHint,
  valueSuffix,
  gainPositive,
  gainText,
  stats,
  footer,
  footerHint,
}) {
  return (
    <div className="card !p-5 h-full min-w-0 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${badgeColor}`}>
          {badge}
        </div>
        <div className="flex-1 min-w-0">
          <h3
            className={`font-semibold text-gray-900 dark:text-white leading-snug ${titleClamp ? 'line-clamp-2 break-words' : 'truncate'}`}
            title={titleHint}
          >
            {title}
          </h3>
          {subtitle && (
            <div className="mt-0.5 text-sm text-gray-500 dark:text-gray-400 truncate" title={subtitleHint}>
              {subtitle}
            </div>
          )}
        </div>
        <div className="flex items-center shrink-0 -mr-2 -mt-1">
          <TileAction label={`Edit ${itemLabel}`} onClick={onEdit}>
            <Edit2 className="w-4 h-4" />
          </TileAction>
          <TileAction label={`Delete ${itemLabel}`} onClick={onDelete} danger>
            <Trash2 className="w-4 h-4" />
          </TileAction>
        </div>
      </div>

      <div>
        <p className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">Current value</p>
        <p className="flex items-baseline flex-wrap gap-x-2 min-w-0">
          <span className="text-2xl font-bold tabular-nums leading-tight text-gray-900 dark:text-white" title={valueHint}>
            {value}
          </span>
          {valueSuffix}
        </p>
        <p className={`mt-1 text-sm font-medium flex items-center gap-1 ${gainPositive
          ? 'text-green-600 dark:text-green-400'
          : 'text-red-600 dark:text-red-400'}`}
        >
          {gainPositive ? <TrendingUp className="w-4 h-4 shrink-0" /> : <TrendingDown className="w-4 h-4 shrink-0" />}
          <span className="truncate">{gainText}</span>
        </p>
      </div>

      <div className="mt-auto space-y-2">
        <dl className="grid grid-cols-3 gap-2 rounded-lg bg-gray-50 dark:bg-gray-900/40 px-3 py-2">
          {stats.map((stat) => (
            <div key={stat.label} className="min-w-0">
              <dt className="text-[11px] text-gray-400 dark:text-gray-500 truncate">{stat.label}</dt>
              <dd className="text-sm font-semibold tabular-nums text-gray-900 dark:text-white truncate" title={stat.hint}>
                {stat.value}
              </dd>
            </div>
          ))}
        </dl>
        {footer && <div className="text-xs text-gray-500 dark:text-gray-400 truncate" title={footerHint}>{footer}</div>}
      </div>
    </div>
  );
}
