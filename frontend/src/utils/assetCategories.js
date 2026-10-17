import {
  Banknote, PiggyBank, Building, Car, Wallet, Bitcoin, HelpCircle,
  Briefcase, Umbrella, Gem, Coins, ScrollText,
} from 'lucide-react';

// Every asset category. `kind` picks the extra form fields: 'provident' (balance + contribution + rate),
// 'nps' (balance + contributions + investment options) or 'quantity' (quantity × price); others are a plain
// value. `unit` labels quantity holdings; `purities` are the grades a metal can have (the first is the default), with
// the fraction of pure metal each holds (as the server's models.METAL_PURITIES).
export const ASSET_CATEGORIES = [
  { value: 'cash', label: 'Cash & Savings', icon: Banknote, color: 'bg-green-100 text-green-600' },
  { value: 'real_estate', label: 'Real Estate', icon: Building, color: 'bg-purple-100 text-purple-600' },
  { value: 'vehicles', label: 'Vehicles', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'epf', label: 'EPF', icon: Briefcase, color: 'bg-indigo-100 text-indigo-600', kind: 'provident' },
  { value: 'ppf', label: 'PPF', icon: PiggyBank, color: 'bg-teal-100 text-teal-600', kind: 'provident' },
  { value: 'nps', label: 'NPS', icon: Umbrella, color: 'bg-sky-100 text-sky-600', kind: 'nps' },
  { value: 'retirement', label: 'Other retirement', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  {
    value: 'gold', label: 'Gold', icon: Gem, color: 'bg-amber-100 text-amber-600', kind: 'quantity', unit: 'g',
    purities: [{ value: '24K', fraction: 0.999 }, { value: '22K', fraction: 0.916 }, { value: '18K', fraction: 0.75 }],
  },
  {
    value: 'silver', label: 'Silver', icon: Coins, color: 'bg-zinc-200 text-zinc-600', kind: 'quantity', unit: 'g',
    purities: [{ value: '999', fraction: 0.999 }, { value: '925', fraction: 0.925 }],
  },
  { value: 'bonds', label: 'Bonds', icon: ScrollText, color: 'bg-slate-100 text-slate-600' },
  { value: 'crypto', label: 'Cryptocurrency', icon: Bitcoin, color: 'bg-yellow-100 text-yellow-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

export const assetCategoryInfo = (value) =>
  ASSET_CATEGORIES.find((c) => c.value === value) || ASSET_CATEGORIES.find((c) => c.value === 'other');

// A metal's grade: the one stored, or the category's default; null for a category without grades.
export const purityOf = (category, purity) => {
  const purities = assetCategoryInfo(category).purities;
  if (!purities) return null;
  return purities.find((p) => p.value === purity) ?? purities[0];
};

const BUCKET_LABELS = { equities: 'Equities', bank_accounts: 'Bank Accounts', mutual_funds: 'Mutual Funds' };
// Retired categories, still named in snapshots saved before their assets moved to Gold and Other
const RETIRED_LABELS = { investments: 'Investments', sgb: 'Sovereign Gold Bonds', esop_rsu: 'ESOP / RSU' };
const titleCase = (name) => name.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

// Label for a dashboard key: an asset category, a holdings bucket, or (title-cased) a liability category.
export const categoryLabel = (name) =>
  name
    ? (ASSET_CATEGORIES.find((c) => c.value === name)?.label ?? BUCKET_LABELS[name] ?? RETIRED_LABELS[name] ?? titleCase(name))
    : '—';
