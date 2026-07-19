from __future__ import annotations

from src.data.market_store import MarketStore
from src.data.recommendation_features import history_readiness, load_recommendation_features


def _bars(count: int) -> list[dict]:
    return [
        {
            "date": f"2026-{1 + index // 28:02d}-{1 + index % 28:02d}",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 1000,
        }
        for index in range(count)
    ]


def test_history_readiness_requires_coverage_across_active_universe(tmp_path) -> None:
    store = MarketStore(tmp_path / "market.db")
    store.upsert_security_master(
        [
            {"ts_code": "600000.SH", "symbol": "600000", "name": "A", "list_status": "L"},
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "B", "list_status": "L"},
        ]
    )
    store.upsert_daily_bars("600000.SH", _bars(60), source="test", sync_run_id="run")

    partial = history_readiness(store, min_bars=60, min_codes=2, min_coverage=0.8)
    assert partial["ready"] is False
    assert partial["covered_codes"] == 1
    assert partial["coverage"] == 0.5

    store.upsert_daily_bars("000001.SZ", _bars(60), source="test", sync_run_id="run")
    complete = history_readiness(store, min_bars=60, min_codes=2, min_coverage=0.8)
    assert complete["ready"] is True


def test_local_feature_snapshot_rewards_auditable_hot_capital_signal(tmp_path) -> None:
    store = MarketStore(tmp_path / "market.db")
    trade_date = "2026-07-15"
    store.upsert_stock_capital_rank(
        trade_date,
        [{"code": "600000", "name": "A", "rank_type": "main_net", "main_net": 8_000_000}],
    )
    store.upsert_hot_list(
        trade_date,
        [{"code": "600000", "name": "A", "rank": 2, "hot_value": 99}],
    )
    store.upsert_ths_hot_reason(
        trade_date,
        [{"code": "600000", "name": "A", "reason": "industry catalyst"}],
    )
    store.upsert_market_breadth_snapshot(
        trade_date,
        {"total": 5000, "advancers": 3200, "decliners": 1700, "limit_up": 70, "limit_down": 5},
    )

    features = load_recommendation_features(
        store,
        ["600000.SH", "000001.SZ"],
        trade_date,
        require_published=False,
    )

    hot = features["600000.SH"]
    neutral = features["000001.SZ"]
    assert hot["status"] == "ok"
    assert hot["score"] > neutral["score"]
    assert {row["dataset"] for row in hot["signals"]} >= {
        "capital_rank",
        "hot_list",
        "ths_hot",
        "market_breadth",
    }
    assert hot["as_of"] == trade_date


def test_sector_capital_signal_matches_cross_source_industry_name(tmp_path) -> None:
    store = MarketStore(tmp_path / "market.db")
    trade_date = "2026-07-15"
    store.upsert_security_master(
        [{"code": "600000.SH", "symbol": "600000", "name": "浦发银行", "industry": "银行"}]
    )
    store.upsert_sector_capital(
        trade_date,
        [{"sector": "银行Ⅱ", "main_net": 80_000_000, "change_pct": 1.2}],
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        trade_date,
        require_published=False,
    )

    signals = features["600000.SH"]["signals"]
    sector_signal = next(row for row in signals if row["dataset"] == "sector_capital")
    assert sector_signal["sector"] == "银行Ⅱ"
    assert sector_signal["contribution"] == 0.08


def test_missing_breadth_does_not_collapse_symbol_to_limited(tmp_path) -> None:
    # Defect G: market_breadth is one market-wide row. When it is unavailable
    # every symbol used to fall to status="limited" and lose eligibility, even
    # with rich per-symbol evidence. Breadth absence must stay neutral.
    store = MarketStore(tmp_path / "market.db")
    trade_date = "2026-07-15"
    store.upsert_stock_capital_rank(
        trade_date,
        [{"code": "600000", "name": "A", "rank_type": "main_net", "main_net": 8_000_000}],
    )
    store.upsert_hot_list(
        trade_date,
        [{"code": "600000", "name": "A", "rank": 2, "hot_value": 99}],
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        trade_date,
        require_published=False,
    )

    hot = features["600000.SH"]
    assert hot["status"] != "limited"  # two symbol sources -> ok
    assert hot["breadth_available"] is False
    assert {row["dataset"] for row in hot["signals"]} == {"capital_rank", "hot_list"}


def test_single_symbol_source_is_partial_not_ok(tmp_path) -> None:
    store = MarketStore(tmp_path / "market.db")
    trade_date = "2026-07-15"
    store.upsert_hot_list(
        trade_date,
        [{"code": "600000", "name": "A", "rank": 2, "hot_value": 99}],
    )
    store.upsert_market_breadth_snapshot(
        trade_date,
        {"total": 5000, "advancers": 3200, "decliners": 1700, "limit_up": 70, "limit_down": 5},
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        trade_date,
        require_published=False,
    )

    # Only one per-symbol source fired -> partial (still eligible in scoring).
    assert features["600000.SH"]["status"] == "partial"


