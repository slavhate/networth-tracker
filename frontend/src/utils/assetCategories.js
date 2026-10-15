import {
  Banknote, PiggyBank, Building, Car, Wallet, Bitcoin, HelpCircle,
  Briefcase, Umbrella, Gem, Coins, ScrollText, BadgePercent,
} from 'lucide-react';

// Every asset category. `kind` picks the extra form fields: 'provident' (balance + contribution + rate),
// 'nps' (balance + contributions + investment options) or 'quantity' (quantity × price); others are a plain
// value. `unit` labels quantity holdings.
export const ASSET_CATEGORIES = [
  { value: 'cash', label: 'Cash & Savings', icon: Banknote, color: 'bg-green-100 text-green-600' },
  { value: 'investments', label: 'Investments', icon: PiggyBank, color: 'bg-blue-100 text-blue-600' },
  { value: 'real_estate', label: 'Real Estate', icon: Building, color: 'bg-purple-100 text-purple-600' },
  { value: 'vehicles', label: 'Vehicles', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'epf', label: 'EPF', icon: Briefcase, color: 'bg-indigo-100 text-indigo-600', kind: 'provident' },
  { value: 'ppf', label: 'PPF', icon: PiggyBank, color: 'bg-teal-100 text-teal-600', kind: 'provident' },
  { value: 'nps', label: 'NPS', icon: Umbrella, color: 'bg-sky-100 text-sky-600', kind: 'nps' },
  { value: 'retirement', label: 'Other retirement', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  { value: 'gold', label: 'Gold', icon: Gem, color: 'bg-amber-100 text-amber-600', kind: 'quantity', unit: 'g' },
  { value: 'sgb', label: 'Sovereign Gold Bonds', icon: Coins, color: 'bg-amber-100 text-amber-700', kind: 'quantity', unit: 'g' },
  { value: 'bonds', label: 'Bonds', icon: ScrollText, color: 'bg-slate-100 text-slate-600' },
  { value: 'esop_rsu', label: 'ESOP / RSU', icon: BadgePercent, color: 'bg-pink-100 text-pink-600', kind: 'quantity', unit: 'units' },
  { value: 'crypto', label: 'Cryptocurrency', icon: Bitcoin, color: 'bg-yellow-100 text-yellow-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

export const assetCategoryInfo = (value) =>
  ASSET_CATEGORIES.find((c) => c.value === value) || ASSET_CATEGORIES.find((c) => c.value === 'other');

const BUCKET_LABELS = { equities: 'Equities', bank_accounts: 'Bank Accounts', mutual_funds: 'Mutual Funds' };
const titleCase = (name) => name.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

// Label for a dashboard key: an asset category, a holdings bucket, or (title-cased) a liability category.
export const categoryLabel = (name) =>
  name ? (ASSET_CATEGORIES.find((c) => c.value === name)?.label ?? BUCKET_LABELS[name] ?? titleCase(name)) : '—';
