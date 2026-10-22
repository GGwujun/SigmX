from __future__ import annotations

from src.data.dataset_registry import (
    _SPECS,
    contract_for,
    intraday_datasets,
    keep_days_for,
    post_close_core,
    post_close_datasets,
    premarket_datasets,
    table_map,
)


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
    # freeze the entire core publish (see registry daily_basic notes).
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


# ---------------------------------------------------------------------------
# 快照一致性：下面这些字面量是迁移前 worker/market_sync 里手抄的原始值
# （commit 50eae59 之前的 _POST_CLOSE_DATASETS / _POST_CLOSE_CORE /
# _DATASET_TABLE / _INTRADAY_DATASETS / _PREMARKET_DATASETS / prune 默认值）。
# 注册表派生结果必须与它们精确相等——新增 dataset 时同步改字面量，这是
# 有意识的二次确认，不是漂移。
# ---------------------------------------------------------------------------

_OLD_POST_CLOSE = {
    "calendar", "master", "index_master", "board_master", "board_members",
    "daily", "daily_basic", "dragon", "pool", "etf", "fund_daily", "etf_master",
    "fund_master", "etf_size", "index", "board", "capital", "capital_rank",
    "sector_capital", "sector_snapshot", "market_breadth", "global_indices",
    "us_theme", "us_transmission", "premarket_news", "stage_snapshot",
    "premium", "ths_hot", "zt_pool", "hot_list", "eps_forecast",
    "financial_snapshot", "financial_statement", "announcements",
    "fund_flow_daily", "fund_flow_120d", "option_chain", "margin_trading",
    "block_trade", "holder_num", "dividend_history", "northbound",
    "cls_telegraph", "irm_qa", "stock_news", "lockup_expiry", "fq_factors",
    "minute_bars", "unusual", "hot_money", "hot_money_list", "shortline",
}

_OLD_POST_CLOSE_CORE = {"calendar", "master", "daily_basic", "index", "daily"}

_OLD_PREMARKET = {
    "global_indices", "us_theme", "us_transmission", "premarket_news",
    "stage_snapshot",
}

_OLD_INTRADAY = {
    "realtime", "pool", "capital_rank", "sector_capital", "sector_snapshot",
    "market_breadth", "stage_snapshot", "ths_hot", "zt_pool", "hot_list",
    "northbound", "cls_telegraph", "shortline",
}

_OLD_DATASET_TABLE = {
    "calendar": "trade_calendar", "master": "security_master",
    "index_master": "index_master", "board_master": "board_master",
    "board_members": "board_members", "daily": "bars_daily",
    "daily_basic": "stock_daily_basic", "index": "index_daily",
    "etf": "etf_daily", "etf_master": "etf_master", "fund_master": "fund_master",
    "fund_daily": "fund_daily", "etf_size": "etf_share_size",
    "dragon": "dragon_tiger", "pool": "stock_pool", "zt_pool": "zt_pool",
    "zb_pool": "zb_pool", "dt_pool": "dt_pool", "yzt_pool": "yzt_pool",
    "ths_hot": "ths_limit_up", "capital": "stock_capital_flow",
    "capital_rank": "stock_capital_rank", "sector_capital": "sector_capital_flow",
    "sector_snapshot": "sector_snapshot",
    "sector_snapshot_industry": "sector_snapshot_industry",
    "sector_snapshot_concept": "sector_snapshot_concept",
    "market_breadth": "market_breadth_snapshot",
    "global_indices": "global_market_index_daily", "us_theme": "us_theme_snapshot",
    "us_transmission": "us_a_share_transmission",
    "premarket_news": "premarket_news",
    "stage_snapshot": "market_stage_snapshot", "premium": "fund_premium_snapshot",
    "shortline": "shortline_snapshot",
    "board": "board_daily", "hot_list": "hot_list", "eps_forecast": "eps_forecast",
    "financial_snapshot": "financial_snapshot",
    "financial_statement": "financial_statement",
    "announcements": "announcements", "fund_flow_daily": "fund_flow_daily",
    "fund_flow_120d": "fund_flow_daily", "option_chain": "option_chain",
    "margin_trading": "margin_trading", "block_trade": "block_trade",
    "holder_num": "holder_num", "dividend_history": "dividend_history",
    "northbound": "northbound_flow", "cls_telegraph": "cls_telegraph",
    "irm_qa": "irm_qa", "stock_news": "stock_news",
    "lockup_expiry": "lockup_expiry", "fq_factors": "fq_factors",
    "minute_bars": "minute_bars", "unusual": "unusual_event",
    "call_auction": "call_auction_snapshot", "hot_money": "hot_money_daily",
    "hot_money_list": "hot_money_list",
}


def test_derived_post_close_matches_pre_registry_literal() -> None:
    assert post_close_datasets() == frozenset(_OLD_POST_CLOSE)


def test_derived_core_matches_pre_registry_literal() -> None:
    assert post_close_core() == frozenset(_OLD_POST_CLOSE_CORE)


