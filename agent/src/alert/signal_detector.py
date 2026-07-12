"""Z-score based arbitrage signal detection.

Uses a 30-day rolling window of premium rates to compute mean (μ) and
standard deviation (σ). When the current premium deviates by more than
2σ from the mean AND the net spread (|premium| - cost) is positive,
a signal is generated.

Signal types:
- PREMIUM: current_premium > 0 and Z > 2 → 申购套利 (buy at NAV, sell on exchange)
- DISCOUNT: current_premium < 0 and Z < -2 → 赎回套利 (buy on exchange, redeem at NAV)
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# Minimum data points required for meaningful statistics
_MIN_HISTORY = 15
# Z-score threshold (2σ = 95% confidence interval)
_Z_THRESHOLD = 2.0
# Default round-trip cost estimates by fund type
_COST_ESTIMATES = {
    "ETF": 0.5,    # 0.5% round-trip
    "LOF": 1.2,    # 1.2% round-trip
    "QDII": 1.5,   # 1.5% round-trip (includes FX spread)
}
_DEFAULT_COST = 1.0


def _cost_for(fund_type: str) -> float:
    return _COST_ESTIMATES.get(fund_type.upper(), _DEFAULT_COST)


def compute_zscore(
    current_premium: float,
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Compute Z-score for a single fund's current premium.

    Args:
        current_premium: today's premium rate (%)
        history: list of {trade_date, premium_rate} dicts (at least _MIN_HISTORY)

    Returns:
        dict with z_score, mean, std, net_spread, signal_type — or None if
        not enough data or not statistically significant.
    """
    if len(history) < _MIN_HISTORY:
        return None

    premiums = [float(h["premium_rate"]) for h in history if h.get("premium_rate") is not None]
    if len(premiums) < _MIN_HISTORY:
        return None

    n = len(premiums)
    mean = sum(premiums) / n
    variance = sum((p - mean) ** 2 for p in premiums) / n
    std = math.sqrt(variance)

    if std < 0.001:
        return None  # no variation, Z-score meaningless

    z_score = (current_premium - mean) / std

    if abs(z_score) <= _Z_THRESHOLD:
        return None  # not statistically significant

    return {
        "z_score": round(z_score, 3),
        "mean": round(mean, 3),
        "std": round(std, 3),
        "n": n,
    }


def detect_signals(
    funds: list[dict[str, Any]],
    store: Any,
    trade_date: str,
) -> list[dict[str, Any]]:
    """Scan all funds and return active arbitrage signals.

    For each fund with sufficient history, compute Z-score. If |Z| > 2 and
    net_spread > 0, generate a signal.

    Args:
        funds: current fund premium data (from get_fund_premium)
        store: MarketStore instance for history queries
        trade_date: today's trade date

    Returns:
        list of signal dicts ready for DB insertion.
    """
    signals: list[dict[str, Any]] = []

    for fund in funds:
        code = fund.get("code", "")
        premium = float(fund.get("premium_rate") or 0.0)
        ftype = (fund.get("type") or "").upper()

        if abs(premium) < 0.5:
            continue  # skip trivial premiums

        # Get historical premiums (60 days for better statistics)
        try:
            history = store.get_fund_premium_history(code, 60)
        except Exception:
            continue

        if len(history) < _MIN_HISTORY:
            continue

        # Exclude today's data from history (it's the current value)
        hist_excl = [h for h in history if h.get("trade_date") != trade_date]

        stats = compute_zscore(premium, hist_excl)
        if stats is None:
            continue

        cost = _cost_for(ftype)
        net_spread = abs(premium) - cost

        if net_spread <= 0:
            continue  # not profitable after costs

        signal_type = "PREMIUM" if premium > 0 else "DISCOUNT"

        signal = {
            "code": code,
            "name": fund.get("name", ""),
            "type": ftype,
            "trade_date": trade_date,
            "signal_type": signal_type,
            "premium_rate": round(premium, 3),
            "z_score": stats["z_score"],
            "historical_mean": stats["mean"],
            "historical_std": stats["std"],
            "n_history": stats["n"],
            "cost_estimate": cost,
            "net_spread": round(net_spread, 3),
            "status": "ACTIVE",
        }
        signals.append(signal)
        logger.debug(
            "signal: %s %s Z=%.2f premium=%.2f%% net=%.2f%%",
            signal_type, code, stats["z_score"], premium, net_spread,
        )

    if signals:
        logger.info("signal_detector: %d signals detected on %s", len(signals), trade_date)

    return signals
