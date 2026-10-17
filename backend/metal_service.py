"""Gold and silver rates in rupees per gram, from the international spot price.

The spot price (USD per troy ounce) comes from gold-api.com (free, no key; the base URL is a setting so a mirror or
a local stub can stand in), with Yahoo Finance's gold and silver futures as the fallback. It is converted with the
app's USD→INR rate and India's import duty on the metals (METAL_IMPORT_DUTY_PCT) is added; GST is not, as market
rates are quoted before it. Like the other sources, nothing here raises: a rate that can't be fetched is None.
"""
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

import httpx

import exchange_service
from config import settings

logger = logging.getLogger(__name__)

CACHE_SECONDS = 5 * 60
TROY_OUNCE_GRAMS = 31.1034768
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# Per metal: the gold-api.com symbol, the Yahoo Finance futures symbol, and the USD-per-ounce range a real price
# falls in (far wider than either metal has ever traded); anything outside it is a bad feed, not a price
METALS: Dict[str, Tuple[str, str, float, float]] = {
    "gold": ("XAU", "GC=F", 100.0, 100_000.0),
    "silver": ("XAG", "SI=F", 1.0, 5_000.0),
}
SOURCE_GOLD_API = "gold-api.com"
SOURCE_YAHOO = "Yahoo Finance"

_HEADERS = {
    "Accept": "application/json",
    # Yahoo refuses requests without a browser-like agent
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

_cache: Dict[str, Tuple[float, Dict]] = {}


async def _get_json(url: str, params: Optional[Dict] = None) -> Optional[Any]:
    """GET a JSON document; None on any failure (network, HTTP, decoding, a malformed URL)."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, params=params, headers=_HEADERS)
            response.raise_for_status()
            return response.json()
    except Exception:  # same policy as nps_service: any failure is None
        return None


def _usd_per_ounce(value: Any, metal: str) -> Optional[float]:
    """A price from a feed as a float, when it is a finite number in the metal's plausible range."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        price = float(value)
    except (ValueError, OverflowError):
        return None
    low, high = METALS[metal][2:]
    return price if math.isfinite(price) and low <= price <= high else None


def parse_gold_api(payload: Any, metal: str) -> Optional[float]:
    """USD per ounce from a gold-api.com response: {"price": 2650.1, "updatedAt": "...", ...}."""
    return _usd_per_ounce(payload.get("price"), metal) if isinstance(payload, dict) else None


def parse_yahoo_chart(payload: Any, metal: str) -> Optional[float]:
    """USD per ounce from a Yahoo Finance chart response: the market price, else the last usable close."""
    try:
        result = payload["chart"]["result"][0]
    except (TypeError, KeyError, IndexError):
        return None
    if not isinstance(result, dict):
        return None
    meta = result.get("meta")
    price = _usd_per_ounce(meta.get("regularMarketPrice"), metal) if isinstance(meta, dict) else None
    if price is not None:
        return price
    try:
        closes = result["indicators"]["quote"][0]["close"]
    except (TypeError, KeyError, IndexError):
        return None
    for close in reversed(closes if isinstance(closes, list) else []):
        price = _usd_per_ounce(close, metal)
        if price is not None:
            return price
    return None


async def fetch_usd_per_ounce(metal: str) -> Optional[Tuple[float, str]]:
    """(USD per troy ounce, source) for "gold" or "silver": gold-api.com first, then Yahoo Finance; None when
    neither has a usable price."""
    symbol, futures = METALS[metal][:2]
    base = settings.METAL_PRICE_API_URL.rstrip("/")
    price = parse_gold_api(await _get_json(f"{base}/{symbol}"), metal)
    if price is not None:
        return price, SOURCE_GOLD_API
    price = parse_yahoo_chart(
        await _get_json(f"{YAHOO_CHART_URL}/{quote(futures, safe='')}", {"interval": "1d", "range": "5d"}), metal)
    if price is not None:
        return price, SOURCE_YAHOO
    return None


def import_duty_pct() -> float:
    """The duty setting when it is a sensible percentage; 0 otherwise (and logged), so a typo can't inflate rates."""
    duty = settings.METAL_IMPORT_DUTY_PCT
    if isinstance(duty, (int, float)) and math.isfinite(duty) and 0 <= duty <= 100:
        return float(duty)
    logger.warning("METAL_IMPORT_DUTY_PCT=%r is not a percentage between 0 and 100; using 0", duty)
    return 0.0


def inr_per_gram(usd_per_ounce: float, usd_to_inr: float, duty_pct: float) -> float:
    """Rupees per gram of pure metal, import duty included, to the paisa."""
    return round(usd_per_ounce * usd_to_inr / TROY_OUNCE_GRAMS * (1 + duty_pct / 100), 2)


async def fetch_rates() -> Optional[Dict]:
    """{"gold_per_gram", "silver_per_gram", "fetched_at", "source", "import_duty_pct", "usd_inr_live"}, from the
    cache when fresh; None when either metal's price can't be fetched (a failure is not cached). Gold and silver
    are fetched one after the other: two small requests, and a refresh is a click, not a page load.

    usd_inr_live is False when the USD→INR rate used was a stale or fallback one, for the caller to warn about.
    """
    hit = _cache.get("rates")
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return dict(hit[1])
    prices = {}
    for metal in METALS:
        fetched = await fetch_usd_per_ounce(metal)
        if fetched is None:
            return None
        prices[metal] = fetched
    usd_to_inr = await exchange_service.fetch_usd_to_inr()
    if not (isinstance(usd_to_inr, (int, float)) and math.isfinite(usd_to_inr) and usd_to_inr > 0):
        return None
    duty = import_duty_pct()
    sources = list(dict.fromkeys(source for _, source in prices.values()))
    rates = {
        "gold_per_gram": inr_per_gram(prices["gold"][0], usd_to_inr, duty),
        "silver_per_gram": inr_per_gram(prices["silver"][0], usd_to_inr, duty),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": ", ".join(sources),
        "import_duty_pct": duty,
        "usd_inr_live": exchange_service.last_rate_was_live(),
    }
    if rates["usd_inr_live"]:  # rates on a stale USD→INR rate are used once, not kept: the next refresh tries again
        _cache["rates"] = (time.time(), rates)
    return dict(rates)
