# -*- coding: utf-8 -*-
"""全球指数降级链：yfinance 主面 → 新浪美股/港股逐标的降级，双面全灭不造数。

全程 stub 外部取数（monkeypatch market_sync 的取数入口），无网络。
"""

from __future__ import annotations

import pytest

from src.data import market_sync as ms


class FakeStore:
    def __init__(self):
        self.captured: list[dict] = []

    def upsert_global_market_indices(self, trade_date: str, rows: list[dict]) -> int:
        self.captured = rows
        return len(rows)


def _hist(close: float) -> list[dict]:
    return [
        {"trade_date": "2026-10-21", "open": close - 1, "high": close, "low": close - 2,
         "close": close - 1, "volume": 1000},
        {"trade_date": "2026-10-22", "open": close - 1, "high": close + 1, "low": close - 1,
         "close": close, "volume": 1200},
    ]


@pytest.fixture()
def faces(monkeypatch: pytest.MonkeyPatch):
    """stub 三个取数面：yfinance 批量 / 新浪美股 / 新浪港股。"""
    state = {
        "yf": {"^GSPC": _hist(7700.0), "^DJI": _hist(52000.0)},
        "us": {},
        "hk": {},
        "us_calls": [],
        "hk_calls": [],
    }
    monkeypatch.setattr(ms, "_yf_last_rows", lambda symbols, **kw: {
        s: state["yf"][s] for s in symbols if s in state["yf"]})
    monkeypatch.setattr(ms, "_ak_us_index_history", lambda symbol: (
        state["us_calls"].append(symbol), state["us"].get(symbol) or [])[1])
    monkeypatch.setattr(ms, "_ak_hk_index_history", lambda symbol: (
        state["hk_calls"].append(symbol), state["hk"].get(symbol) or [])[1])
    return state


def test_us_symbol_falls_to_sina_when_yfinance_missing(faces) -> None:
    """yfinance 缺 ^SOX → 新浪美股面接管，source 标注真实来源。"""
    faces["us"]["^SOX"] = _hist(11500.0)
    store = FakeStore()
    n = ms._sync_global_market_indices(store, "2026-10-23")

    assert n >= 1
    by_symbol = {r["symbol"]: r for r in store.captured}
    assert by_symbol["^SOX"]["source"] == "akshare.index_us_stock_sina"
    assert "^SOX" in faces["us_calls"]
    # yfinance 命中的标的不打扰降级面
    assert by_symbol["^GSPC"]["source"] == "yfinance"


def test_hsi_falls_to_sina_hk_and_marks_hkd(faces) -> None:
    """yfinance 缺 HSI → 新浪港股面接管，币种标 HKD（美股仍 USD）。"""
    faces["hk"]["^HSI"] = _hist(26000.0)
    faces["hk"]["HSTECH"] = _hist(5800.0)
    store = FakeStore()
    ms._sync_global_market_indices(store, "2026-10-23")

    by_symbol = {r["symbol"]: r for r in store.captured}
    assert by_symbol["^HSI"]["source"] == "akshare.stock_hk_index_daily_sina"
    assert by_symbol["^HSI"]["currency"] == "HKD"
    assert by_symbol["HSTECH"]["currency"] == "HKD"
    assert by_symbol["^GSPC"]["currency"] == "USD"


def test_both_faces_dead_skips_row_without_fabrication(faces) -> None:
    """双面全灭的标的整行跳过——不造数、不写半行。"""
    store = FakeStore()
    ms._sync_global_market_indices(store, "2026-10-23")

    symbols = {r["symbol"] for r in store.captured}
    assert "^GSPC" in symbols and "^DJI" in symbols    # yfinance 活的照常
    for dead in ("^IXIC", "^SOX", "^HSI"):
        assert dead not in symbols
        assert dead in faces["us_calls"] + faces["hk_calls"]   # 降级面确实被尝试过


def test_us_sina_symbol_table_covers_all_us_indices() -> None:
    """符号表必须覆盖 _GLOBAL_INDEX_SYMBOLS 里全部美股标的（漏一个降级就断）。"""
    us_symbols = {s for s, _ in ms._GLOBAL_INDEX_SYMBOLS
                  if s not in ("^HSI", "HSTECH")}
    assert us_symbols == set(ms._US_SINA_SYMBOLS)
