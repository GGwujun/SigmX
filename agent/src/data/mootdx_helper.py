"""Mootdx helper: provide a working TDX server (the built-in list has stale IPs).

We pin a known-good server so every caller (opportunity scanner, fund premium,
OHLCV cache, backtest loader) works without per-callsite changes.
"""

from __future__ import annotations

# Known-working TDX servers verified from Aliyun ECS (2026-06-14).
# The mootdx built-in list contains IPs that are no longer reachable.
_WORKING_SERVERS = [
    ("180.153.18.170", 7709),
    ("180.153.18.171", 7709),
]


def get_quotes(timeout: int = 15):
    """Return a mootdx Quotes client pinned to a working server."""
    from mootdx.quotes import Quotes
    return Quotes.factory(market="std", timeout=timeout, server=_WORKING_SERVERS[0])
