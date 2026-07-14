"""Tests for strict market-data quality state."""

from __future__ import annotations

from src.data.market_quality import DataReadiness, DatasetQualityReport, QualityStatus


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
