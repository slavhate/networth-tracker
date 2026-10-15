"""
Mutual Fund NAV Service - Fetches current NAV from mfapi.in (free API for Indian mutual funds)
"""
import httpx
import logging
import time
from collections import OrderedDict
from datetime import date
from typing import Optional, Dict, List, Tuple
import re

from nps_service import parse_history  # mfapi.in uses the same {"data": [{"date", "nav"}]} shape

logger = logging.getLogger(__name__)

# Cache for NAV data (scheme_code -> {nav, timestamp})
_nav_cache: Dict[str, Dict] = {}
# Cache for NAV history (scheme_code -> {data, timestamp})
_history_cache: Dict[str, Dict] = {}
# Cache for search results (search_term -> {results, timestamp}), least recently used first
_search_cache: "OrderedDict[str, Dict]" = OrderedDict()
MAX_SEARCH_CACHE_ENTRIES = 500  # search terms are user input: the oldest are dropped beyond this
MAX_SEARCH_LENGTH = 150  # the longest fund name a fund can have (models.MutualFundBase.fund_name)

# Cache duration in seconds (1 hour for NAV, 24 hours for search)
NAV_CACHE_DURATION = 3600
SEARCH_CACHE_DURATION = 86400


async def search_mutual_fund(fund_name: str) -> List[Dict]:
    """
    Search for mutual funds by name.
    Returns list of matching funds with scheme codes.
    """
    # Clean up the fund name for searching
    search_term = fund_name.strip().lower()[:MAX_SEARCH_LENGTH]
    
    # Check cache
    if search_term in _search_cache:
        cached = _search_cache[search_term]
        if time.time() - cached["timestamp"] < SEARCH_CACHE_DURATION:
            _search_cache.move_to_end(search_term)
            return cached["results"]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # mfapi.in search endpoint. The name goes in as an encoded query parameter: an "&" or "#" in it
            # (as in "Banking & PSU Debt") must stay part of the search, not end it
            response = await client.get(
                "https://api.mfapi.in/mf/search", params={"q": fund_name.strip()[:MAX_SEARCH_LENGTH]}
            )
            if response.status_code == 200:
                results = response.json()
                # Cache the results
                _search_cache[search_term] = {
                    "results": results[:20],  # Limit to top 20 results
                    "timestamp": time.time()
                }
                _search_cache.move_to_end(search_term)
                while len(_search_cache) > MAX_SEARCH_CACHE_ENTRIES:
                    _search_cache.popitem(last=False)
                return results[:20]
    except Exception as e:
        logger.warning("Error searching mutual fund: %s", e)
    
    return []


async def fetch_nav_by_scheme_code(scheme_code: str) -> Optional[Dict]:
    """
    Fetch NAV for a specific scheme code from mfapi.in
    Returns {nav, date, scheme_name} or None
    """
    # The code goes into the URL path: ASCII digits only, like an AMFI scheme code
    scheme_code = str(scheme_code or "")
    if not (scheme_code.isascii() and scheme_code.isdigit()):
        return None
    # Check cache
    if scheme_code in _nav_cache:
        cached = _nav_cache[scheme_code]
        if time.time() - cached["timestamp"] < NAV_CACHE_DURATION:
            return cached["data"]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.mfapi.in/mf/{scheme_code}"
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    latest = data["data"][0]
                    result = {
                        "nav": float(latest["nav"]),
                        "date": latest["date"],
                        "scheme_name": data.get("meta", {}).get("scheme_name", ""),
                        "scheme_code": scheme_code
                    }
                    # Cache the result
                    _nav_cache[scheme_code] = {
                        "data": result,
                        "timestamp": time.time()
                    }
                    return result
    except Exception as e:
        logger.warning("Error fetching NAV for scheme %s: %s", scheme_code, e)
    
    return None


async def _get_history_json(scheme_code: str):
    """mfapi.in's full NAV history for a scheme; None on any network, HTTP or decoding error."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.mfapi.in/mf/{scheme_code}")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        return None


async def fetch_history(scheme_code: str) -> Optional[List[Tuple[date, float]]]:
    """Every NAV the scheme has published, oldest first; None when unavailable. Cached like the latest NAV."""
    # ASCII digits only: str.isdigit() also accepts other scripts' digits, which don't belong in the URL
    code = str(scheme_code or "")
    if not (code.isascii() and code.isdigit()):
        return None
    cached = _history_cache.get(code)
    if cached and time.time() - cached["timestamp"] < NAV_CACHE_DURATION:
        return list(cached["data"])
    payload = await _get_history_json(code)
    history = parse_history(payload) if payload is not None else []
    if not history:
        return None
    _history_cache[code] = {"data": history, "timestamp": time.time()}
    return list(history)


async def fetch_nav_by_fund_name(fund_name: str) -> Optional[Dict]:
    """
    Search for a fund by name and fetch its current NAV.
    Returns {nav, date, scheme_name, scheme_code} or None
    """
    # Search for the fund
    results = await search_mutual_fund(fund_name)
    
    if not results:
        return None
    
    # Try to find exact or best match
    fund_name_lower = fund_name.lower()
    best_match = None
    best_score = 0
    
    for fund in results:
        scheme_name = fund.get("schemeName", "").lower()
        # Simple scoring: longer common substring = better match
        # Direct Growth funds are preferred for NAV comparison
        score = 0
        
        # Check if key words from search are in the scheme name
        search_words = fund_name_lower.split()
        for word in search_words:
            if word in scheme_name:
                score += len(word)
        
        # Prefer "direct" and "growth" plans
        if "direct" in scheme_name:
            score += 10
        if "growth" in scheme_name:
            score += 5
        
        if score > best_score:
            best_score = score
            best_match = fund
    
    if best_match:
        scheme_code = str(best_match.get("schemeCode"))
        return await fetch_nav_by_scheme_code(scheme_code)
    
    # If no good match, just use the first result
    if results:
        scheme_code = str(results[0].get("schemeCode"))
        return await fetch_nav_by_scheme_code(scheme_code)
    
    return None


def get_cached_nav(scheme_code: str) -> Optional[float]:
    """Get NAV from cache synchronously (for non-async contexts)"""
    if scheme_code in _nav_cache:
        cached = _nav_cache[scheme_code]
        if time.time() - cached["timestamp"] < NAV_CACHE_DURATION:
            return cached["data"].get("nav")
    return None


async def test_nav_service():
    """Test the NAV service to ensure it's working"""
    # Test with a popular fund
    result = await fetch_nav_by_fund_name("HDFC Flexi Cap Fund Direct Growth")
    if result:
        return {
            "status": "ok",
            "message": "NAV service is working",
            "test_fund": result["scheme_name"],
            "nav": result["nav"],
            "date": result["date"]
        }
    return {
        "status": "error",
        "message": "Could not fetch NAV data"
    }
