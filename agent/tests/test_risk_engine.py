"""Tests for the 8-layer risk engine.

Each ``check_l*`` is an independent function that reads price/bars from a
MarketStore. Tests seed a tmp store with realtime quotes + daily bars and
assert both the triggered and not-triggered paths, plus the pure helpers
(``_calc_atr``, ``_calc_price_limit``, ``_trading_days_between``) and the
``compute_health_score`` aggregation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.market_store import MarketStore
from src.risk import risk_engine as re
from src.risk.regime_classifier import REGIME_PARAMS


@pytest.fixture
def store(tmp_path: Path) -> MarketStore:
    s = MarketStore(tmp_path / "market.db")
    yield s
    s._conn.close()


def _seed_bars(store: MarketStore, code: str, closes: list[float], *,
               start: str = "2026-06-01") -> None:
    """Seed daily bars for a code (date ascending)."""
    dates = pd.date_range(start=start, periods=len(closes), freq="B").strftime("%Y-%m-%d")
    rows = [
        {"date": dates[i], "open": c - 0.2, "high": c + 0.3,
         "low": c - 0.3, "close": c, "volume": 1e6 + i * 1000}
        for i, c in enumerate(closes)
    ]
    store.upsert_daily_bars(code, rows, source="test", sync_run_id="test")


def _seed_quote(store: MarketStore, code: str, *, price: float, pre_close: float = 0,
                rise_rate: float = 0, trade_date: str = "2026-07-17") -> None:
    store.upsert_realtime_quotes(trade_date, [{
        "code": code, "price": price, "pre_close": pre_close,
        "rise_rate": rise_rate,
    }])


PARAMS = REGIME_PARAMS["range"]


# ── pure helpers ────────────────────────────────────────────────────────

def test_calc_atr_short_series_returns_zero() -> None:
    bars = [{"high": 11, "low": 9, "close": 10}] * 5
    assert re._calc_atr(bars, 20) == 0.0


def test_calc_atr_computes_mean_true_range() -> None:
    # 21 bars, each (high=11, low=9, close=10) → TR=2 every day → ATR=2
    bars = [{"high": 11.0, "low": 9.0, "close": 10.0}] * 21
    assert re._calc_atr(bars, 20) == pytest.approx(2.0)


def test_calc_price_limit_main_board_is_ten_percent() -> None:
    up, down = re._calc_price_limit("600519", 100.0)
    assert up == 110.0
    assert down == 90.0


def test_calc_price_limit_chinext_and_star_is_twenty_percent() -> None:
    for code in ("300750", "301088", "688981", "689009"):
        up, down = re._calc_price_limit(code, 100.0)
        assert up == 120.0
        assert down == 80.0


def test_calc_price_limit_zero_pre_close_returns_zeros() -> None:
    assert re._calc_price_limit("600519", 0) == (0, 0)


def test_trading_days_between_uses_workday_approximation() -> None:
    from src.risk.risk_engine import _CST
    now = datetime(2026, 7, 17, tzinfo=_CST)  # aware — matches production now()
    # 14 calendar days ago → ~10 trading days (14 * 5/7)
    d = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    assert re._trading_days_between(d, now=now) == 10


def test_trading_days_between_future_date_clamped_to_zero() -> None:
    from src.risk.risk_engine import _CST
    now = datetime(2026, 7, 17, tzinfo=_CST)
    future = (now + timedelta(days=5)).strftime("%Y-%m-%d")
    assert re._trading_days_between(future, now=now) == 0


def test_trading_days_between_naive_now_returns_zero() -> None:
    # naive now vs aware internal _CST → TypeError swallowed → 0.
    # Pins current behavior; the helper is only safe with tz-aware now.
    now = datetime(2026, 7, 17)  # naive
    d = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    assert re._trading_days_between(d, now=now) == 0


def test_trading_days_between_bad_format_returns_zero() -> None:
    assert re._trading_days_between("not-a-date") == 0


# ── L1: portfolio drawdown circuit breaker ──────────────────────────────

def test_l1_drawdown_triggers_at_ten_percent(store: MarketStore) -> None:
    # cost 100, now 89 → drawdown 11% ≥ 10%
    _seed_quote(store, "600519.SH", price=89.0)
    positions = [{"symbol": "600519.SH", "avg_cost": 100.0, "quantity": 100}]
    res = re.check_l1_drawdown_circuit_breaker(positions, store, PARAMS)
    assert res.triggered is True
    assert res.severity == "critical"
    assert res.action == "suggest_sell"


def test_l1_drawdown_passes_when_under_threshold(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=95.0)  # 5% drawdown
    positions = [{"symbol": "600519.SH", "avg_cost": 100.0, "quantity": 100}]
    res = re.check_l1_drawdown_circuit_breaker(positions, store, PARAMS)
    assert res.triggered is False


def test_l1_drawdown_passes_when_no_valid_positions(store: MarketStore) -> None:
    # zero quantity / zero cost → skipped, total_cost=0 → pass
    res = re.check_l1_drawdown_circuit_breaker([], store, PARAMS)
    assert res.triggered is False


# ── L2: trailing stop profit ────────────────────────────────────────────

def test_l2_trailing_stop_triggers_on_half_retrace(store: MarketStore) -> None:
    # peak +20%, now +9% (less than half of peak) → trigger
    _seed_quote(store, "600519.SH", price=109.0)
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "peak_profit_pct": 0.20, "name": "茅台"}
    res = re.check_l2_trailing_stop_profit(pos, store, PARAMS)
    assert res.triggered is True
    assert res.severity == "critical"


def test_l2_trailing_stop_skips_when_peak_below_threshold(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=105.0)
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "peak_profit_pct": 0.05}  # <10%
    res = re.check_l2_trailing_stop_profit(pos, store, PARAMS)
    assert res.triggered is False


def test_l2_trailing_stop_passes_when_still_near_peak(store: MarketStore) -> None:
    # peak +20%, now +11% (>half of peak=10%) → no trigger
    _seed_quote(store, "600519.SH", price=111.0)
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "peak_profit_pct": 0.20}
    res = re.check_l2_trailing_stop_profit(pos, store, PARAMS)
    assert res.triggered is False


# ── L3: ATR stop loss ───────────────────────────────────────────────────

def test_l3_atr_stop_triggers_when_price_below_stop(store: MarketStore) -> None:
    # 25 bars around 100, ATR small; avg_cost high so stop is well below → trigger
    closes = [100.0] * 25
    _seed_bars(store, "600519.SH", closes)
    _seed_quote(store, "600519.SH", price=80.0)
    pos = {"symbol": "600519.SH", "avg_cost": 120.0, "name": "茅台"}
    res = re.check_l3_atr_stop_loss(pos, store, PARAMS)
    assert res.triggered is True


def test_l3_atr_stop_skips_when_insufficient_bars(store: MarketStore) -> None:
    _seed_bars(store, "600519.SH", [100.0, 101.0, 102.0])  # <20 bars
    _seed_quote(store, "600519.SH", price=50.0)
    pos = {"symbol": "600519.SH", "avg_cost": 100.0}
    res = re.check_l3_atr_stop_loss(pos, store, PARAMS)
    assert res.triggered is False


# ── L4: tiered take profit ──────────────────────────────────────────────

def test_l4_take_profit_triggers_tp3(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=140.0)  # +40% ≥ tp3=0.35
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "tp_triggered": [], "name": "茅台"}
    res = re.check_l4_tiered_take_profit(pos, store, PARAMS)
    assert res.triggered is True
    assert res.details["level"] == "TP3"
    assert res.severity == "warning"  # level>=2


def test_l4_take_profit_respects_already_triggered(store: MarketStore) -> None:
    # +40% but TP3 already triggered → should report TP2/TP1 if not triggered
    _seed_quote(store, "600519.SH", price=140.0)
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "tp_triggered": [3, 2, 1]}
    res = re.check_l4_tiered_take_profit(pos, store, PARAMS)
    assert res.triggered is False  # all levels already hit


def test_l4_take_profit_passes_below_tp1(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=105.0)  # +5% < tp1=0.15
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "tp_triggered": []}
    res = re.check_l4_tiered_take_profit(pos, store, PARAMS)
    assert res.triggered is False


# ── L5: stampede + index ────────────────────────────────────────────────

def test_l5_index_circuit_breaker_triggers_on_three_percent_drop(store: MarketStore) -> None:
    _seed_quote(store, "000001.SH", price=3000.0, pre_close=3100.0, rise_rate=-3.5)
    res = re.check_l5_stampede_and_index([], store, PARAMS)
    assert res.triggered is True
    assert res.severity == "critical"


def test_l5_stampede_triggers_when_half_positions_dropping(store: MarketStore) -> None:
    # no index quote seeded → index check skipped; 2 of 2 positions drop >3%
    _seed_quote(store, "600519.SH", price=90.0, pre_close=100.0, rise_rate=-5.0)
    _seed_quote(store, "000858.SZ", price=90.0, pre_close=100.0, rise_rate=-5.0)
    positions = [
        {"symbol": "600519.SH"},
        {"symbol": "000858.SZ"},
    ]
    res = re.check_l5_stampede_and_index(positions, store, PARAMS)
    assert res.triggered is True


# ── L6: max holding period ──────────────────────────────────────────────

def test_l6_holding_period_triggers_after_twenty_trading_days(store: MarketStore) -> None:
    # 30 calendar days ago → ~21 trading days ≥ 20
    from datetime import datetime, timedelta
    buy = (datetime(2026, 7, 17) - timedelta(days=30)).strftime("%Y-%m-%d")
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "buy_date": buy,
           "tp_triggered": [], "name": "茅台"}
    res = re.check_l6_max_holding_period(pos, store, PARAMS)
    assert res.triggered is True
    assert res.severity == "warning"


def test_l6_holding_period_skips_when_tp1_reached(store: MarketStore) -> None:
    from datetime import datetime, timedelta
    buy = (datetime(2026, 7, 17) - timedelta(days=60)).strftime("%Y-%m-%d")
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "buy_date": buy, "tp_triggered": [1]}
    res = re.check_l6_max_holding_period(pos, store, PARAMS)
    assert res.triggered is False


def test_l6_holding_period_skips_without_buy_date(store: MarketStore) -> None:
    pos = {"symbol": "600519.SH", "avg_cost": 100.0, "buy_date": None, "tp_triggered": []}
    res = re.check_l6_max_holding_period(pos, store, PARAMS)
    assert res.triggered is False


# ── L7: limit down ──────────────────────────────────────────────────────

def test_l7_limit_down_triggers_at_limit_price(store: MarketStore) -> None:
    # main board, pre_close 100 → limit_down 90.0
    _seed_quote(store, "600519.SH", price=90.0, pre_close=100.0)
    pos = {"symbol": "600519.SH", "name": "茅台"}
    res = re.check_l7_limit_down(pos, store, PARAMS)
    assert res.triggered is True
    assert res.severity == "critical"


def test_l7_limit_down_passes_above_limit(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=95.0, pre_close=100.0)
    pos = {"symbol": "600519.SH"}
    res = re.check_l7_limit_down(pos, store, PARAMS)
    assert res.triggered is False


def test_l7_limit_down_skips_without_pre_close(store: MarketStore) -> None:
    _seed_quote(store, "600519.SH", price=90.0, pre_close=0)
    pos = {"symbol": "600519.SH"}
    res = re.check_l7_limit_down(pos, store, PARAMS)
    assert res.triggered is False


# ── L8: position correlation ────────────────────────────────────────────

def test_l8_correlation_passes_with_single_position(store: MarketStore) -> None:
    _seed_bars(store, "600519.SH", [100.0 + i for i in range(25)])
    res = re.check_l8_position_correlation([{"symbol": "600519.SH"}], store, PARAMS)
    assert res.triggered is False


def test_l8_correlation_triggers_on_identical_series(store: MarketStore) -> None:
    # two symbols with identical close series → correlation ≈ 1.0 ≥ 0.7
    closes = [100.0 + i * 0.5 for i in range(25)]
    _seed_bars(store, "600519.SH", closes)
    _seed_bars(store, "000858.SZ", closes)
    positions = [{"symbol": "600519.SH"}, {"symbol": "000858.SZ"}]
    res = re.check_l8_position_correlation(positions, store, PARAMS)
    assert res.triggered is True
    assert res.severity == "warning"


# ── health score ────────────────────────────────────────────────────────

def test_health_score_no_positions_is_hundred() -> None:
    assert re.compute_health_score([], store=None, regime_params=PARAMS) == 100.0


def test_health_score_penalizes_losses(store: MarketStore) -> None:
    _seed_bars(store, "600519.SH", [100.0] * 25)  # flat volume, no MA penalty
    _seed_quote(store, "600519.SH", price=80.0)   # -20%
    pos = [{"symbol": "600519.SH", "avg_cost": 100.0}]
    score = re.compute_health_score(pos, store, PARAMS)
    assert 0.0 <= score < 100.0


def test_health_score_bounded_to_zero_one_hundred(store: MarketStore) -> None:
    # penalty is min(|profit|*5, 40)/n per position → bounded, score stays in [0,100]
    closes = [100.0] * 25
    _seed_bars(store, "600519.SH", closes)
    _seed_quote(store, "600519.SH", price=10.0)  # -90%
    pos = [{"symbol": "600519.SH", "avg_cost": 100.0}]
    score = re.compute_health_score(pos, store, PARAMS)
    assert 0.0 <= score <= 100.0
    # a -90% loss must cost more than a flat position (100.0)
    assert score < 100.0


# ── report serialization ────────────────────────────────────────────────

def test_risk_report_to_dict_is_json_serializable() -> None:
    report = re.RiskReport(trade_date="2026-07-17", regime="range",
                           checks=[re._pass(1, "test")], portfolio_health_score=88.5,
                           summary="ok")
    import json
    d = report.to_dict()
    json.dumps(d)
    assert d["portfolio_health_score"] == 88.5
    assert d["checks"][0]["layer"] == 1
