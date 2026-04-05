"""
Mutual Fund NAV Service - Fetches current NAV from mfapi.in (free API for Indian mutual funds)
"""
import httpx
import time
from typing import Optional, Dict, List
import re

# Cache for NAV data (scheme_code -> {nav, timestamp})
_nav_cache: Dict[str, Dict] = {}
# Cache for search results (search_term -> {results, timestamp})
_search_cache: Dict[str, Dict] = {}

# Cache duration in seconds (1 hour for NAV, 24 hours for search)
NAV_CACHE_DURATION = 3600
SEARCH_CACHE_DURATION = 86400


async def search_mutual_fund(fund_name: str) -> List[Dict]:
    """
    Search for mutual funds by name.
    Returns list of matching funds with scheme codes.
    """
    # Clean up the fund name for searching
    search_term = fund_name.strip().lower()
    
    # Check cache
    if search_term in _search_cache:
        cached = _search_cache[search_term]
        if time.time() - cached["timestamp"] < SEARCH_CACHE_DURATION:
            return cached["results"]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # mfapi.in search endpoint
            response = await client.get(
                f"https://api.mfapi.in/mf/search?q={fund_name}"
            )
            if response.status_code == 200:
                results = response.json()
                # Cache the results
                _search_cache[search_term] = {
                    "results": results[:20],  # Limit to top 20 results
                    "timestamp": time.time()
                }
                return results[:20]
    except Exception as e:
        print(f"Error searching mutual fund: {e}")
    
    return []


async def fetch_nav_by_scheme_code(scheme_code: str) -> Optional[Dict]:
    """
    Fetch NAV for a specific scheme code from mfapi.in
    Returns {nav, date, scheme_name} or None
    """
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
        print(f"Error fetching NAV for scheme {scheme_code}: {e}")
    
    return None


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
