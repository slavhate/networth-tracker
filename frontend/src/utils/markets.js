// US listings are priced in USD and converted to INR wherever values are totalled.
export const USD_MARKETS = ['NASDAQ', 'NYSE'];
export const isUsdMarket = (market) => USD_MARKETS.includes(market);
// Used when the live USD→INR rate can't be fetched.
export const DEFAULT_USD_TO_INR = 83.5;
