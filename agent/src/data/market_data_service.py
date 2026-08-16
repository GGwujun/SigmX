"""Canonical market-data read service.

Business code should read OHLCV through this module instead of the old
``ohlcv_cache`` pickle layer. The local SQLite ``MarketStore`` is the source of
truth; scheduled sync/backfill jobs are responsible for keeping it warm.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.data.market_store import get_market_store

logger = logging.getLogger(__name__)


def normalize_code(code: str) -> str:
    """Normalize common A-share inputs to project form (000001.SZ)."""
    raw = str(code or "").strip().upper()
    if raw.endswith((".SH", ".SZ", ".BJ")):
        return raw
    digits = raw.replace(".", "")
    if len(digits) == 6 and digits.isdigit():
        if digits[0] == "6":
            return f"{digits}.SH"
        if digits[0] in {"0", "2", "3"}:
            return f"{digits}.SZ"
        if digits[0] in {"4", "8"}:
            return f"{digits}.BJ"
    return raw


def latest_daily_bars(code: str, days: int = 90) -> Optional[pd.DataFrame]:
    """Return the latest settled daily OHLCV bars from the local DB only."""
    store = get_market_store()
    if store is None:
        logger.debug("market data service: store unavailable")
        return None
    return store.get_daily_bars(normalize_code(code), days=days)


def daily_bars(
    code: str,
    *,
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
    adjustment: str = "raw",
) -> Optional[pd.DataFrame]:
    """Return daily OHLCV with an explicit raw/qfq/hfq price convention."""
    if adjustment not in {"raw", "qfq", "hfq"}:
        raise ValueError("adjustment must be raw, qfq, or hfq")
    store = get_market_store()
    if store is None:
        logger.debug("market data service: store unavailable")
        return None
    normalized = normalize_code(code)
    frame = store.get_daily_bars(normalized, days=days, start=start, end=end)
    if frame is None or frame.empty:
        return frame
    frame.attrs["adjustment"] = adjustment
    if adjustment == "raw":
        return frame
    range_start = frame.index.min().strftime("%Y-%m-%d")
    range_end = frame.index.max().strftime("%Y-%m-%d")
    factors = store.get_adjustment_factors(normalized, start=range_start, end=range_end)
    if factors is None:
        raise ValueError(f"adjustment factors unavailable for {normalized} {range_start}..{range_end}")
    aligned = factors.reindex(frame.index).ffill().bfill()
    if aligned.isna().any() or (aligned <= 0).any():
        raise ValueError(f"adjustment factors incomplete for {normalized}")
    anchor = float(aligned.iloc[-1] if adjustment == "qfq" else aligned.iloc[0])
    multiplier = aligned / anchor
    adjusted = frame.copy()
    adjusted.loc[:, ["open", "high", "low", "close"]] = adjusted[["open", "high", "low", "close"]].mul(multiplier, axis=0)
    adjusted.attrs["adjustment"] = adjustment
    adjusted.attrs["factor_version"] = factors.index.max().strftime("%Y-%m-%d")
    return adjusted


def daily_bars_batch(codes: list[str], days: int = 90) -> dict[str, pd.DataFrame]:
    """Batch-read latest daily OHLCV bars from the local DB only."""
    out: dict[str, pd.DataFrame] = {}
    for code in codes:
        norm = normalize_code(code)
        df = latest_daily_bars(norm, days=days)
        if df is not None and not df.empty:
            out[norm] = df
    return out


def default_strategy_codes() -> list[str]:
    """Return active A-share codes excluding ST/delisting/BJ by default."""
    store = get_market_store()
    if store is None:
        logger.debug("market data service: store unavailable")
        return []
    return store.default_strategy_codes()


def security_master(default_only: bool = False) -> list[dict]:
    """Return local security metadata, optionally filtered to default universe."""
    store = get_market_store()
    if store is None:
        logger.debug("market data service: store unavailable")
        return []
    return store.list_security_master(default_only=default_only)


def missing_daily_dates(code: str, start: str, end: str) -> list[str]:
    """Return expected trading dates missing from local daily bars.

    This is a diagnostic helper for backfill planning. It does not fetch from
    external sources.
    """
    df = daily_bars(code, start=start, end=end)
    present = set()
    if df is not None and not df.empty:
        present = {ts.strftime("%Y-%m-%d") for ts in df.index}
    dates = _trading_dates(start, end)
    return [d for d in dates if d not in present]


def _trading_dates(start: str, end: str) -> list[str]:
    try:
        from src.data.trade_calendar import is_trading_day
    except Exception:  # noqa: BLE001
        is_trading_day = None  # type: ignore[assignment]

    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    out: list[str] = []
    cur = s
    while cur <= e:
        d = cur.strftime("%Y-%m-%d")
        if is_trading_day is not None:
            try:
                if is_trading_day(d):
                    out.append(d)
            except Exception:  # noqa: BLE001
                if cur.weekday() < 5:
                    out.append(d)
        elif cur.weekday() < 5:
            out.append(d)
        cur += timedelta(days=1)
    return out
