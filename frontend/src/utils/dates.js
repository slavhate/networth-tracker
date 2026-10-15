// Dates travel as "YYYY-MM-DD". Parse them as local dates: new Date("YYYY-MM-DD") is UTC and can show the previous day.
const parseIso = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};

// Today's local date as YYYY-MM-DD
export const todayIso = () => {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

export const formatDate = (iso) =>
  iso ? new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }).format(parseIso(iso)) : '';

export const formatMonthYear = (iso) =>
  iso ? new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' }).format(parseIso(iso)) : '';