def test_derived_premarket_matches_pre_registry_literal() -> None:
    assert premarket_datasets() == frozenset(_OLD_PREMARKET)


def test_derived_intraday_matches_pre_registry_literal() -> None:
    assert intraday_datasets() == frozenset(_OLD_INTRADAY)


def test_derived_table_map_matches_pre_registry_literal() -> None:
    assert table_map() == _OLD_DATASET_TABLE


def test_worker_constants_are_derived_from_registry() -> None:
    # worker 与 market_sync 的模块级常量不再是手抄清单，必须与注册表同源。
    from src.data import market_sync, market_sync_worker

    assert market_sync_worker._POST_CLOSE_DATASETS == post_close_datasets()
    assert market_sync_worker._POST_CLOSE_CORE == post_close_core()
    assert market_sync_worker._DATASET_TABLE == table_map()
    assert market_sync._INTRADAY_DATASETS == intraday_datasets()
    assert market_sync._PREMARKET_DATASETS == premarket_datasets()


def test_keep_days_defaults_and_env_override(monkeypatch) -> None:
    # 迁移前默认值：minute_bars 60 / unusual 120 / call_auction 60。
    monkeypatch.delenv("MARKET_SYNC_MINUTE_BARS_KEEP_DAYS", raising=False)
    monkeypatch.delenv("MARKET_SYNC_UNUSUAL_KEEP_DAYS", raising=False)
    monkeypatch.delenv("MARKET_SYNC_CALL_AUCTION_KEEP_DAYS", raising=False)
    assert keep_days_for("minute_bars") == 60
    assert keep_days_for("unusual") == 120
    assert keep_days_for("call_auction") == 60
    # env 覆盖仍然生效（部署侧调优入口保留）。
    monkeypatch.setenv("MARKET_SYNC_MINUTE_BARS_KEEP_DAYS", "10")
    assert keep_days_for("minute_bars") == 10
    # 无 prune 语义的 dataset 返回 None（无默认保留天数可取）。
    assert keep_days_for("daily") is None
    assert keep_days_for("__missing__") is None


def test_advisory_minimums_match_pre_registry_literals() -> None:
    # 迁移前 _ADVISORY 的行数下限逐条固化。
    expected = {
        "board_members": 3000, "realtime": 3000, "daily_basic": 1000,
        "capital_rank": 20, "sector_capital": 10, "sector_snapshot": 10,
        "sector_snapshot_industry": 10, "sector_snapshot_concept": 10,
        "market_breadth": 1, "stage_snapshot": 1, "ths_hot": 5, "zt_pool": 1,
        "hot_list": 20, "cls_telegraph": 5, "fq_factors": 3000,
        "minute_bars": 100, "unusual": 5, "hot_money": 10,
    }
    for dataset, minimum in expected.items():
        assert contract_for(dataset).minimum_rows == minimum, dataset
    # 临界集：calendar 1 / master 3000 / index 4。
    assert contract_for("calendar").minimum_rows == 1
    assert contract_for("master").minimum_rows == 3000
    assert contract_for("index").minimum_rows == 4


def test_recommendation_input_set_matches_pre_registry_literal() -> None:
    expected = {
        "daily", "realtime", "capital_rank", "sector_capital",
        "sector_snapshot", "market_breadth", "stage_snapshot", "ths_hot",
        "zt_pool", "hot_list", "northbound", "cls_telegraph", "stock_news",
        "fund_flow_daily",
    }
    actual = {d for d in _SPECS if contract_for(d).recommendation_input}
    assert actual == expected


def test_hard_fail_set_matches_pre_registry_literal() -> None:
    expected = {
        "realtime", "capital_rank", "sector_capital", "market_breadth",
        "master", "board_members",
    }
    actual = {d for d in _SPECS if contract_for(d).hard_fail_on_zero_valid}
    assert actual == expected


def test_registry_invariants() -> None:
    valid_phases = {"premarket", "intraday", "post_close"}
    assert len(_SPECS) == 59  # 58 张表 + realtime
    for dataset, spec in _SPECS.items():
        assert spec.id == dataset  # 键与 id 一致（dict 构造已保证，显式断言防手滑）
        assert spec.phases <= valid_phases, dataset
        assert spec.source, dataset
        if spec.invalidation == "rolling_days":
            # rolling 必有保留天数，否则 prune 永远不会跑。
            assert spec.keep_days, dataset
        if spec.invalidation == "cumulative":
            # 累积型不得配 prune（fq_factors 全量保留）。
            assert spec.keep_days is None, dataset
        assert spec.invalidation in ("per_day", "cumulative", "rolling_days")
    # 核心集必须是收盘相位的子集（tier-1 先于增强集发布的前提）。
    assert post_close_core() <= post_close_datasets()
    # 全部表名互不相同（fund_flow_daily/fund_flow_120d 有意共用一张表，例外）。
    tables = [t for t in (s.table for s in _SPECS.values()) if t]
    assert len(tables) - len(set(tables)) == 1  # 仅 fund_flow_daily 一对共用
