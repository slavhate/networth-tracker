// Round up to the paisa, like valuation._round_up_to_paisa on the server: the loan then clears on its
// last anniversary instead of leaving a stub payment. toFixed(6) absorbs float noise before the ceil.
const roundUpToPaisa = (amount) => Math.ceil(Number((amount * 100).toFixed(6))) / 100;

// Monthly EMI that clears `principal` in `months` at `annualRate` % (reducing balance).
// Same formula as valuation.emi_for_tenure.
export const emiForTenure = (principal, annualRate, months) => {
  const r = annualRate / 1200;
  if (r === 0) return roundUpToPaisa(principal / months);
  const growthMinusOne = Math.expm1(months * Math.log1p(r)); // (1 + r) ** months - 1, exact even for tiny r
  return roundUpToPaisa((principal * r * (growthMinusOne + 1)) / growthMinusOne);
};
