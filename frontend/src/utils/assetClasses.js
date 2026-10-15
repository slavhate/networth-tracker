// Asset classes in display order, with labels and fixed chart colours.
export const ASSET_CLASSES = [
  { key: 'equity', label: 'Equity', color: '#0ea5e9' },
  { key: 'debt', label: 'Debt', color: '#22c55e' },
  { key: 'gold', label: 'Gold', color: '#f59e0b' },
  { key: 'real_estate', label: 'Real Estate', color: '#8b5cf6' },
  { key: 'cash', label: 'Cash', color: '#06b6d4' },
  { key: 'other', label: 'Other', color: '#94a3b8' },
];

export const assetClassLabel = (key) => ASSET_CLASSES.find((c) => c.key === key)?.label ?? key;
