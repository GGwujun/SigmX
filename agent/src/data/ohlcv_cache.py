"""Persistent OHLCV cache using pickle files.

Stores daily bars per A-share symbol under ``~/.vibe-trading/cache/ohlcv/``.
On fetch, loads cached data first, then only pulls new dates from mootdx.

Cache policy:
- During A-share trading hours (Mon-Fri 9:30-15:00 CST): always fetch fresh from mootdx
- Outside trading hours: use cache if last bar is from the most recent trading day
- Weekends/holidays: use Friday's data if within 2 days

Usage::

    from src.data.ohlcv_cache import fetch_with_cache

    df = fetch_with_cache("000001.SZ")  # returns DataFrame with all cached bars
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_ROOT = Path.home() / ".vibe-trading" / "cache" / "ohlcv"

# A-share trading hours (Beijing time UTC+8)
_CST = timezone(timedelta(hours=8))
_TRADING_START_MORNING = 9 * 60 + 30   # 9:30
_TRADING_END_MORNING = 11 * 60 + 30    # 11:30
_TRADING_START_AFTERNOON = 13 * 60      # 13:00
_TRADING_END_AFTERNOON = 15 * 60        # 15:00


def _is_trading_hours() -> bool:
    """Return True if we are currently within A-share trading hours."""
    now_cst = datetime.now(_CST)
    if now_cst.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    minutes = now_cst.hour * 60 + now_cst.minute
    return (
        (_TRADING_START_MORNING <= minutes <= _TRADING_END_MORNING)
        or (_TRADING_START_AFTERNOON <= minutes <= _TRADING_END_AFTERNOON)
    )


def _needs_today_fetch(last_cached_date: pd.Timestamp) -> bool:
    """Return True if we should try to fetch today's bar from mootdx.

    During trading hours: always try (today's bar changes throughout the day).
    Outside trading hours: only if cache doesn't have today's bar yet.
    """
    today = pd.Timestamp.now().normalize()
    if last_cached_date.normalize() >= today:
        # Cache already has today's bar. Only re-fetch during trading hours.
        return _is_trading_hours()
    # Cache doesn't have today's bar — always try to fetch it
    return True


def _use_cached_historical(cached: pd.DataFrame, days: int) -> pd.DataFrame | None:
    """Return cached historical data if we have enough bars, else None."""
    if cached is not None and not cached.empty and len(cached) >= min(days, 20):
        return cached
    return None


def _cache_path(code: str) -> Path:
    """Return the cache file path for a stock code."""
    return _CACHE_ROOT / f"{code.replace('.', '_')}.pkl"


def load_cached(code: str) -> pd.DataFrame | None:
    """Load cached OHLCV data for a stock, or None if not cached."""
    path = _cache_path(code)
    if path.exists():
        try:
            df = pd.read_pickle(path)
            if not df.empty:
                if df.index.name != "date" and "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                return df.sort_index()
        except Exception:
            logger.debug("Failed to read cache for %s, will re-fetch", code)
    return None


def save_cache(code: str, df: pd.DataFrame) -> None:
    """Save OHLCV data to disk cache as pickle."""
    if df is None or df.empty:
        return
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    path = _cache_path(code)
    try:
        df.to_pickle(path)
    except Exception as exc:
        logger.debug("Failed to save cache for %s: %s", code, exc)


def _fetch_bars_mootdx(codes: list[str], offset: int = 100) -> dict[str, pd.DataFrame]:
    """Fetch daily bars from mootdx for multiple codes. Returns {code: DataFrame}."""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std", timeout=15)
        results: dict[str, pd.DataFrame] = {}
        for code in codes:
            raw = code.replace(".SZ", "").replace(".SH", "")
            try:
                df = client.bars(symbol=raw, frequency=9, start=0, offset=offset)
                if df is not None and not df.empty:
                    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
                    df.index = pd.to_datetime(df.index)
                    df = df.sort_index()
                    results[code] = df[["open", "high", "low", "close", "volume"]]
            except Exception:
                logger.debug("mootdx bars failed for %s", code)
        return results
    except Exception as exc:
        logger.warning("mootdx unavailable: %s", exc)
        return {}


def _fetch_incremental_mootdx(code: str, since_date: str) -> pd.DataFrame | None:
    """Fetch only new bars from mootdx since a given date (YYYY-MM-DD)."""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std", timeout=10)
        raw = code.replace(".SZ", "").replace(".SH", "")
        df = client.bars(symbol=raw, frequency=9, start=0, offset=30)
        if df is not None and not df.empty:
            df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            cutoff = pd.Timestamp(since_date)
            new = df[df.index > cutoff]
            return new[["open", "high", "low", "close", "volume"]] if not new.empty else None
    except Exception:
        pass
    return None


def fetch_with_cache(code: str, days: int = 90) -> pd.DataFrame | None:
    """Get OHLCV data for a stock, using disk cache + incremental today fetch.

    Strategy:
    1. Historical bars (yesterday and earlier): always from disk cache
    2. Today's bar: incremental fetch from mootdx if needed (trading hours or missing)
    3. Merge and save; if mootdx fails fall back to cache
    """
    cached = load_cached(code)

    if cached is not None and not cached.empty:
        last_date = cached.index.max()

        if _needs_today_fetch(last_date):
            # Try to get only today's new bars
            since_str = last_date.strftime("%Y-%m-%d")
            new_bars = _fetch_incremental_mootdx(code, since_str)
            if new_bars is not None and not new_bars.empty:
                merged = pd.concat([cached, new_bars])
                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                save_cache(code, merged)
                return merged.tail(days)

        # No new bars needed, or incremental fetch failed — use cache
        if len(cached) >= min(days, 20):
            return cached.tail(days)

    # No cache or too few bars — full historical fetch + save
    result = _fetch_bars_mootdx([code], offset=max(days + 20, 100))
    df = result.get(code)
    if df is not None and not df.empty:
        # Merge with any partial cache
        if cached is not None and not cached.empty:
            df = pd.concat([cached, df])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        save_cache(code, df)
        return df.tail(days)

    # mootdx completely failed — return cached if available
    if cached is not None and not cached.empty:
        return cached.tail(days)
    return None


def fetch_batch(codes: list[str], days: int = 90) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV for multiple codes — historical from cache, today incremental.

    Strategy per code:
    1. Load historical bars from disk cache
    2. If today's bar is needed (trading hours or missing), incremental fetch
    3. Merge today's bar with cached history; save back
    4. If no cache at all, full fetch from mootdx
    5. mootdx failure → fall back to cache
    """
    results: dict[str, pd.DataFrame] = {}
    need_full_fetch: list[str] = []
    need_incremental: dict[str, pd.DataFrame] = {}  # code → cached_df

    for code in codes:
        cached = load_cached(code)
        if cached is not None and not cached.empty:
            last_date = cached.index.max()
            if _needs_today_fetch(last_date):
                need_incremental[code] = cached
            else:
                results[code] = cached.tail(days)
        else:
            need_full_fetch.append(code)

    # Incremental fetch for codes that have cache but need today's bar
    for code, cached in need_incremental.items():
        last_date = cached.index.max()
        since_str = last_date.strftime("%Y-%m-%d")
        new_bars = _fetch_incremental_mootdx(code, since_str)
        if new_bars is not None and not new_bars.empty:
            merged = pd.concat([cached, new_bars])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            save_cache(code, merged)
            results[code] = merged.tail(days)
        else:
            # Incremental failed — use cache as-is
            results[code] = cached.tail(days)

    # Full fetch for codes with no cache at all
    if need_full_fetch:
        fresh = _fetch_bars_mootdx(need_full_fetch, offset=max(days + 20, 100))
        for code, df in fresh.items():
            if df is not None and not df.empty:
                save_cache(code, df)
                results[code] = df.tail(days)
        # Codes that failed full fetch — try any cached fallback
        for code in need_full_fetch:
            if code not in results:
                cached = load_cached(code)
                if cached is not None:
                    results[code] = cached.tail(days)

    return results
