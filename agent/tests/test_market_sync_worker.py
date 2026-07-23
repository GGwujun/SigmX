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


def test_post_close_worker_includes_board_members() -> None:
    assert "board_members" in worker._POST_CLOSE_DATASETS


def test_component_results_are_recorded_independently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(
        worker,
        "run_daily_sync",
        lambda *args, **kwargs: {"zt_pool": 5, "zt_pool_eastmoney": 0, "zt_pool_ths": 5},
    )

    worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"zt_pool"},
        deadline_seconds=60,
        lookback_days=30,
    )

    live_store = MarketStore(live)
    assert live_store.get_data_readiness("zt_pool_ths", "2026-07-14").status is QualityStatus.PUBLISHED
    assert live_store.get_data_readiness("zt_pool_eastmoney", "2026-07-14").status is QualityStatus.PARTIAL


def test_empty_advisory_dataset_publishes_but_marks_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # hot_list is advisory: a provider returning nothing must not freeze the
    # whole day's snapshot.  The run publishes, but readiness records PARTIAL so
    # the recommendation layer senses the gap.
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"hot_list": 0})

    rows = worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"hot_list"},
        deadline_seconds=60,
        lookback_days=30,
    )

    assert rows == {"hot_list": 0}
    readiness = MarketStore(live).get_data_readiness("hot_list", "2026-07-14")
    assert readiness.status is worker.QualityStatus.PARTIAL
    assert "row_count_below_minimum" in readiness.blocking_reasons


def test_semantically_invalid_realtime_rows_block_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)

    def fake_sync(*args, **kwargs):
        target = kwargs["store"]
        rows = [
            {
                "code": f"{idx:06d}.SZ",
                "name": f"S{idx}",
                "price": 0,
                "pre_close": 10,
                "volume": 1,
                "source": "broken-provider",
            }
            for idx in range(3000)
        ]
        assert target.upsert_realtime_quotes("2026-07-14", rows) == 3000
        return {"realtime": 3000}

    monkeypatch.setattr(worker, "run_daily_sync", fake_sync)

    with pytest.raises(worker.MarketDataQualityError, match="realtime"):
        worker._run_post_close_shadow_sync(
            "2026-07-14",
            live_db=live,
            shadow_db=shadow,
            datasets={"realtime"},
            deadline_seconds=60,
            lookback_days=30,
        )

    assert MarketStore(live).get_meta("daemon:2026-07-14") is None


def test_incomplete_realtime_universe_publishes_but_marks_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Realtime coverage shortfall (rate-limited provider) is degradable: the
    # 3000 valid quotes are not corrupt, so the run publishes even though the
    # 4000-code universe is only 75% covered.  Readiness records the shortfall.
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    store = MarketStore(live)
    store.upsert_security_master(
        [
            {
                "code": f"{idx:06d}.SZ",
                "symbol": f"{idx:06d}",
                "name": f"S{idx}",
                "list_status": "L",
            }
            for idx in range(4000)
        ]
    )
    store._conn.close()

    def fake_sync(*args, **kwargs):
        target = kwargs["store"]
        quotes = [
            {
                "code": f"{idx:06d}.SZ",
                "name": f"S{idx}",
                "price": 10,
                "pre_close": 9.9,
                "volume": 1,
                "source": "partial-provider",
            }
            for idx in range(3000)
        ]
        target.upsert_realtime_quotes("2026-07-14", quotes)
        return {"realtime": len(quotes)}

    monkeypatch.setattr(worker, "run_daily_sync", fake_sync)

    rows = worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"realtime"},
        deadline_seconds=60,
        lookback_days=30,
    )

    assert rows["realtime"] == 3000
    readiness = MarketStore(live).get_data_readiness("realtime", "2026-07-14")
    assert readiness.status is worker.QualityStatus.PARTIAL
    assert "realtime_universe_coverage_below_threshold" in readiness.blocking_reasons
    assert MarketStore(live).get_meta("daemon:2026-07-14") is not None


def test_nonempty_extended_dataset_gets_published_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"hot_list": 30})

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
    assert readiness.published_rows == 30


def test_optional_empty_dataset_is_partial_without_blocking_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"stock_news": 0})

    worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"stock_news"},
        deadline_seconds=60,
        lookback_days=30,
    )

    readiness = MarketStore(live).get_data_readiness("stock_news", "2026-07-14")
    assert readiness.status is QualityStatus.PARTIAL
    assert readiness.ready is False
    assert readiness.blocking_reasons == ["row_count_below_minimum"]


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


def test_independently_verified_tpdog_fallback_can_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)

    def fake_sync(*args, **kwargs):
        target = kwargs["store"]
        target.upsert_daily_bars(
            "600000.SH",
            [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
            source="tpdog.stock_his/daily",
            sync_run_id=kwargs["sync_run_id"],
        )
        return {"daily": 1}

    monkeypatch.setattr(worker, "run_daily_sync", fake_sync)
    monkeypatch.setattr(worker, "fetch_suspended_codes", lambda *args, **kwargs: SuspensionResult.success(set()))
    monkeypatch.setattr(worker, "fetch_daily_reference_closes", lambda *args, **kwargs: ReferenceResult.success({}))
    monkeypatch.setattr(
        worker,
        "fetch_tdx_reference_closes",
        lambda *args, **kwargs: ReferenceResult.success({"600000.SH": 10.5}),
        raising=False,
    )

    result = worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"daily"},
        deadline_seconds=60,
        lookback_days=30,
    )

    assert result == {"daily": 1}
    assert MarketStore(live).get_data_readiness("bars_daily", "2026-07-14").ready is True


def test_swallowed_dataset_failure_blocks_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A missing critical dataset (provider temporarily unavailable) is lenient
    # by default: it degrades to PARTIAL + warning rather than freezing the
    # whole day's publish. Hard-block happens only under MARKET_SYNC_CORE_STRICT=1.
    live = tmp_path / "live.db"
    shadow = tmp_path / "shadow.db"
    _seed_live(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *args, **kwargs: {"daily": 1})

    # Default (lenient): missing index does NOT raise; the run still publishes.
    monkeypatch.delenv("MARKET_SYNC_CORE_STRICT", raising=False)
    result = worker._run_post_close_shadow_sync(
        "2026-07-14",
        live_db=live,
        shadow_db=shadow,
        datasets={"daily", "index"},
        deadline_seconds=60,
        lookback_days=30,
    )
    assert result == {"daily": 1}

    # Strict mode: the same missing critical dataset must hard-block publication.
    monkeypatch.setenv("MARKET_SYNC_CORE_STRICT", "1")
    live2 = tmp_path / "live2.db"
    shadow2 = tmp_path / "shadow2.db"
    _seed_live(live2)
    with pytest.raises(worker.MarketDataQualityError, match="missing critical dataset results"):
        worker._run_post_close_shadow_sync(
            "2026-07-14",
            live_db=live2,
            shadow_db=shadow2,
            datasets={"daily", "index"},
            deadline_seconds=60,
            lookback_days=30,
        )
    assert MarketStore(live2).get_meta("daemon:2026-07-14") is None


def test_run_once_rejects_unsafe_no_shadow_mode() -> None:
    with pytest.raises(ValueError, match="shadow publication is mandatory"):
        worker.run_once(shadow=False)
