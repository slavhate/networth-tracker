// Indian numbering units for rupee amounts: crore (1,00,00,000), lakh (1,00,000) and thousand.
// Full amounts stay the primary display (en-IN grouping, e.g. ₹1,09,036); these helpers add a short form.

const TIERS = [
  { value: 1e7, short: 'Cr', word: 'Crore' },
  { value: 1e5, short: 'L', word: 'Lakh' },
  { value: 1e3, short: 'K', word: 'Thousand' },
];

// Up to 2 decimals, trailing zeros dropped, en-IN grouping for big crore counts: 1.50 -> "1.5", 1250 -> "1,250"
const UNIT_FORMAT = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });
const round2 = (n) => Number(n.toFixed(2));

// A number, or null for null/undefined/blank strings and anything non-finite ('12abc', NaN, Infinity)
const toNumber = (value) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string' && value.trim() === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

// How an absolute amount reads after rounding: { tier, amount } with the amount in that tier's unit, or
// { tier: null, amount } for whole rupees below ₹1,000. A value that rounds up to the next unit moves into it:
// 999.5 -> 1 thousand, 99,999 -> 1 lakh, 99,99,999 -> 1 crore.
const split = (abs) => {
  let tier = null;
  let amount = Math.round(abs);
  for (let i = TIERS.length - 1; i >= 0; i -= 1) {
    const candidate = TIERS[i];
    // Compare the value as it would be shown in the smaller unit, so rounding up promotes it
    const shown = tier ? amount * tier.value : amount;
    if (shown >= candidate.value) {
      tier = candidate;
      amount = round2(abs / candidate.value);
    }
  }
  return { tier, amount };
};

// "₹1.25 Cr", "₹1,250 Cr", "₹4.5 L", "₹85K", "₹950"; negatives get a leading minus (never "-₹0");
// a non-number gives "—"
export function formatCompactINR(value) {
  const n = toNumber(value);
  if (n === null) return '—';
  const { tier, amount } = split(Math.abs(n));
  const sign = n < 0 && amount !== 0 ? '-' : '';
  if (!tier) return `${sign}₹${amount}`;
  const text = UNIT_FORMAT.format(amount);
  return tier.short === 'K' ? `${sign}₹${text}K` : `${sign}₹${text} ${tier.short}`;
}

// "₹1.25 Crore", "₹1,250 Crore", "₹12.5 Lakh", "₹85 Thousand"; '' below ₹1,000 or for a non-number
export function amountInWords(value) {
  const n = toNumber(value);
  if (n === null) return '';
  const { tier, amount } = split(Math.abs(n));
  if (!tier) return '';
  return `${n < 0 ? '-' : ''}₹${UNIT_FORMAT.format(amount)} ${tier.word}`;
}

const FULL_INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });

// A headline figure: "₹1.25 Crore", "₹12.5 Lakh"; below ₹1 lakh the full amount ("₹85,000"), already short;
// a non-number gives "—"
export function formatShortINR(value) {
  const n = toNumber(value);
  if (n === null) return '—';
  const { tier } = split(Math.abs(n));
  return tier && tier.short !== 'K' ? amountInWords(n) : FULL_INR.format(Math.round(n) || 0);
}
