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
    store._conn.commit()
    routes._service = PublicResearchService(store)
    yield
    routes._service = None


def test_public_search_and_stock_routes_need_no_user_argument() -> None:
    result = asyncio.run(routes.public_search(q="贵州", limit=10))
    assert result.items[0].code == "600519.SH"
    stock = asyncio.run(routes.public_stock("600519"))
    assert stock.name == "贵州茅台"


def test_unknown_public_instrument_returns_404() -> None:
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.public_fund("999999"))
    assert error.value.status_code == 404


def test_public_router_has_no_auth_dependencies() -> None:
    paths = {route.path: route for route in routes.router.routes}
    for path in ("/api/public/search", "/api/public/stocks/{code}", "/api/public/funds/{code}"):
        assert path in paths
        assert paths[path].dependencies == []
