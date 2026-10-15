// Self-check for indianNumbers.js (the project has no test runner): node src/utils/indianNumbers.check.js
import assert from 'node:assert/strict';
import { formatCompactINR, amountInWords } from './indianNumbers.js';

const compact = [
  [12500000, '₹1.25 Cr'],
  [100000000, '₹10 Cr'],
  [450000, '₹4.5 L'],
  [100000, '₹1 L'],
  [85000, '₹85K'],
  [1000, '₹1K'],
  [950, '₹950'],
  [0, '₹0'],
  [-450000, '-₹4.5 L'],
  [99999, '₹1 L'],          // rounds up into the next unit instead of "₹100K"
  [9999999, '₹1 Cr'],
  [123456789, '₹12.35 Cr'],
  [99995, '₹1 L'],
  [999.5, '₹1K'],           // rounds up across the ₹1,000 boundary
  [999.4, '₹999'],
  [-0.4, '₹0'],             // no "-₹0"
  [-999.5, '-₹1K'],
  [12500000000, '₹1,250 Cr'],  // crore counts grouped en-IN
  [1e15, '₹10,00,00,000 Cr'],
  [NaN, '—'],
  [Infinity, '—'],
  [null, '—'],
  [undefined, '—'],
  ['', '—'],
  ['   ', '—'],
  ['12abc', '—'],
];
for (const [input, expected] of compact) assert.equal(formatCompactINR(input), expected, `formatCompactINR(${input})`);

const words = [
  [12500000, '₹1.25 Crore'],
  [10000000, '₹1 Crore'],
  [1250000, '₹12.5 Lakh'],
  [100000, '₹1 Lakh'],
  [85000, '₹85 Thousand'],
  [999, ''],
  [999.5, '₹1 Thousand'],
  [-0.4, ''],
  [12500000000, '₹1,250 Crore'],
  [0, ''],
  ['', ''],
  ['   ', ''],
  ['12abc', ''],
  [NaN, ''],
  [-2500000, '-₹25 Lakh'],
  ['1250000', '₹12.5 Lakh'],
];
for (const [input, expected] of words) assert.equal(amountInWords(input), expected, `amountInWords(${input})`);

console.log('indianNumbers: all checks passed');
