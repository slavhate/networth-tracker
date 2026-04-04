"""
Exchange Rate Service - Fetches live USD to INR rate from free APIs
"""
import httpx
import time
from typing import Optional

# Cache the exchange rate for 1 hour (3600 seconds)
CACHE_DURATION = 3600
_cached_rate: Optional[float] = None
_cache_timestamp: float = 0

# Fallback rate if all APIs fail
FALLBACK_RATE = 83.5


async def fetch_usd_to_inr() -> float:
    """
    Fetch current USD to INR exchange rate from free APIs.
    Uses caching to avoid excessive API calls.
    Falls back to hardcoded rate if all sources fail.
    """
    global _cached_rate, _cache_timestamp
    
    current_time = time.time()
    
    # Return cached rate if still valid
    if _cached_rate is not None and (current_time - _cache_timestamp) < CACHE_DURATION:
        return _cached_rate
    
    # Try multiple free APIs
    rate = await _try_exchange_rate_api()
    if rate is None:
        rate = await _try_frankfurter_api()
    if rate is None:
        rate = await _try_fawazahmed_api()
    
    if rate is not None:
        _cached_rate = rate
        _cache_timestamp = current_time
        return rate
    
    # Return cached rate if available (even if expired), otherwise fallback
    if _cached_rate is not None:
        return _cached_rate
    
    return FALLBACK_RATE


async def _try_exchange_rate_api() -> Optional[float]:
    """Try exchangerate-api.com (free tier)"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://open.er-api.com/v6/latest/USD"
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "success":
                    return data.get("rates", {}).get("INR")
    except Exception:
        pass
    return None


async def _try_frankfurter_api() -> Optional[float]:
    """Try frankfurter.app (free, open-source)"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://api.frankfurter.app/latest?from=USD&to=INR"
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("rates", {}).get("INR")
    except Exception:
        pass
    return None


async def _try_fawazahmed_api() -> Optional[float]:
    """Try fawazahmed0 currency API (free, no key)"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("usd", {}).get("inr")
    except Exception:
        pass
    return None


def get_cached_rate() -> float:
    """Get the cached rate synchronously (for non-async contexts)"""
    global _cached_rate
    if _cached_rate is not None:
        return _cached_rate
    return FALLBACK_RATE
