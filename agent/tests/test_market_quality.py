"""Tests for strict market-data quality state."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.market_quality import (
    DataReadiness,
    DatasetQualityReport,
    QualityStatus,
    ReferenceResult,
    SuspensionResult,
    validate_daily_dataset,
)
from src.data.market_store import MarketStore


@pytest.fixture
def store(tmp_path: Path) -> MarketStore:
    value = MarketStore(tmp_path / "market.db")
    yield value
    value._conn.close()


def _insert_bar(
    store: MarketStore,
    *,
    code: str = "600000.SH",
    run_id: str = "run-1",
    close: float = 10.5,
    high: float = 11.0,
) -> None:
    store.upsert_daily_bars(
        code,
        [{"date": "2026-07-14", "open": 10, "high": high, "low": 9, "close": close, "volume": 100}],
        source="tushare.daily",
        sync_run_id=run_id,
    )


def test_data_readiness_only_accepts_verified_or_published() -> None:
    base = dict(
        dataset="bars_daily",
        as_of="2026-07-14",
        expected_rows=2,
        valid_rows=2,
        published_rows=0,
        source="tushare.daily",
        run_id="run-1",
    )

    assert DataReadiness(status=QualityStatus.VERIFIED, **base).ready is True
    assert DataReadiness(status=QualityStatus.PUBLISHED, **base).ready is True
    assert DataReadiness(status=QualityStatus.PARTIAL, **base).ready is False
    assert DataReadiness(status=QualityStatus.QUARANTINED, **base).ready is False


def test_dataset_report_defaults_are_isolated() -> None:
    first = DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=QualityStatus.PARTIAL,
        expected_rows=2,
        received_rows=1,
        valid_rows=1,
    )
    second = DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=QualityStatus.VERIFIED,
        expected_rows=1,
        received_rows=1,
        valid_rows=1,
    )

    first.missing_codes.append("000001.SZ")
    assert second.missing_codes == []


def test_daily_validator_rejects_invalid_ohlc(store: MarketStore) -> None:
    _insert_bar(store, high=9.0)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.QUARANTINED
    assert report.invalid_rows[0]["code"] == "600000.SH"


def test_daily_validator_rejects_unexplained_missing_code(store: MarketStore) -> None:
    _insert_bar(store)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH", "000001.SZ"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.PARTIAL
    assert report.missing_codes == ["000001.SZ"]


def test_daily_validator_blocks_when_suspension_reference_unavailable(store: MarketStore) -> None:
    _insert_bar(store)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.unavailable("tushare timeout"),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.PARTIAL
    assert "suspension_reference_unavailable" in report.blocking_reasons


def test_daily_validator_blocks_when_cross_source_reference_unavailable(store: MarketStore) -> None:
    _insert_bar(store)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.unavailable("tpdog timeout"),
    )

    assert report.status == QualityStatus.PARTIAL
    assert "cross_source_reference_unavailable" in report.blocking_reasons


def test_daily_validator_excludes_confirmed_suspension(store: MarketStore) -> None:
    _insert_bar(store)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH", "000001.SZ"],
        "run-1",
        suspension_result=SuspensionResult.success({"000001.SZ"}),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.VERIFIED
    row = store._conn.execute(
        "SELECT quality_status FROM bars_daily WHERE code = '600000.SH'"
    ).fetchone()
    assert row["quality_status"] == "verified"


def test_daily_validator_quarantines_cross_source_close_mismatch(store: MarketStore) -> None:
    _insert_bar(store)

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({"600000.SH": 10.8}),
    )

    assert report.status == QualityStatus.QUARANTINED
    assert "cross_source_close_mismatch" in report.blocking_reasons


def test_daily_validator_ignores_rows_from_previous_run(store: MarketStore) -> None:
    _insert_bar(store, run_id="old-run")

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "new-run",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.PARTIAL
    assert report.received_rows == 0


def test_daily_validator_degrades_when_tdx_entirely_unavailable(store: MarketStore) -> None:
    # When the TongdaXin reference server is unreachable, tpdog-sourced bars
    # cannot be independently verified — but freezing the whole post-close run
    # on a flaky mootdx connection is worse than shipping unverifiable bars.
    # The run publishes (VERIFIED, no blocking reason) rather than blocking.
    store.upsert_daily_bars(
        "600000.SH",
        [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        source="tpdog.stock_his/daily",
        sync_run_id="run-1",
    )

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({"600000.SH": 10.5}),
        fallback_reference_result=ReferenceResult.unavailable("mootdx connection refused"),
    )

    assert report.status is QualityStatus.VERIFIED
    assert "unverified_fallback_source" not in report.blocking_reasons


def test_daily_validator_blocks_when_tdx_partially_reachable_but_coverage_low(
    store: MarketStore,
) -> None:
    # TDX is reachable (returned some closes) but covers too few of the
    # fallback codes — that signals real verification failure, not a network
    # outage, and must block publication.
    for code in ("600000.SH", "600001.SH", "600002.SH"):
        store.upsert_daily_bars(
            code,
            [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
            source="tpdog.stock_his/daily",
            sync_run_id="run-1",
        )

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH", "600001.SH", "600002.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({}),
        # Only 1 of 3 fallback codes resolved — below the 50% coverage floor.
        fallback_reference_result=ReferenceResult.unavailable(
            "partial", closes={"600000.SH": 10.5}
        ),
    )

    assert "fallback_reference_coverage_too_low" in report.blocking_reasons


def test_daily_validator_accepts_independently_verified_tpdog_fallback(
    store: MarketStore,
) -> None:
    store.upsert_daily_bars(
        "600000.SH",
        [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        source="tpdog.stock_his/daily",
        sync_run_id="run-1",
    )

    report = validate_daily_dataset(
        store,
        "2026-07-14",
        ["600000.SH"],
        "run-1",
        suspension_result=SuspensionResult.success(set()),
        reference_result=ReferenceResult.success({}),
        fallback_reference_result=ReferenceResult.success({"600000.SH": 10.5}),
    )

    assert report.status == QualityStatus.VERIFIED
    assert "unverified_fallback_source" not in report.blocking_reasons
