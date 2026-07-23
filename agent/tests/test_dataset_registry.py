from __future__ import annotations

from src.data.dataset_registry import contract_for


def test_recommendation_inputs_keep_realistic_minimums() -> None:
    assert contract_for("hot_list").minimum_rows >= 20
    assert contract_for("capital_rank").minimum_rows >= 20
    assert contract_for("sector_snapshot").minimum_rows >= 10
    # market_breadth is advisory: a missing breadth snapshot must not block
    # publication of the whole run (it degrades recommendations, not the data).
    assert contract_for("market_breadth").blocking is False


def test_core_universe_contracts_block_publication() -> None:
    # Only the structural backbone blocks the whole snapshot when it fails.
    # daily_basic is intentionally advisory: it is tushare-only with no degraded
    # fallback, so making it blocking would let a single rate-limited fetch
    # freeze the entire core publish (see dataset_registry._CRITICAL note).
    for dataset in ("master", "index", "calendar"):
        assert contract_for(dataset).blocking is True
    assert contract_for("daily_basic").blocking is False


def test_market_wide_snapshots_are_advisory_not_blocking() -> None:
    # realtime/board_members minimums stay high so PARTIAL is recorded, but a
    # rate-limited provider must not freeze the live DB for the day.
    assert contract_for("realtime").minimum_rows >= 3000
    assert contract_for("realtime").blocking is False
    assert contract_for("board_members").minimum_rows >= 3000
    assert contract_for("board_members").blocking is False


def test_sector_snapshot_components_remain_observable_but_advisory() -> None:
    for dataset in ("sector_snapshot_industry", "sector_snapshot_concept"):
        contract = contract_for(dataset)
        assert contract.minimum_rows >= 10
        assert contract.blocking is False


def test_composite_provider_components_remain_observable_but_optional() -> None:
    for dataset in (
        "zt_pool_eastmoney",
        "zt_pool_ths",
        "zb_pool_eastmoney",
        "dt_pool_eastmoney",
        "yzt_pool_eastmoney",
        "hot_list_ths",
        "hot_list_eastmoney",
    ):
        contract = contract_for(dataset)
        assert contract.minimum_rows == 1
        assert contract.blocking is False


def test_optional_dataset_missing_is_degraded_not_silently_verified() -> None:
    contract = contract_for("stock_news")

    assert contract.minimum_rows >= 1
    assert contract.blocking is False
