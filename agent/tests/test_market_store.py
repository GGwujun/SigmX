"""Tests for the market-data SQLite store."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data.market_quality import DatasetQualityReport, QualityStatus
from src.data.market_store import MarketStore


@pytest.fixture
def store(tmp_path: Path) -> MarketStore:
    s = MarketStore(tmp_path / "market.db")
    yield s
    s._conn.close()


def _row(date: str, close: float = 1.0) -> dict:
    return {"date": date, "open": 1, "high": 1, "low": 1, "close": close,
            "volume": 1, "total_amt": 1, "rise_rate": 0.5, "t_rate": 0.1, "name": "X"}


def _upsert_daily(store: MarketStore, code: str, rows: list[dict], *, run_id: str = "test-run") -> int:
    return store.upsert_daily_bars(
        code,
        rows,
        source="test.fixture",
        sync_run_id=run_id,
    )


def test_init_is_idempotent(store: MarketStore) -> None:
    # Second init must not raise (CREATE TABLE IF NOT EXISTS).
    store._init_db()


def test_fund_flow_backup_preserves_total_net_amount(store: MarketStore) -> None:
    store.upsert_fund_flow_daily(
        "600519.SH",
        [
            {
                "date": "2026-07-14",
                "net_amount": 123456.0,
                "turnover": 987654.0,
                "source": "sina.backup",
            }
        ],
    )

    row = store._conn.execute(
        "SELECT main_net, net_amount, turnover, source FROM fund_flow_daily "
        "WHERE code = ? AND trade_date = ?",
        ("600519.SH", "2026-07-14"),
    ).fetchone()

    assert row is not None
    assert row["main_net"] is None
    assert row["net_amount"] == 123456.0
    assert row["turnover"] == 987654.0
    assert row["source"] == "sina.backup"


def test_replace_option_chain_keeps_all_months_and_sides(store: MarketStore) -> None:
    rows = [
        {"month": "2607", "code": "10001", "call_put": "call", "last": 0.1},
        {"month": "2607", "code": "10002", "call_put": "put", "last": 0.2},
        {"month": "2608", "code": "10003", "call_put": "call", "last": 0.3},
    ]

    assert store.replace_option_chain("510050", "2026-07-14", rows) == 3
    stored = store._conn.execute(
        "SELECT month, code, call_put FROM option_chain "
        "WHERE underlying = ? AND trade_date = ? ORDER BY code",
        ("510050", "2026-07-14"),
    ).fetchall()

    assert [tuple(row) for row in stored] == [
        ("2607", "10001", "call"),
        ("2607", "10002", "put"),
        ("2608", "10003", "call"),
    ]


def test_lockup_round_trip_keeps_v34_fields(store: MarketStore) -> None:
    store.upsert_lockup_expiry(
        "600519.SH",
        [
            {
                "date": "2026-07-20",
                "shares": 100.0,
                "able_shares": 80.0,
                "ratio": 0.012,
                "type": "首发原股东限售股份",
            }
        ],
    )

    row = store._conn.execute(
        "SELECT free_shares, able_shares, free_ratio, lift_type FROM lockup_expiry "
        "WHERE code = ? AND free_date = ?",
        ("600519.SH", "2026-07-20"),
    ).fetchone()

    assert row is not None
    assert tuple(row) == (100.0, 80.0, 0.012, "首发原股东限售股份")


def test_rotating_dataset_codes_eventually_cover_universe(store: MarketStore) -> None:
    codes = ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ", "000005.SZ"]

    first = store.next_dataset_codes("eps_forecast", codes, limit=2)
    second = store.next_dataset_codes("eps_forecast", codes, limit=2)
    third = store.next_dataset_codes("eps_forecast", codes, limit=2)

    assert first == ["000001.SZ", "000002.SZ"]
    assert second == ["000003.SZ", "000004.SZ"]
    assert third == ["000005.SZ", "000001.SZ"]
    store._init_db()


def test_upsert_and_get_daily(store: MarketStore) -> None:
    n = _upsert_daily(store, "600206.SH", [_row("2026-06-10"), _row("2026-06-11")])
    assert n == 2
    df = store.get_daily_bars("600206.SH", days=10)
    assert df is not None
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.name == "date"
    assert len(df) == 2


def test_upsert_replaces_on_pk_conflict(store: MarketStore) -> None:
    _upsert_daily(store, "600206.SH", [_row("2026-06-10", close=1.0)])
    _upsert_daily(store, "600206.SH", [_row("2026-06-10", close=99.99)])
    df = store.get_daily_bars("600206.SH", start="2026-06-10", end="2026-06-10")
    assert df is not None and df["close"].iloc[0] == 99.99


def test_daily_bar_provenance_round_trip(store: MarketStore) -> None:
    store.upsert_daily_bars(
        "600206.SH",
        [_row("2026-06-10")],
        source="tushare.daily",
        sync_run_id="run-1",
        quality_status="verified",
    )
    row = store._conn.execute(
        "SELECT source, sync_run_id, quality_status, ingested_at "
        "FROM bars_daily WHERE code = ? AND trade_date = ?",
        ("600206.SH", "2026-06-10"),
    ).fetchone()

    assert row is not None
    assert tuple(row[:3]) == ("tushare.daily", "run-1", "verified")
    assert row["ingested_at"]


def test_get_daily_returns_none_when_empty(store: MarketStore) -> None:
    assert store.get_daily_bars("000000.SH", days=5) is None


def test_last_daily_date(store: MarketStore) -> None:
    _upsert_daily(store, "600206.SH", [_row("2026-06-10"), _row("2026-06-11")])
    assert store.last_daily_date("600206.SH") == "2026-06-11"
    assert store.last_daily_date("000000.SH") is None


def test_security_master_default_universe_filters_risky_names(store: MarketStore) -> None:
    n = store.upsert_security_master(
        [
            {"code": "000001.SZ", "symbol": "000001", "name": "平安银行", "list_status": "L", "list_date": "19910403"},
            {"code": "000002.SZ", "symbol": "000002", "name": "ST测试", "list_status": "L", "is_st": True},
            {"code": "000003.SZ", "symbol": "000003", "name": "退市测试", "list_status": "D", "is_delisting": True, "is_active": False},
            {"code": "430001.BJ", "symbol": "430001", "name": "北交测试", "list_status": "L", "is_bj": True},
        ]
    )
    assert n == 4
    assert store.security_master_count() == 4
    assert store.security_master_count(default_only=True) == 1
    assert store.default_strategy_codes() == ["000001.SZ"]
    lo, hi = store.date_range("security_master")
    assert lo == "19910403" and hi == "19910403"


def test_dragon_tiger_get_has(store: MarketStore) -> None:
    assert store.has_dragon_tiger("2026-06-11") is False
    store.upsert_dragon_tiger("2026-06-11", [{"code": "600206", "name": "X", "close": 10}])
    assert store.has_dragon_tiger("2026-06-11") is True
    rows = store.get_dragon_tiger("2026-06-11")
    assert len(rows) == 1 and rows[0]["code"] == "600206"


def test_pool_replace_semantics(store: MarketStore) -> None:
    # Second upsert for the same (pool_type, date) must fully replace, not append.
    store.upsert_pool("limitup", "2026-06-11", [{"code": "600206"}])
    store.upsert_pool("limitup", "2026-06-11", [{"code": "000001"}, {"code": "300750"}])
    codes = {p["code"] for p in store.get_pool("limitup", "2026-06-11")}
    assert codes == {"000001", "300750"}


def test_meta_round_trip(store: MarketStore) -> None:
    assert store.get_meta("k") is None
    store.set_meta("daemon:2026-06-11", "ts")
    assert store.get_meta("daemon:2026-06-11") == "ts"


def test_sync_run_and_dataset_result_round_trip(store: MarketStore) -> None:
    run_id = store.create_sync_run("2026-07-14", worker_id="test-worker")
    report = DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=QualityStatus.VERIFIED,
        expected_rows=2,
        received_rows=2,
        valid_rows=2,
        published_rows=2,
        source="tushare.daily",
    )

    store.record_dataset_result(run_id, report)
    store.finish_sync_run(run_id, QualityStatus.PUBLISHED)

    readiness = store.get_data_readiness("bars_daily", "2026-07-14")
    assert readiness.ready is True
    assert readiness.status == QualityStatus.PUBLISHED
    assert readiness.run_id == run_id
    assert readiness.valid_rows == 2
    assert readiness.published_rows == 2


def test_partial_dataset_is_never_ready(store: MarketStore) -> None:
    run_id = store.create_sync_run("2026-07-14", worker_id="test-worker")
    report = DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=QualityStatus.PARTIAL,
        expected_rows=2,
        received_rows=1,
        valid_rows=1,
        missing_codes=["000001.SZ"],
        blocking_reasons=["unexplained_missing_codes"],
        source="tushare.daily",
    )
    store.record_dataset_result(run_id, report)
    store.finish_sync_run(run_id, QualityStatus.PARTIAL, error_summary="missing row")

    readiness = store.get_data_readiness("bars_daily", "2026-07-14")
    assert readiness.ready is False
    assert readiness.status == QualityStatus.PARTIAL
    assert readiness.blocking_reasons == ["unexplained_missing_codes"]


def test_table_counts_and_range(store: MarketStore) -> None:
    _upsert_daily(store, "600206.SH", [_row("2026-06-10"), _row("2026-06-11")])
    store.upsert_security_master([{"code": "600206.SH", "name": "X", "list_status": "L"}])
    store.upsert_trade_calendar([{"date": "2026-06-11", "is_trading": True}])
    store.upsert_realtime_quotes("2026-06-11", [{"code": "600206.SH", "price": 12.3}])
    store.upsert_stock_daily_basic([{"code": "600206.SH", "trade_date": "2026-06-11", "pe": 10.5}])
    store.upsert_etf_master([{"code": "510300.SH", "list_date": "20120528", "csname": "CSI300"}])
    store.upsert_fund_daily("510300.SH", [{"trade_date": "2026-06-11", "close": 4.05}])
    store.upsert_etf_share_size([{"code": "510300.SH", "trade_date": "2026-06-11", "total_size": 100}])
    store.upsert_index_master([{"code": "zssh.000300", "name": "CSI300", "type": "zssh"}])
    store.upsert_index_daily("000300.SH", [{"trade_date": "2026-06-11", "close": 4000}])
    store.upsert_board_master([{"code": "bki.880001", "name": "Industry", "board_type": "industry"}])
    store.upsert_board_members("bki.880001", "industry", [{"code": "600206.SH", "name": "X"}])
    store.upsert_board_daily("bki.880001", [{"trade_date": "2026-06-11", "close": 100}])
    counts = store.table_counts()
    assert counts["trade_calendar"] == 1
    assert counts["security_master"] == 1
    assert counts["bars_daily"] == 2
    assert counts["realtime_quote_snapshot"] == 1
    assert counts["stock_daily_basic"] == 1
    assert counts["etf_master"] == 1
    assert counts["fund_daily"] == 1
    assert counts["etf_share_size"] == 1
    assert counts["index_master"] == 1
    assert counts["index_daily"] == 1
    assert counts["board_master"] == 1
    assert counts["board_members"] == 1
    assert counts["board_daily"] == 1
    assert store.date_range("trade_calendar") == ("2026-06-11", "2026-06-11")
    lo, hi = store.date_range("bars_daily")
    assert lo == "2026-06-10" and hi == "2026-06-11"
    assert store.date_range("realtime_quote_snapshot") == ("2026-06-11", "2026-06-11")
    assert store.date_range("stock_daily_basic") == ("2026-06-11", "2026-06-11")
    assert store.date_range("etf_master") == ("20120528", "20120528")
    assert store.date_range("fund_daily") == ("2026-06-11", "2026-06-11")
    assert store.date_range("etf_share_size") == ("2026-06-11", "2026-06-11")
    assert store.date_range("index_master") != (None, None)
    assert store.date_range("index_daily") == ("2026-06-11", "2026-06-11")
    assert store.date_range("board_master") != (None, None)
    assert store.date_range("board_members") != (None, None)
    assert store.date_range("board_daily") == ("2026-06-11", "2026-06-11")


def test_market_coverage_and_missing_daily_codes(store: MarketStore) -> None:
    store.upsert_security_master(
        [
            {"code": "000001.SZ", "symbol": "000001", "name": "A", "list_status": "L"},
            {"code": "000002.SZ", "symbol": "000002", "name": "B", "list_status": "L"},
            {"code": "000003.SZ", "symbol": "000003", "name": "ST B", "list_status": "L", "is_st": True},
            {"code": "430001.BJ", "symbol": "430001", "name": "BJ", "list_status": "L", "is_bj": True},
        ]
    )
    _upsert_daily(store, "000001.SZ", [_row("2026-06-10")])

    cov = store.market_coverage()
    assert cov["security_total"] == 4
    assert cov["security_default"] == 2
    assert cov["daily_codes"] == 1
    assert cov["daily_default_codes"] == 1
    assert cov["daily_default_missing_codes"] == 1
    assert cov["stock_daily_basic_rows"] == 0
    assert cov["etf_master_rows"] == 0
    assert cov["etf_share_size_rows"] == 0
    assert cov["index_daily_rows"] == 0
    assert cov["date_ranges"]["bars_daily"] == ["2026-06-10", "2026-06-10"]
    assert store.missing_daily_codes() == ["000002.SZ"]


def test_fund_snapshot_codes_filters_type(store: MarketStore) -> None:
    store.upsert_fund_premium(
        "2026-06-24",
        [
            {"code": "510300", "type": "ETF"},
            {"code": "160105", "type": "LOF"},
            {"code": "159919", "type": "ETF"},
        ],
    )
    assert store.fund_snapshot_codes(fund_type="ETF") == ["159919", "510300"]
    assert store.fund_snapshot_codes() == ["159919", "160105", "510300"]


def test_has_etf_daily(store: MarketStore) -> None:
    assert store.has_etf_daily("510300", "2026-06-24") is False
    store.upsert_etf_daily("510300", [{"date": "2026-06-24", "close": 4.05}])
    assert store.has_etf_daily("510300", "2026-06-24") is True


def test_missing_etf_daily_codes(store: MarketStore) -> None:
    store.upsert_fund_premium(
        "2026-06-24",
        [
            {"code": "510300", "type": "ETF"},
            {"code": "159919", "type": "ETF"},
            {"code": "160105", "type": "LOF"},
        ],
    )
    store.upsert_etf_daily("510300", [{"date": "2026-06-24", "close": 4.05}])
    assert store.missing_etf_daily_codes("2026-06-24") == ["159919"]
