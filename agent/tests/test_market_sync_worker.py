"""Strict publication-gate tests for the standalone market sync worker."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data import market_sync_worker as worker
from src.data.market_quality import (
    DatasetQualityReport,
    QualityStatus,
    ReferenceResult,
    SuspensionResult,
)
from src.data.market_store import MarketStore


def test_post_close_worker_includes_long_horizon_fund_flow() -> None:
    assert "fund_flow_120d" in worker._POST_CLOSE_DATASETS


def test_empty_recommendation_dataset_blocks_shadow_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"hot_list": 0})
    monkeypatch.setattr(worker, "_publish_shadow", lambda *args, **kwargs: pytest.fail("published"))

    with pytest.raises(worker.MarketDataQualityError, match="hot_list"):
        worker._run_post_close_shadow_sync(
            "2026-07-14",
            live_db=live,
            shadow_db=shadow,
            datasets={"hot_list"},
            deadline_seconds=60,
            lookback_days=30,
        )


def test_nonempty_extended_dataset_gets_published_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"hot_list": 12})

    worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"hot_list"},
        deadline_seconds=60,
        lookback_days=30,
    )

    readiness = MarketStore(live).get_data_readiness("hot_list", "2026-07-14")
    assert readiness.status is QualityStatus.PUBLISHED
    assert readiness.published_rows == 12


def _report(status: QualityStatus) -> DatasetQualityReport:
    return DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=status,
        expected_rows=1,
        received_rows=1 if status is QualityStatus.VERIFIED else 0,
        valid_rows=1 if status is QualityStatus.VERIFIED else 0,
        missing_codes=[] if status is QualityStatus.VERIFIED else ["600000.SH"],
        blocking_reasons=[] if status is QualityStatus.VERIFIED else ["unexplained_missing_codes"],
        source="tushare.daily",
    )


def _seed_live(path: Path) -> None:
    store = MarketStore(path)
    store.upsert_security_master(
        [{"code": "600000.SH", "name": "PF Bank", "list_status": "L"}]
    )
    store._conn.close()


def test_partial_daily_dataset_is_not_published(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"daily": 0})
    monkeypatch.setattr(worker, "fetch_suspended_codes", lambda *args, **kwargs: SuspensionResult.success(set()))
    monkeypatch.setattr(worker, "fetch_daily_reference_closes", lambda *args, **kwargs: ReferenceResult.success({}))
    monkeypatch.setattr(worker, "validate_daily_dataset", lambda *args, **kwargs: _report(QualityStatus.PARTIAL))
    published = False

    def fail_if_published(*args, **kwargs):
        nonlocal published
        published = True

    monkeypatch.setattr(worker, "_publish_shadow", fail_if_published)

    with pytest.raises(worker.MarketDataQualityError):
        worker._run_post_close_shadow_sync(
            "2026-07-14",
            live_db=live,
            shadow_db=shadow,
            datasets={"daily"},
            deadline_seconds=60,
            lookback_days=30,
        )

    assert published is False
    assert MarketStore(live).get_meta("daemon:2026-07-14") is None


def test_verified_daily_dataset_publishes_and_marks_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"daily": 1})
    monkeypatch.setattr(worker, "fetch_suspended_codes", lambda *args, **kwargs: SuspensionResult.success(set()))
    monkeypatch.setattr(worker, "fetch_daily_reference_closes", lambda *args, **kwargs: ReferenceResult.success({}))
    monkeypatch.setattr(worker, "validate_daily_dataset", lambda *args, **kwargs: _report(QualityStatus.VERIFIED))

    result = worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"daily"},
        deadline_seconds=60,
        lookback_days=30,
    )

    live_store = MarketStore(live)
    assert result == {"daily": 1}
    assert live_store.get_meta("daemon:2026-07-14") is not None
    assert live_store.get_data_readiness("bars_daily", "2026-07-14").status is QualityStatus.PUBLISHED


def test_swallowed_dataset_failure_blocks_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"daily": 1})

    with pytest.raises(worker.MarketDataQualityError, match="missing dataset results"):
        worker._run_post_close_shadow_sync(
            "2026-07-14",
            live_db=live,
            shadow_db=shadow,
            datasets={"daily", "index"},
            deadline_seconds=60,
            lookback_days=30,
        )

    assert MarketStore(live).get_meta("daemon:2026-07-14") is None


def test_run_once_rejects_unsafe_no_shadow_mode() -> None:
    with pytest.raises(ValueError, match="shadow publication is mandatory"):
        worker.run_once(shadow=False)
