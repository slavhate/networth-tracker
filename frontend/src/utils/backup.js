// Sections of a backup file, in the order the restore dialog lists them.
export const BACKUP_SECTIONS = [
  { key: 'assets', label: 'Assets' },
  { key: 'liabilities', label: 'Liabilities' },
  { key: 'bank_accounts', label: 'Bank accounts' },
  { key: 'insurances', label: 'Insurances' },
  { key: 'mutual_funds', label: 'Mutual funds' },
  { key: 'equities', label: 'Equities' },
  { key: 'snapshots', label: 'Snapshots' },
];

export const countOf = (data, key) => (Array.isArray(data?.[key]) ? data[key].length : 0);

// Same shape check the server makes first: a JSON object with at least one known section.
export const looksLikeBackup = (data) =>
  data !== null && typeof data === 'object' && !Array.isArray(data) &&
  [...BACKUP_SECTIONS.map((s) => s.key), 'goal'].some((key) => key in data);
