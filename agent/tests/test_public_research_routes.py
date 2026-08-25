from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.public_research_routes as routes
from src.data.market_store import MarketStore
from src.product.public_research import PublicResearchService


@pytest.fixture(autouse=True)
def public_service(tmp_path: Path):
    store = MarketStore(tmp_path / "market.db")
    store._conn.execute(
        "INSERT INTO security_master "
        "(code,symbol,name,industry,market,exchange,list_status,is_st,is_delisting,is_bj,is_active,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("600519.SH", "600519", "贵州茅台", "白酒", "主板", "SSE", "L", 0, 0, 0, 1, "2026-08-15T10:00:00+08:00"),
    )
    store._conn.executemany(
        "INSERT INTO index_daily (code,trade_date,close,pre_close,pct_chg,updated_at) VALUES (?,?,?,?,?,?)",
        [
            ("000001.SH", "20260814", 3381.21, 3367.07, 0.42, "2026-08-15T10:00:00+08:00"),
            ("399001.SZ", "20260814", 10642.08, 10566.98, 0.71, "2026-08-15T10:00:00+08:00"),
            ("399006.SZ", "20260814", 2178.36, 2166.23, 0.56, "2026-08-15T10:00:00+08:00"),
        ],
    )
    store._conn.executemany(
        "INSERT INTO bars_daily (code,trade_date,open,close,total_amt,source,quality_status,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        [
            ("TEST.UP", "20260814", 10, 11, 50_000_000, "tushare", "verified", "2026-08-15T10:00:00+08:00"),
            ("TEST.DOWN", "20260814", 11, 10, 30_000_000, "tushare", "verified", "2026-08-15T10:00:00+08:00"),
        ],
    )
    store._conn.commit()
    routes._service = PublicResearchService(store)
    yield
    routes._service = None


def test_public_search_and_stock_routes_need_no_user_argument() -> None:
    result = asyncio.run(routes.public_search(q="贵州", limit=10))
    assert result.items[0].code == "600519.SH"
    stock = asyncio.run(routes.public_stock("600519"))
    assert stock.name == "贵州茅台"
    assert stock.quality["status"] == "unverified"
    assert "贵州茅台" in stock.research_summary
    assert stock.risks


def test_unknown_public_instrument_returns_404() -> None:
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.public_fund("999999"))
    assert error.value.status_code == 404


def test_public_router_has_no_auth_dependencies() -> None:
    paths = {route.path: route for route in routes.router.routes}
    for path in ("/api/public/search", "/api/public/stocks/{code}", "/api/public/funds/{code}"):
        assert path in paths
        assert paths[path].dependencies == []


def test_public_search_route_preserves_intent_answer_and_resources() -> None:
    docs = asyncio.run(routes.public_search(q="Data Hub 股票日线接口", limit=10))

    assert docs.intent == "api_docs"
    assert docs.answer
    assert docs.resources[0].url == "/docs/data-hub/stocks-daily"


def test_discovery_uses_latest_stored_market_data_with_provenance() -> None:
    result = asyncio.run(routes.public_discovery())

    assert result.as_of == "20260814"
    assert result.source == "local_market_store"
    assert result.is_delayed is True
    assert result.market_status in {"open", "closed", "unknown"}
    metrics = {item.key: item for item in result.metrics}
    assert metrics["shanghai_index"].value == 3381.21
    assert metrics["market_breadth"].value == 1
    assert metrics["market_breadth"].secondary_value == 1
    assert metrics["turnover"].value == 0.8
    assert metrics["turnover"].unit == "亿元"
    assert all(item.quality in {"fresh", "delayed", "unavailable"} for item in result.metrics)
    assert result.templates


def test_discovery_does_not_invent_values_when_store_is_empty(tmp_path: Path) -> None:
    routes._service = PublicResearchService(MarketStore(tmp_path / "empty.db"))

    result = asyncio.run(routes.public_discovery())

    assert result.as_of is None
    assert all(item.value is None for item in result.metrics)
    assert all(item.quality == "unavailable" for item in result.metrics)


def test_public_intelligence_returns_cached_aggregated_articles(monkeypatch, tmp_path: Path) -> None:
    from src.api import news_routes
    from src.data.market_store import MarketStore

    calls = 0
    def fetch(keyword: str) -> dict:
        nonlocal calls
        calls += 1
        return {
            "articles": [{"title": "交易所发布真实公告", "url": "https://example.com/a", "source": "交易所", "published": "2026-08-24", "snippet": "公告摘要"}],
            "query": keyword, "sources": ["交易所"], "updated_at": "2026-08-24T10:00:00Z",
        }
    monkeypatch.setattr(news_routes, "_NEWS_STORE", MarketStore(tmp_path / "news.db"))
    monkeypatch.setattr(news_routes, "_build_news_list", fetch)
    response = asyncio.run(routes.public_intelligence(q="公告", limit=10))
    cached = asyncio.run(routes.public_intelligence(q="公告", limit=10))
    assert response.articles[0].title == "交易所发布真实公告"
    assert response.articles[0].url == "https://example.com/a"
    assert response.sources == ["交易所"]
    assert response.cache_status == "live"
    assert cached.cache_status == "fresh_cache"
    assert calls == 1
