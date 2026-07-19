"""Observability for silent provider failures and per-dataset readiness.

Covers the gap where a provider returns an empty result, the sync records it as
``sync_error:{dataset}:{source}`` meta, but nothing surfaces the failure — so a
run blocked on row count looks like a mystery until someone opens the container
and queries sqlite by hand.
"""

from __future__ import annotations

from pathlib import Path

from src.data.market_store import MarketStore


def test_list_sync_errors_reports_active_failures(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    store.set_meta(
        "sync_error:realtime:tpdog.current_funds",
        '{"dataset":"realtime","source":"tpdog.current_funds","message":"rate limited","at":"2026-07-16T15:00:00+08:00"}',
    )

    errors = store.list_sync_errors("realtime")

    assert len(errors) == 1
    assert errors[0]["dataset"] == "realtime"
    assert errors[0]["source"] == "tpdog.current_funds"
    assert "rate limited" in errors[0]["message"]


def test_list_sync_errors_excludes_cleared_and_other_datasets(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    store.set_meta(
        "sync_error:realtime:tpdog.current_funds",
        '{"dataset":"realtime","source":"tpdog.current_funds","message":"","ok":true,"at":"2026-07-16T15:05:00+08:00"}',
    )
    store.set_meta(
        "sync_error:hot_list:astock_client.ths_hot",
        '{"dataset":"hot_list","source":"astock_client.ths_hot","message":"empty result","at":"2026-07-16T15:00:00+08:00"}',
    )

    realtime_errors = store.list_sync_errors("realtime")
    all_errors = store.list_sync_errors()

    # The recovered (ok=True) realtime entry must not appear as an active error.
    assert realtime_errors == []
    # The hot_list failure is still active and visible in the unfiltered list.
    assert [e["dataset"] for e in all_errors] == ["hot_list"]


def test_list_sync_errors_tolerates_corrupt_meta(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    store.set_meta("sync_error:realtime:broken", "not-json-at-all")

    # A corrupt meta row must not raise; it is simply skipped.
    assert store.list_sync_errors("realtime") == []
