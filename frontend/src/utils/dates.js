// Dates travel as "YYYY-MM-DD". Parse them as local dates: new Date("YYYY-MM-DD") is UTC and can show the previous day.
// Anything that doesn't start with YYYY-MM-DD gives null.
const parseIso = (iso) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso));
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? null : date;
};

const DAY_MS = 24 * 60 * 60 * 1000;

// Today's local date as YYYY-MM-DD
export const todayIso = () => {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

// A value that isn't a YYYY-MM-DD date is shown as it is rather than throwing
const formatWith = (options) => (iso) => {
  if (!iso) return '';
  const date = parseIso(iso);
  return date ? new Intl.DateTimeFormat('en-IN', options).format(date) : String(iso);
};

export const formatDate = formatWith({ day: 'numeric', month: 'short', year: 'numeric' });

export const formatMonthYear = formatWith({ month: 'short', year: 'numeric' });

// Whole local days from today to a YYYY-MM-DD date (negative once it has passed); null when there is no valid date
export const daysUntil = (iso) => {
  const date = iso ? parseIso(iso) : null;
  if (!date) return null;
  // Rounded: a daylight-saving change makes a local day 23 or 25 hours long
  return Math.round((date - parseIso(todayIso())) / DAY_MS);
};
