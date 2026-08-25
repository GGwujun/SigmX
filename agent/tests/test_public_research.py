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
            ("000002.SZ", "000002", "ST 测试", "测试", "主板", "SZSE", "L", 1, 0, 0, 1, "2026-08-15T10:00:00+08:00"),
        ],
    )
    conn.executemany(
        "INSERT INTO stock_daily_basic "
        "(code,trade_date,close,pe_ttm,pb,dv_ttm,total_mv,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("600519.SH", "20260814", 1500, 24, 8, 2, 1_900_000, "2026-08-15T10:00:00+08:00"),
            ("000001.SZ", "20260814", 12, 6, 0.7, 5, 230_000, "2026-08-15T10:00:00+08:00"),
            ("000002.SZ", "20260814", 3, 8, 0.5, 6, 20_000, "2026-08-15T10:00:00+08:00"),
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
    conn.execute(
        "INSERT INTO financial_snapshot (code,trade_date,eps,bvps,roe,profit,income,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("600519.SH", "20260814", 62.1, 210.5, 31.2, 86_000_000_000, 174_000_000_000, "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO stock_capital_flow (code,trade_date,period,m_net,r_net,updated_at) VALUES (?,?,?,?,?,?)",
        ("600519.SH", "20260814", 1, 120_000_000, -20_000_000, "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO announcement (code,ann_date,title,ann_type,url,updated_at) VALUES (?,?,?,?,?,?)",
        ("600519.SH", "20260813", "2026 年半年度报告", "定期报告", "https://example.test/a", "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO fund_premium_snapshot (code,trade_date,name,type,price,nav,premium_rate,amount,change_pct,signal,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("510300", "20260814", "沪深300ETF", "ETF", 4.21, 4.20, 0.24, 1_500_000_000, 0.5, "NEUTRAL", "2026-08-15T10:00:00+08:00"),
    )
    conn.execute(
        "INSERT INTO etf_share_size (code,trade_date,name,total_share,total_size,nav,close,exchange,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("510300", "20260814", "沪深300ETF", 50_000_000_000, 210_000_000_000, 4.20, 4.21, "SSE", "2026-08-15T10:00:00+08:00"),
    )
    conn.commit()
    return PublicResearchService(store)


def test_search_supports_code_name_and_limited_natural_language(research: PublicResearchService) -> None:
    assert research.search("600519").items[0].name == "贵州茅台"
    assert research.search("平安").items[0].code == "000001.SZ"
    filtered = research.search("低估值 高股息 小市值")
    assert [item.code for item in filtered.items] == ["000001.SZ"]
    assert filtered.interpretation == ["市盈率 0-20", "股息率 ≥ 3%", "按总市值升序"]


def test_factor_question_ignores_natural_language_filler_instead_of_false_empty(research: PublicResearchService) -> None:
    result = research.search("寻找低估值且高股息的 A 股公司")

    assert [item.code for item in result.items] == ["000001.SZ"]
    assert result.interpretation == ["市盈率 0-20", "股息率 ≥ 3%"]


def test_discovery_only_advertises_templates_the_research_executor_can_run(research: PublicResearchService) -> None:
    templates = research.discovery().templates

    assert {item.id for item in templates} == {"dividend", "value", "small_dividend"}
    for template in templates:
        result = research.search(template.prompt)
        assert result.interpretation
        assert result.items


def test_stock_summary_is_delayed_and_source_labelled(research: PublicResearchService) -> None:
    result = research.stock("600519")
    assert result.code == "600519.SH"
    assert result.close == 1500
    assert result.as_of == "20260814"
    assert result.is_delayed is True
    assert result.source == "local_market_store"


def test_stock_profile_contains_finance_flow_events_risk_summary_and_quality(research: PublicResearchService) -> None:
    result = research.stock("600519")

    assert result.quote["close"] == 1500
    assert result.finance["roe"] == 31.2
    assert result.capital_flows[0]["main_net"] == 120_000_000
    assert result.events[0]["title"] == "2026 年半年度报告"
    assert result.quality["status"] == "verified"
    assert result.quality["source"] == "tushare"
    assert "贵州茅台" in result.research_summary
    assert result.risks


def test_fund_summary_uses_fund_master_and_latest_daily(research: PublicResearchService) -> None:
    result = research.fund("510300")
    assert result.name == "沪深300ETF"
    assert result.close == 4.21
    assert result.fund_type == "ETF"


def test_fund_profile_contains_premium_scale_liquidity_and_risk(research: PublicResearchService) -> None:
    result = research.fund("510300")

    assert result.premium["premium_rate"] == 0.24
    assert result.scale["total_size"] == 210_000_000_000
    assert result.liquidity["amount"] == 1_500_000_000
    assert result.quality["status"] in {"verified", "unverified"}
    assert result.research_summary.startswith("沪深300ETF")


def test_unknown_instrument_is_explicit(research: PublicResearchService) -> None:
    with pytest.raises(InstrumentNotFound):
        research.stock("999999")


def test_market_question_returns_an_explainable_market_answer(research: PublicResearchService) -> None:
    result = research.search("今天市场怎么样")

    assert result.intent == "market_question"
    assert result.items == []
    assert result.answer is not None
    assert "20260814" in result.answer
    assert result.interpretation == ["识别为市场概览问题"]


def test_api_docs_query_returns_relevant_document_links(research: PublicResearchService) -> None:
    result = research.search("Data Hub 股票日线接口怎么调用")

    assert result.intent == "api_docs"
    assert result.items == []
    assert result.resources[0].title == "股票日线接口"
    assert result.resources[0].url == "/docs/data-hub/stocks-daily"


def test_fund_search_reads_fund_master_instead_of_stock_master(research: PublicResearchService) -> None:
    result = research.search("沪深300 ETF")

    assert result.intent == "fund_search"
    assert result.items[0].code == "510300"
    assert result.items[0].instrument_type == "fund"
