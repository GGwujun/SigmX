"""Capital flow data layer (Tier 4 of the info chain).

Sources, in fallback order:
  1. **akshare** — stock_individual_fund_flow_rank / stock_hsgt_north_net_flow_in
  2. **efinance** — get_history_bill (alt east-money wrapper, different code path)

Both hit east-money under the hood; either may be flaky on a given network, so
we try one then the other and never raise. All public functions return plain
dicts/lists (JSON-serializable) and degrade to empty results on failure.

Coverage:
  - get_stock_capital(code)   — per-stock main/super/big/mid/small order net flow
  - get_sector_capital()      — industry sector fund-flow ranking
  - get_north_capital(days)   — north-bound (HSGT) net inflow history
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


# ---------------------------------------------------------------------------
# Per-stock capital flow (main / super / big / mid / small order net)
# ---------------------------------------------------------------------------

def get_stock_capital(code: str, days: int = 10) -> list[dict[str, Any]]:
    """Per-stock daily fund flow (main/super/big/mid/small order net) for `days`.

    Returns a list of daily dicts: {date, main_net, super_net, big_net,
    mid_net, small_net, main_pct}. Sorted by date desc.
    """
    cache_key = f"stock_cap:{code}:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    rows = _stock_capital_efinance(code, days)
    if not rows:
        rows = _stock_capital_akshare(code, days)
    _cache_set(cache_key, rows)
    return rows


def _stock_capital_efinance(code: str, days: int) -> list[dict[str, Any]]:
    try:
        import efinance as ef
        df = ef.stock.get_history_bill(code)
    except Exception as exc:
        logger.info("capital_flow: efinance failed for %s: %s", code, exc)
        return []
    if df is None or df.empty:
        return []
    # Column names vary; map common ones.
    colmap = {
        "日期": "date", "股票代码": "code",
        "主力净流入-净额": "main_net", "主力净流入-净占比": "main_pct",
        "超大单净流入-净额": "super_net", "大单净流入-净额": "big_net",
        "中单净流入-净额": "mid_net", "小单净流入-净额": "small_net",
    }
    df = df.rename(columns={k: v for k, v in colmap.items() if k in df.columns})
    out: list[dict[str, Any]] = []
    for _, row in df.tail(days).iterrows():
        out.append({
            "date": str(row.get("date", "")),
            "main_net": _safe_float(row.get("main_net")),
            "super_net": _safe_float(row.get("super_net")),
            "big_net": _safe_float(row.get("big_net")),
            "mid_net": _safe_float(row.get("mid_net")),
            "small_net": _safe_float(row.get("small_net")),
            "main_pct": _safe_float(row.get("main_pct")),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def _stock_capital_akshare(code: str, days: int) -> list[dict[str, Any]]:
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
    except Exception as exc:
        logger.info("capital_flow: akshare failed for %s: %s", code, exc)
        return []
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for _, row in df.tail(days).iterrows():
        out.append({
            "date": str(row.get("日期", "")),
            "main_net": _safe_float(row.get("主力净流入-净额", 0)),
            "super_net": _safe_float(row.get("超大单净流入-净额", 0)),
            "big_net": _safe_float(row.get("大单净流入-净额", 0)),
            "mid_net": _safe_float(row.get("中单净流入-净额", 0)),
            "small_net": _safe_float(row.get("小单净流入-净额", 0)),
            "main_pct": _safe_float(row.get("主力净流入-净占比", 0)),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Sector capital-flow ranking
# ---------------------------------------------------------------------------

def get_sector_capital() -> list[dict[str, Any]]:
    """Industry sector fund-flow ranking (net inflow, today)."""
    cache_key = "sector_cap"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    rows = _sector_capital_akshare()
    _cache_set(cache_key, rows)
    return rows


def _sector_capital_akshare() -> list[dict[str, Any]]:
    try:
        import akshare as ak
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
    except Exception as exc:
        logger.info("capital_flow: sector akshare failed: %s", exc)
        return []
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for _, row in df.head(20).iterrows():
        out.append({
            "sector": str(row.get("名称", "")),
            "main_net": _safe_float(row.get("今日主力净流入-净额", row.get("主力净流入-净额", 0))),
            "change_pct": _safe_float(row.get("今日涨跌幅", 0)),
        })
    return out


# ---------------------------------------------------------------------------
# North-bound (HSGT) capital
# ---------------------------------------------------------------------------

def get_north_capital(days: int = 30) -> list[dict[str, Any]]:
    """North-bound (Stock Connect) net inflow history."""
    cache_key = f"north_cap:{days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    rows = _north_capital_akshare(days)
    _cache_set(cache_key, rows)
    return rows


def _north_capital_akshare(days: int) -> list[dict[str, Any]]:
    try:
        import akshare as ak
        df = ak.stock_hsgt_hist_em(symbol="北向资金")
    except Exception as exc:
        logger.info("capital_flow: north akshare failed: %s", exc)
        return []
    if df is None or df.empty:
        return []
    out: list[dict[str, Any]] = []
    for _, row in df.tail(days).iterrows():
        out.append({
            "date": str(row.get("日期", row.get("date", ""))),
            "net": _safe_float(row.get("当日成交净买额", row.get("净买额", 0))),
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out
