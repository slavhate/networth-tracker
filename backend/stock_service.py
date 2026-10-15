"""
Stock price fetching service using Yahoo Finance API directly
"""
import requests
from typing import Optional, Dict
import logging
import time
import random

logger = logging.getLogger(__name__)

# Browser-like headers
_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://finance.yahoo.com/'
}

# Cache to store prices temporarily
_price_cache: Dict[str, Dict] = {}
_cache_timeout = 300  # 5 minutes

def get_yahoo_symbol(symbol: str, market: str) -> str:
    """Convert symbol to Yahoo Finance format based on market"""
    symbol = symbol.upper().strip()
    
    if market == "NSE":
        return f"{symbol}.NS"
    elif market == "BSE":
        return f"{symbol}.BO"
    elif market in ("NASDAQ", "NYSE"):
        return symbol  # US listings don't need a suffix
    else:
        return symbol

def _fetch_price_direct(yahoo_symbol: str) -> Optional[float]:
    """Fetch price using Yahoo Finance Chart API directly"""
    try:
        # Yahoo Finance Chart API - more reliable than scraping
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        params = {
            'interval': '1d',
            'range': '5d'
        }
        
        response = requests.get(url, headers=_headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            chart = data.get('chart', {})
            result = chart.get('result', [])
            
            if result:
                meta = result[0].get('meta', {})
                price = meta.get('regularMarketPrice')
                if price:
                    return float(price)
                
                # Fallback to last close
                indicators = result[0].get('indicators', {})
                quote = indicators.get('quote', [{}])[0]
                closes = quote.get('close', [])
                if closes:
                    # Get last non-None close price
                    for close in reversed(closes):
                        if close is not None:
                            return float(close)
        
        logger.debug(f"Chart API failed for {yahoo_symbol}: status {response.status_code}")
        return None
        
    except Exception as e:
        logger.debug(f"Direct API failed for {yahoo_symbol}: {e}")
        return None

def fetch_stock_price(symbol: str, market: str) -> Optional[Dict]:
    """
    Fetch current stock price from Yahoo Finance
    Returns dict with price info or None if failed
    """
    cache_key = f"{symbol}_{market}"
    
    # Check cache first
    if cache_key in _price_cache:
        cached = _price_cache[cache_key]
        if time.time() - cached.get('_cached_at', 0) < _cache_timeout:
            logger.debug(f"Returning cached price for {symbol}")
            return cached
    
    try:
        yahoo_symbol = get_yahoo_symbol(symbol, market)
        currency = 'INR' if market in ['NSE', 'BSE'] else 'USD'
        
        # Add small random delay
        time.sleep(random.uniform(0.3, 0.8))
        
        current_price = _fetch_price_direct(yahoo_symbol)

        if current_price is None:
            logger.warning(f"Could not get price for {yahoo_symbol}")
            return None
        
        result = {
            "symbol": symbol,
            "market": market,
            "current_price": current_price,
            "company_name": None,
            "currency": currency,
            "_cached_at": time.time()
        }
        
        # Cache the result
        _price_cache[cache_key] = result
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching price for {symbol} on {market}: {str(e)}")
        return None

def fetch_multiple_prices(stocks: list) -> Dict[str, Optional[Dict]]:
    """
    Fetch prices for multiple stocks
    stocks: list of dicts with 'symbol' and 'market' keys
    Returns: dict mapping "symbol_market" to price info
    """
    results = {}
    
    for stock in stocks:
        key = f"{stock['symbol']}_{stock['market']}"
        results[key] = fetch_stock_price(stock['symbol'], stock['market'])
    
    return results
