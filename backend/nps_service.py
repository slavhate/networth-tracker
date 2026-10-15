"""NPS scheme list and NAV history from the npsnav.in API.

npsnav.in is free and needs no key; its data comes from the NPS CRA and is licensed CC BY-NC 4.0
(personal, non-commercial use). The base URL is a setting so a mirror or a local stub can stand in.
"""
import math
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from config import settings

CACHE_SECONDS = 6 * 60 * 60
SCHEME_CODE = re.compile(r"SM[0-9]{6}")
_cache: Dict[str, Tuple[float, Any]] = {}


async def _get_json(url: str) -> Optional[Any]:
    """GET a JSON document; None on any failure (network, HTTP, decoding, a malformed URL).

    Broad on purpose: any failure means "unavailable", and the service never raises to its callers.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            return response.json()
    except Exception:  # same policy as nav_service: any failure is None
        return None


async def _cached(key: str, url: str, parse: Callable[[Any], Any]) -> Optional[Any]:
    """The parsed document, from the cache when fresh; a failed or empty fetch is not cached.

    Callers get a shallow copy of the list, so clearing or re-sorting it cannot change the cache.
    """
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return list(hit[1])
    payload = await _get_json(url)
    parsed = parse(payload) if payload is not None else None
    if not parsed:
        return None
    _cache[key] = (time.time(), parsed)
    return list(parsed)


def _base_url() -> str:
    return settings.NPS_NAV_API_URL.rstrip("/")


def _parse_day(text: Any) -> Optional[date]:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_nav(value: Any) -> Optional[float]:
    try:
        nav = float(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: an integer too large for a float
        return None
    return nav if math.isfinite(nav) and nav > 0 else None


def _rows(payload: Any) -> List[Dict]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def parse_history(payload: Any) -> List[Tuple[date, float]]:
    """(date, NAV) pairs, oldest first; rows without a usable date and a positive NAV are skipped."""
    navs: Dict[date, float] = {}
    for row in _rows(payload):
        day, nav = _parse_day(row.get("date")), _parse_nav(row.get("nav"))
        if day is not None and nav is not None:
            navs[day] = nav
    return sorted(navs.items())


def parse_latest(payload: Any) -> List[Dict]:
    """Every scheme with its latest NAV, sorted by name; rows without a valid code and a name are skipped."""
    schemes = []
    for row in _rows(payload):
        code = str(row.get("Scheme Code") or "").strip()
        name = " ".join(str(row.get("Scheme Name") or "").split())[:150]
        if not SCHEME_CODE.fullmatch(code) or not name:
            continue
        day = _parse_day(row.get("Last Updated"))
        schemes.append({
            "scheme_code": code,
            "scheme_name": name,
            "pfm_name": " ".join(str(row.get("PFM Name") or "").split()) or None,
            "nav": _parse_nav(row.get("NAV")),
            "nav_date": day.isoformat() if day else None,
        })
    return sorted(schemes, key=lambda scheme: scheme["scheme_name"])


async def list_schemes() -> Optional[List[Dict]]:
    return await _cached("latest", f"{_base_url()}/latest", parse_latest)


async def fetch_history(code: str) -> Optional[List[Tuple[date, float]]]:
    if not SCHEME_CODE.fullmatch(code or ""):
        return None
    return await _cached(f"history:{code}", f"{_base_url()}/historical/{code}", parse_history)
