"""Warnings for the user collected while handling one request, e.g. a NAV source that couldn't be reached.

The middleware in main.py starts a list per request and sends what was collected in the X-Warnings header.
A list (not a tuple) is stored so that code running in a copied context (a thread or a child task) appends to
the same list.
"""
import json
from contextvars import ContextVar, Token
from typing import List, Optional

_current: ContextVar[Optional[List[str]]] = ContextVar("user_warnings", default=None)

# Bytes the X-Warnings header may take. Proxies refuse a response whose headers outgrow their buffers (nginx's
# default is 4–8 KB for all of them), so the warnings keep well below that.
HEADER_BUDGET = 2000


def start() -> Token:
    return _current.set([])


def stop(token: Token) -> None:
    _current.reset(token)


def warn(message: str) -> None:
    """Add a warning for this request; repeats are kept once, and outside a request it does nothing."""
    collected = _current.get()
    if collected is not None and message not in collected:
        collected.append(message)


def collected() -> List[str]:
    return list(_current.get() or [])


def _more(count: int) -> str:
    return f"…and {count} more {'warning' if count == 1 else 'warnings'}"


def header_value(messages: List[str], budget: int = HEADER_BUDGET) -> str:
    """The X-Warnings value: the messages as a JSON array (ASCII only) within `budget` bytes. They are kept in order
    while they fit; the rest are replaced by one last "…and N more warnings"."""
    kept: List[str] = []
    for index, message in enumerate(messages):
        left = len(messages) - index - 1
        if len(json.dumps(kept + [message] + ([_more(left)] if left else []), ensure_ascii=True)) > budget:
            break
        kept.append(message)
    left = len(messages) - len(kept)
    return json.dumps(kept + ([_more(left)] if left else []), ensure_ascii=True)
