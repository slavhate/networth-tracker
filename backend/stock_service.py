"""
Stock price fetching service using yfinance
"""
import yfinance as yf
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

def get_yahoo_symbol(symbol: str, market: str) -> str:
    """Convert symbol to Yahoo Finance format based on market"""
    symbol = symbol.upper().strip()
    
    if market == "NSE":
        return f"{symbol}.NS"
    elif market == "BSE":
        return f"{symbol}.BO"
    elif market == "NASDAQ":
        return symbol  # NASDAQ symbols don't need suffix
    else:
        return symbol

def fetch_stock_price(symbol: str, market: str) -> Optional[Dict]:
    """
    Fetch current stock price from Yahoo Finance
    Returns dict with price info or None if failed
    """
    try:
        yahoo_symbol = get_yahoo_symbol(symbol, market)
        ticker = yf.Ticker(yahoo_symbol)
        
        # Get current price info
        info = ticker.info
        
        if not info:
            logger.warning(f"No info found for {yahoo_symbol}")
            return None
        
        # Try different price fields
        current_price = (
            info.get('currentPrice') or 
            info.get('regularMarketPrice') or 
            info.get('previousClose') or
            info.get('open')
        )
        
        if current_price is None:
            # Try to get from history
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = float(hist['Close'].iloc[-1])
        
        if current_price is None:
            logger.warning(f"Could not get price for {yahoo_symbol}")
            return None
            
        return {
            "symbol": symbol,
            "market": market,
            "current_price": float(current_price),
            "company_name": info.get('shortName') or info.get('longName'),
            "currency": info.get('currency', 'INR' if market in ['NSE', 'BSE'] else 'USD'),
            "change": info.get('regularMarketChange'),
            "change_percent": info.get('regularMarketChangePercent'),
            "day_high": info.get('dayHigh'),
            "day_low": info.get('dayLow'),
            "fifty_two_week_high": info.get('fiftyTwoWeekHigh'),
            "fifty_two_week_low": info.get('fiftyTwoWeekLow'),
        }
        
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
