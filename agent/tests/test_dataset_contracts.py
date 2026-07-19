from __future__ import annotations

from src.data.dataset_contracts import run_provider_chain, validate_dataset


def test_baidu_kline_rejects_empty_truthy_payload() -> None:
    result = validate_dataset("baidu_kline", {"keys": [], "rows": []})

    assert result.valid is False
    assert "no usable rows" in result.reasons


def test_eps_forecast_rejects_placeholder_row() -> None:
    result = validate_dataset(
        "eps_forecast",
        [{"year": "2026", "institution_count": 0, "eps_mean": 68.83}],
    )

    assert result.valid is False
    assert "institution_count must be positive" in result.reasons


def test_provider_chain_falls_back_and_records_rejection() -> None:
    result = run_provider_chain(
        "fund_flow_daily",
        [
            ("eastmoney", lambda: []),
            ("sina", lambda: [{"date": "2026-07-14", "main_net": 12.0}]),
        ],
        trade_date="2026-07-14",
    )

    assert result.source == "sina"
    assert result.rows == [{"date": "2026-07-14", "main_net": 12.0}]
    assert result.attempts[0].source == "eastmoney"
    assert result.attempts[0].valid is False


def test_northbound_rejects_rows_without_a_reliable_channel() -> None:
    result = validate_dataset(
        "northbound_flow",
        [{"time": "10:00", "hgt_yi": None, "sgt_yi": None}],
        trade_date="2026-07-14",
    )

    assert result.valid is False
    assert "no reliable northbound channel" in result.reasons


def test_realtime_rejects_invalid_prices_and_duplicate_codes() -> None:
    result = validate_dataset(
        "realtime",
        [
            {"code": "600000.SH", "price": 0, "pre_close": 10, "volume": 1},
            {"code": "600001.SH", "price": 10, "pre_close": 0, "volume": 1},
            {"code": "600002.SH", "price": 10, "pre_close": 9, "volume": -1},
            {"code": "600003.SH", "price": 10, "pre_close": 9, "volume": 0},
            {"code": "600003.SH", "price": 11, "pre_close": 9, "volume": 0},
        ],
    )

    assert result.valid is True
    assert result.rows == [
        {"code": "600003.SH", "price": 10, "pre_close": 9, "volume": 0}
    ]


def test_market_breadth_rejects_impossible_arithmetic() -> None:
    result = validate_dataset(
        "market_breadth",
        [{"total": 100, "advancers": 80, "decliners": 40, "limit_up": 5, "limit_down": 2}],
    )

    assert result.valid is False
    assert "breadth counts exceed total" in result.reasons


def test_capital_rank_requires_code_rank_type_and_finite_flow() -> None:
    result = validate_dataset(
        "capital_rank",
        [
            {"code": "600000.SH", "rank_type": "inflow", "main_net": 12.0},
            {"code": "", "rank_type": "outflow", "main_net": 1.0},
            {"code": "600001.SH", "rank_type": "other", "main_net": 1.0},
            {"code": "600002.SH", "rank_type": "inflow", "main_net": float("nan")},
        ],
    )

    assert result.valid is True
    assert result.rows == [{"code": "600000.SH", "rank_type": "inflow", "main_net": 12.0}]


def test_cls_telegraph_rejects_unparseable_timestamp() -> None:
    result = validate_dataset(
        "cls_telegraph",
        [{"title": "headline", "time": "not-a-time"}],
        trade_date="2026-07-16",
    )

    assert result.valid is False
    assert "no fresh timestamped news rows" in result.reasons


def test_master_rejects_rows_without_usable_code() -> None:
    # Corruption that a bare row count misses: 3000 rows written but every row
    # is a null/placeholder. The semantic contract must drop them so the worker
    # flags the dataset as corrupt (valid_rows == 0) rather than VERIFIED.
    result = validate_dataset(
        "master",
        [{"code": "", "list_status": ""}, {"code": None, "name": "x"}],
    )
    assert result.valid is False
    assert "no master rows with a usable code" in result.reasons


def test_master_accepts_legitimate_variation() -> None:
    # Nameless codes or unusual list statuses must NOT be rejected — only rows
    # missing a code entirely are corrupt.
    result = validate_dataset(
        "master",
        [{"code": "600000.SH", "list_status": "L", "name": ""},
         {"code": "000001.SZ", "list_status": "D"}],
    )
    assert result.valid is True
    assert len(result.rows) == 2


def test_board_members_rejects_rows_without_stock_code() -> None:
    result = validate_dataset(
        "board_members",
        [{"board_code": "BK001", "stock_code": ""}, {"board_code": "", "stock_code": None}],
    )
    assert result.valid is False
    assert "no board-member rows with a stock code" in result.reasons
