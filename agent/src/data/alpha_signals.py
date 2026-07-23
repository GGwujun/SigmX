"""Alpha factor cross-sectional signals for position analysis.

Computes a curated set of ~15 alpha factors on a peer universe and
extracts the target stock's cross-sectional percentile ranking.

Cache: peer panel + alpha results cached in memory for 5 minutes.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Curated alpha list — 15 factors across 7 themes
# ---------------------------------------------------------------------------

CURATED_ALPHAS: list[dict[str, str]] = [
    # momentum
    {"id": "alpha101_006",  "theme": "momentum",   "label": "动量-开盘价动量"},
    {"id": "alpha101_013",  "theme": "momentum",   "label": "动量-量价相关性"},
    {"id": "gtja191_010",   "theme": "momentum",   "label": "动量-收益加速度"},
    # reversal
    {"id": "alpha101_043",  "theme": "reversal",    "label": "反转-短期反转"},
    {"id": "qlib158_roc20", "theme": "reversal",    "label": "反转-20日变动率"},
    # volatility
    {"id": "alpha101_061",  "theme": "volatility",  "label": "波动-波动率偏度"},
    {"id": "gtja191_078",   "theme": "volatility",  "label": "波动-振幅异常"},
    # volume / liquidity
    {"id": "alpha101_050",  "theme": "volume",      "label": "量价-成交量比率"},
    {"id": "gtja191_140",   "theme": "volume",      "label": "量价-换手率信号"},
    {"id": "qlib158_std60", "theme": "volume",      "label": "量价-60日波动"},
    # quality
    {"id": "academic_rmw",  "theme": "quality",     "label": "质量-盈利因子"},
    {"id": "alpha101_044",  "theme": "quality",     "label": "质量-盈利稳定性"},
    # size
    {"id": "academic_smb",  "theme": "size",        "label": "规模-SMB因子"},
    # value
    {"id": "academic_hml",  "theme": "value",       "label": "价值-HML因子"},
    # trend / MA
    {"id": "qlib158_ma5",   "theme": "trend",       "label": "趋势-5日均线"},
]


def _theme_emoji(theme: str) -> str:
    return {
        "momentum": "🚀", "reversal": "🔄", "volatility": "🌊",
        "volume": "📊", "quality": "💎", "size": "📏",
        "value": "💰", "trend": "📈",
    }.get(theme, "📌")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_SIGNALS_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300  # 5 min


# ---------------------------------------------------------------------------
# Peer universe
# ---------------------------------------------------------------------------

def _get_peer_codes(code: str, min_peers: int = 10, max_peers: int = 50) -> list[str]:
    """Return persisted same-board peers without recommendation-time I/O."""
    try:
        from src.data.market_store import get_market_store

        store = get_market_store()
        conn = getattr(store, "_conn", None)
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT DISTINCT peer.stock_code FROM board_members target "
            "JOIN board_members peer ON peer.board_code = target.board_code "
            "WHERE target.stock_code = ? AND peer.stock_code <> ? "
            "ORDER BY peer.stock_code LIMIT ?",
            (code, code, max_peers),
        ).fetchall()
        peers = list(dict.fromkeys(str(row["stock_code"]) for row in rows))[:max_peers]
        return peers if len(peers) >= min_peers else []
    except Exception:
        logger.debug("Local peer lookup failed", exc_info=True)
        return []

# ---------------------------------------------------------------------------
# Panel loading
# ---------------------------------------------------------------------------

def _load_peer_panel(codes: list[str], days: int = 90) -> dict[str, pd.DataFrame]:
    """Load wide OHLCV panel for a list of stock codes.

    Returns panel dict: {col_name: DataFrame(index=date, columns=code)}.
    """
    from src.data.market_data_service import daily_bars_batch

    data = daily_bars_batch(codes, days=days)
    if not data:
        return {}

    # Pivot per-stock DataFrames into wide panel per column
    columns = ["open", "high", "low", "close", "volume"]
    panel: dict[str, pd.DataFrame] = {}
    for col in columns:
        frames = []
        for code, df in data.items():
            if col in df.columns:
                s = df[col].copy()
                s.name = code
                frames.append(s)
        if frames:
            panel[col] = pd.concat(frames, axis=1).sort_index()

    return panel


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_alpha_signals(code: str) -> dict[str, Any]:
    """Compute curated alpha factor signals for a single stock.

    Returns:
        dict with keys:
        - peer_count: number of peer stocks used
        - signals: list of {id, theme, label, emoji, rank_pct, z_score, direction, status}
        - top_bullish: list of top 3 strongest alpha signals
        - top_bearish: list of top 3 weakest alpha signals
        - score: composite alpha score (0-1)
        - error: error message if computation failed (str or None)

    Signals where the alpha couldn't be computed have status='skipped'.
    """
    cache_key = code
    now = time.time()
    with _CACHE_LOCK:
        cached = _SIGNALS_CACHE.get(cache_key)
        if cached and (now - cached.get("_ts", 0)) < _CACHE_TTL:
            return {k: v for k, v in cached.items() if k != "_ts"}

    result: dict[str, Any] = {"signals": [], "top_bullish": [], "top_bearish": [],
                                "peer_count": 0, "score": 0.50, "error": None}

    # 1. Get peer codes
    peers = _get_peer_codes(code)
    if not peers:
        result["error"] = "无 peer 可比股票"
        return result

    # 2. Load panel
    all_codes = [code] + peers
    panel = _load_peer_panel(all_codes, days=90)
    if not panel or "close" not in panel or panel["close"].empty:
        result["error"] = "无法加载行情面板数据"
        return result

    # Verify target stock is in the panel
    if code not in panel["close"].columns:
        result["error"] = f"{code} 不在面板中"
        return result
    result["peer_count"] = len(peers)

    # 3. Compute each alpha
    from src.factors.registry import Registry
    registry = Registry()
    registry._scan()

    signals: list[dict] = []
    successes = 0

    for spec in CURATED_ALPHAS:
        alpha_id = spec["id"]
        entry: dict = {
            "id": alpha_id, "theme": spec["theme"], "label": spec["label"],
            "emoji": _theme_emoji(spec["theme"]),
            "rank_pct": 0.5, "z_score": 0.0, "direction": "neutral", "status": "skipped",
        }
        try:
            raw = registry.compute(alpha_id, panel)
            if raw is None or raw.empty:
                signals.append(entry)
                continue

            # Extract target stock's most recent value
            if code not in raw.columns:
                signals.append(entry)
                continue

            series = raw[code].dropna()
            if len(series) < 2:
                signals.append(entry)
                continue

            # Cross-sectional ranking: where does this stock rank vs peers?
            last_row = raw.iloc[-1].dropna()
            if len(last_row) < 3:
                signals.append(entry)
                continue

            stock_val = float(last_row.get(code, np.nan))
            if np.isnan(stock_val) or np.isinf(stock_val):
                signals.append(entry)
                continue

            all_vals = last_row.values.astype(float)
            all_vals = all_vals[np.isfinite(all_vals)]

            if len(all_vals) < 3:
                signals.append(entry)
                continue

            rank_pct = float((all_vals < stock_val).sum()) / max(1, len(all_vals) - 1)
            rank_pct = max(0.01, min(0.99, rank_pct))

            # Z-score within peers
            mean = float(np.mean(all_vals))
            std = float(np.std(all_vals))
            z_score = float((stock_val - mean) / std) if std > 0 else 0.0
            z_score = max(-3.0, min(3.0, z_score))

            # Direction
            if entry["theme"] == "reversal":
                # For reversal factors, high rank = bearish (reversal is fading)
                direction = "bearish" if rank_pct > 0.7 else "bullish" if rank_pct < 0.3 else "neutral"
            elif entry["theme"] == "volatility":
                # High volatility rank = bearish (more risk)
                direction = "bearish" if rank_pct > 0.7 else "bullish" if rank_pct < 0.3 else "neutral"
            else:
                # Most factors: high rank = bullish (strong signal)
                direction = "bullish" if rank_pct > 0.7 else "bearish" if rank_pct < 0.3 else "neutral"

            entry.update({
                "rank_pct": round(rank_pct, 3), "z_score": round(z_score, 2),
                "direction": direction, "status": "ok",
            })
            successes += 1
        except Exception as exc:
            # Keep status='skipped' (a factor not applying is fine), but record
            # the reason so a real bug (KeyError/TypeError) is not silently
            # indistinguishable from "factor N/A". Logged at debug to avoid noise
            # on factors that legitimately lack peer data.
            entry["skip_reason"] = f"{type(exc).__name__}: {exc}"
            logger.debug("alpha_signals: factor %s skipped: %s", entry.get("name"), exc, exc_info=True)
        signals.append(entry)

    result["signals"] = signals

    # 4. Composite alpha score
    ok_signals = [s for s in signals if s["status"] == "ok"]
    if ok_signals:
        # Convert rank_pct to a score: bullish factors (>0.5) increase score
        scores = []
        for s in ok_signals:
            if s["direction"] == "bullish":
                scores.append(s["rank_pct"])
            elif s["direction"] == "bearish":
                scores.append(1.0 - s["rank_pct"])
            else:
                scores.append(0.5)
        composite = float(np.mean(scores)) if scores else 0.5
        result["score"] = round(composite, 3)

    # 5. Top signals
    sorted_signals = sorted(ok_signals, key=lambda s: s["rank_pct"], reverse=True)
    result["top_bullish"] = sorted_signals[:3]
    result["top_bearish"] = sorted(sorted_signals, key=lambda s: s["rank_pct"])[:3]

    with _CACHE_LOCK:
        _SIGNALS_CACHE[cache_key] = {**result, "_ts": time.time()}

    return result
