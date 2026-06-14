"""Global market data layer — international context for A-share analysis.

A-share stocks are materially affected by overseas markets (Fed policy, US
equities overnight, commodities, USD/CNY). This module pulls that context via
akshare (which proxies the international sources domestically — no VPN needed),
so AlphaForge can add an international-influence dimension.

All functions return plain dicts and never raise; missing/unavailable data is
omitted gracefully.

Coverage:
  - get_us_indices()      — Dow / Nasdaq / S&P latest + overnight change
  - get_commodities()     — crude oil / gold / copper (proxy via futures)
  - get_fx()              — USD index, USD/CNY (offshore)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

_CACHE_TTL = 300
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < _CACHE_TTL:
            return hit[1]
    return None


def _cache_set(key: str, val: Any) -> None:
    with _cache_lock:
        _cache[key] = (time.time(), val)


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _pct_change(df: pd.DataFrame) -> tuple[float, float]:
    """Return (latest_close, pct_change_vs_prev) from an OHLC df."""
    if df is None or df.empty:
        return 0.0, 0.0
    closes = df["close"].astype(float).dropna()
    if len(closes) < 2:
        return float(closes.iloc[-1]), 0.0
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    return last, ((last - prev) / prev * 100.0) if prev else 0.0


# ---------------------------------------------------------------------------
# US indices
# ---------------------------------------------------------------------------

_US_INDEX_SYMBOLS = {
    "DJI": ".DJI",      # Dow Jones
    "IXIC": ".IXIC",    # Nasdaq
    "SPX": ".INX",      # S&P 500
}


def get_us_indices() -> dict[str, Any]:
    """Latest close + overnight change for the three major US indices."""
    cache_key = "us_indices"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    import akshare as ak
    result: dict[str, Any] = {}
    for label, sym in _US_INDEX_SYMBOLS.items():
        try:
            df = ak.index_us_stock_sina(symbol=sym)
            last, chg = _pct_change(df)
            date = str(df["date"].iloc[-1]) if df is not None and not df.empty else ""
            result[label] = {"close": round(last, 2), "change_pct": round(chg, 2), "date": date}
        except Exception as exc:
            logger.info("global_market: US index %s failed: %s", label, exc)
            result[label] = None
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Commodities — global futures via akshare's foreign-future history.
# ---------------------------------------------------------------------------

# akshare foreign-future symbols (芝加哥商品等). Names vary by akshare version;
# we try a few common ones and keep whichever works.
_COMMODITY_CANDIDATES = {
    "crude_oil": ["CL", "CLM"],   # WTI crude
    "gold": ["GC", "GCM"],        # COMEX gold
    "copper": ["HG"],             # COMEX copper
}


def get_commodities() -> dict[str, Any]:
    cache_key = "commodities"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {}
    try:
        import akshare as ak
        # ak.futures_foreign_hist(symbol=...) — try each candidate
        hist_fn = getattr(ak, "futures_foreign_hist", None)
        if hist_fn:
            for label, syms in _COMMODITY_CANDIDATES.items():
                got = False
                for sym in syms:
                    try:
                        df = hist_fn(symbol=sym)
                        last, chg = _pct_change(df)
                        if last > 0:
                            result[label] = {"close": round(last, 2), "change_pct": round(chg, 2)}
                            got = True
                            break
                    except Exception:
                        continue
                if not got:
                    result[label] = None
        else:
            logger.info("global_market: futures_foreign_hist not available in this akshare version")
    except Exception as exc:
        logger.info("global_market: commodities failed: %s", exc)
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# FX — USD index + offshore CNY
# ---------------------------------------------------------------------------

def get_fx() -> dict[str, Any]:
    cache_key = "fx"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {}
    try:
        import akshare as ak
        # USD/CNY 汇率（currency_boc_safe 或 fx_spot_quote）
        for label, sym in [("usd_cny", "美元"), ("usd_index", "美元指数")]:
            try:
                fn = getattr(ak, "currency_boc_safe", None) or getattr(ak, "currency_boc_sina", None)
                if fn:
                    df = fn(symbol=sym, start_date="20260101", end_date="20261231") if "start_date" in fn.__code__.co_varnames else fn(sym)
                    if df is not None and not df.empty:
                        # find a numeric close-ish column
                        for col in ["中行折算价", "现汇卖出价", "收盘价", "close"]:
                            if col in df.columns:
                                vals = df[col].astype(float).dropna()
                                if len(vals) >= 2:
                                    last = float(vals.iloc[-1])
                                    prev = float(vals.iloc[-2])
                                    result[label] = {"close": round(last, 4), "change_pct": round(((last - prev) / prev * 100), 2)}
                                    break
            except Exception as exc:
                logger.info("global_market: fx %s failed: %s", label, exc)
    except Exception as exc:
        logger.info("global_market: fx block failed: %s", exc)
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Aggregated snapshot
# ---------------------------------------------------------------------------

def get_global_snapshot() -> dict[str, Any]:
    """One-call digest: US indices + commodities + FX. For the AlphaForge
    global-market agent to inject as upstream context."""
    return {
        "us_indices": get_us_indices(),
        "commodities": get_commodities(),
        "fx": get_fx(),
    }
