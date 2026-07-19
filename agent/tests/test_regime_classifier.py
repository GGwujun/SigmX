"""Tests for the market-regime classifier (technical indicators + scoring).

Covers the pure-function indicator math, the bull/bear scoring rules, the
emotion-score adjustments, and the ``classify_regime`` entry point's
data-insufficient fallback. The classifier is documented as "zero external API
dependency" — all tests run against synthetic numpy/pandas inputs and a tmp
MarketStore, no network.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.market_store import MarketStore
from src.risk import regime_classifier as rc


# ── indicator math ──────────────────────────────────────────────────────

def test_calc_ma_returns_last_window_average() -> None:
    closes = np.arange(1.0, 11.0)  # 1..10
    # MA3 over last 3 (8,9,10) = 9.0
    assert rc._calc_ma(closes, 3) == pytest.approx(9.0)


def test_calc_ma_short_series_falls_back_to_last() -> None:
    closes = np.array([2.0, 4.0])
    # fewer than period → last value
    assert rc._calc_ma(closes, 5) == pytest.approx(4.0)


def test_calc_ma_empty_series_returns_zero() -> None:
    assert rc._calc_ma(np.array([]), 5) == 0.0


def test_calc_rsi_all_gains_is_100() -> None:
    closes = np.arange(1.0, 20.0)  # strictly rising
    assert rc._calc_rsi(closes, 14) == pytest.approx(100.0)


def test_calc_rsi_all_losses_is_near_zero() -> None:
    closes = np.arange(20.0, 1.0, -1.0)  # strictly falling
    # avg_loss > 0, avg_gain = 0 → rs = 0 → rsi = 0
    assert rc._calc_rsi(closes, 14) == pytest.approx(0.0)


def test_calc_rsi_short_series_defaults_to_50() -> None:
    # fewer than period+1 points → neutral 50
    assert rc._calc_rsi(np.array([1.0, 2.0, 3.0]), 14) == 50.0


def test_calc_rsi_flat_series_avoids_divide_by_zero() -> None:
    closes = np.full(20, 5.0)
    # avg_loss == 0 → returns 100 (per the guard), no ZeroDivisionError
    assert rc._calc_rsi(closes, 14) == 100.0


def test_calc_adx_short_series_returns_zeros() -> None:
    highs = np.array([11.0, 12.0])
    lows = np.array([9.0, 10.0])
    closes = np.array([10.0, 11.0])
    adx, pdi, mdi = rc._calc_adx(highs, lows, closes, 14)
    assert (adx, pdi, mdi) == (0.0, 0.0, 0.0)


def test_calc_volatility_flat_series_is_zero() -> None:
    closes = np.full(25, 10.0)
    assert rc._calc_volatility(closes, 20) == 0.0


def test_calc_ma20_slope_short_series_is_zero() -> None:
    # fewer than 25 valid points → 0
    assert rc._calc_ma20_slope(np.array([1.0, 2.0, 3.0])) == 0.0


# ── compute_technical_indicators ────────────────────────────────────────

def _rising_bars(n: int, start: float = 10.0) -> pd.DataFrame:
    """n bars with a gentle uptrend (deterministic)."""
    closes = start + np.arange(n) * 0.5
    return pd.DataFrame({
        "close": closes,
        "high": closes + 1.0,
        "low": closes - 1.0,
    })


def test_technical_indicators_keys_present() -> None:
    inds = rc.compute_technical_indicators(_rising_bars(60))
    for key in ("close", "ma5", "ma10", "ma20", "ma60", "rsi14", "adx",
                "plus_di", "minus_di", "volatility", "ma20_slope", "change_20d",
                "ma_aligned_bull", "ma_aligned_bear"):
        assert key in inds


def test_technical_indicators_rising_series_is_bull_aligned() -> None:
    inds = rc.compute_technical_indicators(_rising_bars(60))
    # a clean uptrend → ma5>ma10>ma20
    assert inds["ma_aligned_bull"] is True
    assert inds["ma_aligned_bear"] is False
    assert inds["change_20d"] > 0
    assert inds["rsi14"] > 55  # rising → overbought-ish


def test_technical_indicators_falling_series_is_bear_aligned() -> None:
    bars = _rising_bars(60)
    bars["close"] = 40.0 - np.arange(60) * 0.5  # downtrend
    inds = rc.compute_technical_indicators(bars)
    assert inds["ma_aligned_bear"] is True
    assert inds["change_20d"] < 0


# ── scoring ─────────────────────────────────────────────────────────────

def test_technical_score_strong_bull_accumulates() -> None:
    inds = rc.compute_technical_indicators(_rising_bars(80))
    bull, bear = rc.compute_technical_score(inds)
    assert bull >= 4  # MA20>MA60*1.02 + change>5% + aligned + rsi + slope + adx
    assert bear == 0


def test_technical_score_strong_bear_accumulates() -> None:
    # clean downtrend: close/high/low all descending together
    closes = 50.0 - np.arange(80) * 0.5
    bars = pd.DataFrame({
        "close": closes,
        "high": closes + 0.5,
        "low": closes - 0.5,
    })
    inds = rc.compute_technical_indicators(bars)
    bull, bear = rc.compute_technical_score(inds)
    assert bear >= 4
    assert bull == 0


def test_emotion_score_empty_returns_zeros() -> None:
    bull, bear = rc.compute_emotion_score(None)
    assert (bull, bear) == (0.0, 0.0)


def test_emotion_score_extreme_breadth_bullish() -> None:
    # advancers >> decliners, many limit-ups, huge turnover
    bull, bear = rc.compute_emotion_score({
        "advancers": 4000, "decliners": 800,  # ratio 5.0
        "limit_up": 120, "limit_down": 5,
        "turnover_billion": 18000,
    })
    assert bull >= 3  # ratio>=2 (+2) + limit_up>=80 (+1) + turnover>15000 (+1)
    assert bear == 0


def test_emotion_score_extreme_breadth_bearish() -> None:
    bull, bear = rc.compute_emotion_score({
        "advancers": 500, "decliners": 4000,  # ratio 0.125
        "limit_up": 5, "limit_down": 60,
        "turnover_billion": 5000,
    })
    assert bear >= 4  # ratio<=0.5 (+2) + limit_up<=15 (+1) + limit_down>=30 (+2) + turnover<7000 (+1)
    assert bull == 0


def test_emotion_score_zero_decliners_treated_as_extreme_bull() -> None:
    # advancers>0 but decliners==0 → ratio=5.0 (extreme bull branch)
    bull, bear = rc.compute_emotion_score({
        "advancers": 100, "decliners": 0,
        "limit_up": 0, "limit_down": 0, "turnover_billion": 0,
    })
    # ratio>=2 → bull +2; limit_up<=15 → bear +1 (zero limit-ups counts as weak breadth)
    assert bull >= 2
    assert bear >= 1  # the zero-limit-up penalty fires on the bear side


# ── classify_regime entry point ─────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> MarketStore:
    s = MarketStore(tmp_path / "market.db")
    yield s
    s._conn.close()


def test_classify_regime_insufficient_bars_falls_back_to_range(store: MarketStore) -> None:
    # no index_daily data at all → range with zero confidence
    result = rc.classify_regime(store, "2026-07-17")
    assert result.regime == "range"
    assert result.confidence == 0.0
    assert result.bull_score == 0.0
    assert result.bear_score == 0.0
    assert result.strong_trend is False


def test_classify_regime_bullish_trend_classifies_bull(store: MarketStore) -> None:
    # seed 120 days of rising index bars (valid calendar dates)
    dates = pd.date_range(end="2026-07-17", periods=120, freq="B").strftime("%Y-%m-%d")
    closes = 3000.0 + np.arange(120) * 8.0  # strong uptrend
    rows = [
        {"date": dates[i], "open": c - 5, "high": c + 10, "low": c - 10,
         "close": c, "volume": 1e8}
        for i, c in enumerate(closes)
    ]
    store.upsert_index_daily("000001.SH", rows)
    result = rc.classify_regime(store, "2026-07-17")
    assert result.regime == "bull"
    assert result.bull_score >= 4
    assert result.bull_score > result.bear_score
    assert "atr_mult" in result.parameters  # params attached


def test_classify_regime_returns_result_dict_serializable(store: MarketStore) -> None:
    result = rc.classify_regime(store, "2026-07-17")
    d = result.to_dict()
    # to_dict must round numerics and keep JSON-serializable shape
    import json
    json.dumps(d)  # should not raise
    assert d["regime"] in ("bull", "bear", "range")


def test_regime_params_cover_all_three_regimes() -> None:
    # the param table is the downstream contract for the risk engine
    for regime in ("bull", "range", "bear"):
        params = rc.REGIME_PARAMS[regime]
        for field in ("stop_loss", "tp1", "tp2", "tp3",
                      "max_position", "max_holdings", "atr_mult", "change_range"):
            assert field in params, f"{regime} missing {field}"
    # bear is the most conservative
    assert rc.REGIME_PARAMS["bear"]["max_position"] < rc.REGIME_PARAMS["bull"]["max_position"]
    assert rc.REGIME_PARAMS["bear"]["stop_loss"] > rc.REGIME_PARAMS["bull"]["stop_loss"]  # tighter (less negative)
