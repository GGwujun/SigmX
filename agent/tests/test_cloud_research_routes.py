from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.cloud_research import CloudResearchService
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def cloud_routes(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._cloud_research = CloudResearchService(store)
    yield
    pr._store = None
    pr._cloud_research = None


def test_query_and_watchlist_routes_are_owner_isolated() -> None:
    asyncio.run(pr.save_cloud_query(pr.SaveCloudQueryRequest(query="高股息", result_summary={"matches": 2}), user={"id": "u1"}))
    asyncio.run(pr.save_cloud_query(pr.SaveCloudQueryRequest(query="低波动", result_summary={"matches": 1}), user={"id": "u2"}))
    queries = asyncio.run(pr.list_cloud_queries(user={"id": "u1"}))
    assert [item.query for item in queries.items] == ["高股息"]

    asyncio.run(pr.add_cloud_watchlist(pr.AddCloudWatchlistRequest(symbol="600519.SH", name="贵州茅台"), user={"id": "u1"}))
    assert asyncio.run(pr.list_cloud_watchlist(user={"id": "u2"})).items == []
    assert asyncio.run(pr.list_cloud_watchlist(user={"id": "u1"})).items[0].symbol == "600519.SH"


def test_report_publish_public_read_and_revoked_410() -> None:
    created = asyncio.run(pr.publish_cloud_report(pr.PublishCloudReportRequest(title="公开摘要", summary="脱敏内容"), user={"id": "u1"}))
    public = asyncio.run(pr.public_cloud_report(created.slug))
    assert public.summary == "脱敏内容"
    asyncio.run(pr.revoke_cloud_report(created.id, user={"id": "u1"}))
    with pytest.raises(pr.HTTPException) as error:
        asyncio.run(pr.public_cloud_report(created.slug))
    assert error.value.status_code == 410


def test_report_revoke_is_owner_scoped() -> None:
    created = asyncio.run(pr.publish_cloud_report(pr.PublishCloudReportRequest(title="报告", summary="摘要"), user={"id": "u1"}))
    with pytest.raises(pr.HTTPException) as error:
        asyncio.run(pr.revoke_cloud_report(created.id, user={"id": "u2"}))
    assert error.value.status_code == 404
