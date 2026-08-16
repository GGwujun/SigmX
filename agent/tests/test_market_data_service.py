"""Tests for the canonical market-data read service."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from src.data import market_data_service as svc
from src.data.market_store import MarketStore


def test_normalize_code() -> None:
    assert svc.normalize_code("000001") == "000001.SZ"
    assert svc.normalize_code("600000") == "600000.SH"
    assert svc.normalize_code("300750.sz") == "300750.SZ"


def test_daily_bars_batch_reads_db_only(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    try:
        store.upsert_daily_bars(
            "000001.SZ",
            [
                {"date": "2026-06-24", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
            ],
            source="test.fixture",
            sync_run_id="test-run",
        )
        with mock.patch.object(svc, "get_market_store", return_value=store):
            out = svc.daily_bars_batch(["000001"], days=5)
        assert set(out) == {"000001.SZ"}
        assert float(out["000001.SZ"]["close"].iloc[-1]) == 2.0
    finally:
        store._conn.close()


def test_daily_bars_applies_explicit_forward_adjustment_and_preserves_trading_dates(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    try:
        store.upsert_daily_bars("000001.SZ", [
            {"date": "2026-06-23", "open": 10, "high": 12, "low": 9, "close": 10, "volume": 100},
            {"date": "2026-06-24", "open": 6, "high": 7, "low": 5, "close": 6, "volume": 120},
        ], source="test.fixture", sync_run_id="test-run")
        store.upsert_fq_factors("2026-06-23", [{"code": "000001.SZ", "adj_factor": 1.0}])
        store.upsert_fq_factors("2026-06-24", [{"code": "000001.SZ", "adj_factor": 2.0}])

        with mock.patch.object(svc, "get_market_store", return_value=store):
            adjusted = svc.daily_bars("000001", start="2026-06-23", end="2026-06-24", adjustment="qfq")

        assert adjusted is not None
        assert list(adjusted.index.strftime("%Y-%m-%d")) == ["2026-06-23", "2026-06-24"]
        assert list(adjusted["close"]) == [5.0, 6.0]
        assert adjusted.attrs["adjustment"] == "qfq"
        assert adjusted.attrs["factor_version"] == "2026-06-24"
    finally:
        store._conn.close()