def test_fund_flow_daily_falls_back_to_previous_trading_day(tmp_path, monkeypatch) -> None:
    # Defect D: fund_flow_daily is produced only by the post-close sync, so at
    # intraday recommendation times the current day is never ready. The signal
    # must fall back to the prior trading day instead of disappearing.
    store = MarketStore(tmp_path / "market.db")
    today = "2026-07-15"
    prev = "2026-07-14"
    # Yesterday's fund flow exists; today's does not.
    store.upsert_fund_flow_daily(
        "600000.SH",
        [{"date": prev, "main_net": 5_000_000, "net_amount": 5_000_000, "source": "sina"}],
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        today,
        require_published=False,
    )

    ff = next(
        row for row in features["600000.SH"]["signals"] if row["dataset"] == "fund_flow_daily"
    )
    assert ff["is_fallback"] is True
    assert ff["as_of"] == prev


def test_fund_flow_daily_fallback_survives_when_today_rows_also_present(tmp_path) -> None:
    # The MAX-date guard must NOT invalidate a prior-day fallback read when the
    # table legitimately holds today's rows on top of yesterday's. This is the
    # normal production state (today's sync already wrote rows even if its
    # readiness record is not yet ready at intraday recommendation time).
    store = MarketStore(tmp_path / "market.db")
    today = "2026-07-15"
    prev = "2026-07-14"
    # Both dates present in the table.
    store.upsert_fund_flow_daily(
        "600000.SH",
        [{"date": prev, "main_net": 5_000_000, "net_amount": 5_000_000, "source": "sina"}],
    )
    store.upsert_fund_flow_daily(
        "600000.SH",
        [{"date": today, "main_net": 9_000_000, "net_amount": 9_000_000, "source": "sina"}],
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        today,
        # require_published=False makes today "available" by readiness, so the
        # current-day path reads today's rows directly — no fallback expected.
        require_published=False,
    )
    ff_today = next(
        row for row in features["600000.SH"]["signals"] if row["dataset"] == "fund_flow_daily"
    )
    assert ff_today["is_fallback"] is False
    assert ff_today["as_of"] == today


def test_fund_flow_daily_fallback_reads_prev_when_today_unverified_but_present(
    tmp_path, monkeypatch
) -> None:
    # The CRITICAL regression: today's rows exist in the table but today's
    # readiness is NOT ready (require_published gate fails), so we fall back to
    # prev. The fallback must still return prev's rows despite today being the
    # table MAX.
    store = MarketStore(tmp_path / "market.db")
    today = "2026-07-15"
    prev = "2026-07-14"
    store.upsert_fund_flow_daily(
        "600000.SH",
        [{"date": prev, "main_net": 5_000_000, "net_amount": 5_000_000, "source": "sina"}],
    )
    store.upsert_fund_flow_daily(
        "600000.SH",
        [{"date": today, "main_net": 9_000_000, "net_amount": 9_000_000, "source": "sina"}],
    )
    # Simulate "today not published yet" while yesterday is published.
    from src.data import recommendation_features as rf

    monkeypatch.setattr(
        rf,
        "_dataset_available",
        lambda store, dataset, trade_date, require_published: trade_date == prev,
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        today,
        require_published=True,
    )
    ff = next(
        row for row in features["600000.SH"]["signals"] if row["dataset"] == "fund_flow_daily"
    )
    assert ff["is_fallback"] is True
    assert ff["as_of"] == prev


def test_sector_capital_matches_via_canonical_when_only_suffix_differs(tmp_path) -> None:
    # Defect H: a stock's master industry "半导体" must match a sector row named
    # "半导体板块" (same sector, different source naming). The canonical key
    # strips the "板块" suffix, so the match resolves uniquely.
    store = MarketStore(tmp_path / "market.db")
    trade_date = "2026-07-15"
    store.upsert_security_master(
        [{"code": "600000.SH", "symbol": "600000", "name": "A", "industry": "半导体"}]
    )
    store.upsert_sector_capital(
        trade_date,
        [{"sector": "半导体板块", "main_net": 80_000_000, "change_pct": 1.2}],
    )

    features = load_recommendation_features(
        store,
        ["600000.SH"],
        trade_date,
        require_published=False,
    )

    sector = next(
        row for row in features["600000.SH"]["signals"] if row["dataset"] == "sector_capital"
    )
    assert sector["sector"] == "半导体板块"
