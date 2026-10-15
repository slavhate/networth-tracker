import { amountInWords } from '../utils/indianNumbers';

// A live "= ₹12.5 Lakh" hint under a rupee amount input; nothing below ₹1,000 or for an empty/invalid value.
export default function AmountHint({ value, className = 'text-xs text-gray-500 dark:text-gray-400 mt-1' }) {
  const words = amountInWords(value);
  if (!words) return null;
  return <p className={className} aria-live="polite">= {words}</p>;
}
