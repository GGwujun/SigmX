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
