from __future__ import annotations

from pathlib import Path

import pytest

from src.data.market_store import MarketStore
from src.product.public_research import InstrumentNotFound, PublicResearchService


@pytest.fixture
def research(tmp_path: Path) -> PublicResearchService:
    store = MarketStore(tmp_path / "market.db")
    conn = store._conn
    conn.executemany(
        "INSERT INTO security_master "
        "(code,symbol,name,industry,market,exchange,list_status,is_st,is_delisting,is_bj,is_active,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("600519.SH", "600519", "贵州茅台", "白酒", "主板", "SSE", "L", 0, 0, 0, 1, "2026-08-15T10:00:00+08:00"),
            ("000001.SZ", "000001", "平安银行", "银行", "主板", "SZSE", "L", 0, 0, 0, 1, "2026-08-15T10:00:00+08:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO stock_daily_basic "
        "(code,trade_date,close,pe_ttm,pb,dv_ttm,total_mv,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("600519.SH", "20260814", 1500, 24, 8, 2, 1_900_000, "2026-08-15T10:00:00+08:00"),
            ("000001.SZ", "20260814", 12, 6, 0.7, 5, 230_000, "2026-08-15T10:00:00+08:00"),
        ],
    )
    conn.execute(
        "INSERT INTO bars_daily (code,trade_date,close,source,sync_run_id,quality_status,updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        ("600519.SH", "20260814", 1500, "tushare", "r1", "verified", "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO fund_master (code,name,type,updated_at) VALUES (?,?,?,?)",
        ("510300", "沪深300ETF", "ETF", "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO etf_daily (code,trade_date,close,rise,updated_at) VALUES (?,?,?,?,?)",
        ("510300", "20260814", 4.21, 0.5, "2026-08-15T10:00:00+08:00"),
    )
    conn.commit()
    return PublicResearchService(store)


def test_search_supports_code_name_and_limited_natural_language(research: PublicResearchService) -> None:
    assert research.search("600519").items[0].name == "贵州茅台"
    assert research.search("平安").items[0].code == "000001.SZ"
    filtered = research.search("低估值 高股息 小市值")
    assert [item.code for item in filtered.items] == ["000001.SZ"]
    assert filtered.interpretation == ["市盈率 0-20", "股息率 ≥ 3%", "按总市值升序"]


def test_stock_summary_is_delayed_and_source_labelled(research: PublicResearchService) -> None:
    result = research.stock("600519")
    assert result.code == "600519.SH"
    assert result.close == 1500
    assert result.as_of == "20260814"
    assert result.is_delayed is True
    assert result.source == "local_market_store"


def test_fund_summary_uses_fund_master_and_latest_daily(research: PublicResearchService) -> None:
    result = research.fund("510300")
    assert result.name == "沪深300ETF"
    assert result.close == 4.21
    assert result.fund_type == "ETF"


def test_unknown_instrument_is_explicit(research: PublicResearchService) -> None:
    with pytest.raises(InstrumentNotFound):
        research.stock("999999")
