# -*- coding: utf-8 -*-
"""统一限频登记表：默认值与历史一致、env 单项覆盖、SCALE 全局缩短。"""

from __future__ import annotations

import pytest

from src.data import rate_limit
from src.data.rate_limit import DATA_DELAYS, RATE_WAITS, rate_seconds


@pytest.mark.unit
def test_defaults_match_legacy_values() -> None:
    """默认值必须与 market_sync 历史硬编码一致（部署行为不漂移）。"""
    assert rate_seconds("tpdog_pacing") == 0.05
    assert rate_seconds("tushare_index_pacing") == 62.0
    assert rate_seconds("tushare_daily_basic_quota_retry") == 62 * 60
    assert rate_seconds("tushare_daily_basic_empty_retry") == 60.0
    assert rate_seconds("akshare_capital_pacing") == 0.6
    assert rate_seconds("eastmoney_clist_paging") == 0.15
    assert rate_seconds("eps_forecast_pacing") == 0.3
    assert rate_seconds("financial_snapshot_pacing") == 0.1
    assert rate_seconds("yfinance_retry") == 10.0
    assert rate_seconds("tpdog_etf_data_delay") == 30 * 60


@pytest.mark.unit
def test_unknown_name_raises() -> None:
    """限频名拼错当场炸，不默默睡 0 秒。"""
    with pytest.raises(KeyError):
        rate_seconds("tushare_pacing_typo")


@pytest.mark.unit
def test_env_override_single_item(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGMX_RATE_TUSHARE_DAILY_BASIC_QUOTA_RETRY", "1800")
    assert rate_seconds("tushare_daily_basic_quota_retry") == 1800.0
    # 其它项不受影响
    assert rate_seconds("tpdog_pacing") == 0.05


@pytest.mark.unit
def test_env_override_beats_scale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGMX_RATE_SCALE", "0.001")
    monkeypatch.setenv("SIGMX_RATE_YFINANCE_RETRY", "10")
    assert rate_seconds("yfinance_retry") == 10.0          # 单项覆盖优先
    assert rate_seconds("tushare_index_pacing") == pytest.approx(0.062)


@pytest.mark.unit
def test_scale_shortens_all_and_rejects_enlargement(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIGMX_RATE_SCALE", "0.5")
    assert rate_seconds("tushare_daily_basic_empty_retry") == 30.0
    monkeypatch.setenv("SIGMX_RATE_SCALE", "2.0")          # 放大拒绝
    assert rate_seconds("tushare_daily_basic_empty_retry") == 60.0
    monkeypatch.setenv("SIGMX_RATE_SCALE", "junk")         # 非法值拒绝
    assert rate_seconds("tushare_daily_basic_empty_retry") == 60.0


@pytest.mark.unit
def test_rate_waits_and_data_delays_are_disjoint() -> None:
    """限频与数据延迟两类不重名（语义不同，防误用）。"""
    assert not (RATE_WAITS.keys() & DATA_DELAYS.keys())
