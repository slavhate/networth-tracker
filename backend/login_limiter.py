"""In-memory limit on failed logins: per username from one client, per username in total, and per client.

Counts live in this process only: they reset on restart and are not shared between workers (the app runs one).
"""
import ipaddress
import math
import time
from collections import OrderedDict, deque
from typing import Deque, Dict, Iterable, Optional

WINDOW_SECONDS = 15 * 60
# Strict, but only for one username from one client: someone guessing from elsewhere can't lock the owner out
MAX_FAILURES_PER_USERNAME_AND_CLIENT = 5
# A username's total across all clients: stops a guesser spread over many addresses, loose enough that one
# attacker needs many addresses to lock the owner out
MAX_FAILURES_PER_USERNAME = 50
# Looser than per username and client: a household or office shares one address, and this limit is there to stop
# one client from trying passwords across many usernames
MAX_FAILURES_PER_IP = 20
MAX_KEYS = 10_000  # the oldest keys are dropped beyond this, so a flood of usernames can't grow memory without end

_failures: "OrderedDict[str, Deque[float]]" = OrderedDict()


def _clock() -> float:
    """Seconds on a monotonic clock; patched in tests."""
    return time.monotonic()


def client_id(ip: str) -> str:
    """Who a failure is counted against: the address, or for IPv6 its /64, which one home or host usually gets
    whole (counting each address would give such a client an endless supply of fresh counts)."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip  # not an address (e.g. the test client's "testclient")
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def username_key(username: str) -> str:
    return f"user:{username}"


def username_and_client_key(username: str, ip: str) -> str:
    return f"user:{username}|{client_id(ip)}"


def ip_key(ip: str) -> str:
    return f"ip:{client_id(ip)}"


def _recent(key: str, now: float) -> Optional[Deque[float]]:
    """The key's failures inside the window (expired ones are dropped), or None when there are none."""
    times = _failures.get(key)
    if times is None:
        return None
    while times and times[0] <= now - WINDOW_SECONDS:
        times.popleft()
    if not times:
        del _failures[key]
        return None
    return times


def retry_after(limits: Dict[str, int]) -> Optional[int]:
    """Seconds until every key in {key: max failures} is below its limit again; None when none is at it."""
    now = _clock()
    wait = 0.0
    for key, limit in limits.items():
        times = _recent(key, now)
        if times and len(times) >= limit:
            # Below the limit again once the oldest of the last `limit` failures leaves the window
            wait = max(wait, times[-limit] + WINDOW_SECONDS - now)
    return max(1, math.ceil(wait)) if wait > 0 else None


def record_failure(keys: Iterable[str]) -> None:
    now = _clock()
    for key in keys:
        times = _recent(key, now) or deque()
        times.append(now)
        _failures[key] = times
        _failures.move_to_end(key)
    while len(_failures) > MAX_KEYS:
        _failures.popitem(last=False)


def forget_one(key: str) -> None:
    """Take back one failure recorded for key (an attempt counted before it was checked, which then succeeded)."""
    times = _failures.get(key)
    if times:
        times.pop()
        if not times:
            del _failures[key]


def reset(key: str) -> None:
    _failures.pop(key, None)


def clear() -> None:
    _failures.clear()
