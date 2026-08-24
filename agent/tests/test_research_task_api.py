from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.research_task_routes as routes
from src.data.market_store import MarketStore
from src.product.public_research import PublicResearchService
from src.product.research_tasks import ResearchTaskService
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def research_service(tmp_path: Path):
    product_store = ProductStore(tmp_path / "product.db")
    market_store = MarketStore(tmp_path / "market.db")
    market_store._conn.execute(
        "INSERT INTO security_master "
        "(code,symbol,name,industry,market,exchange,list_status,is_st,is_delisting,is_bj,is_active,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("000001.SZ", "000001", "平安银行", "银行", "主板", "SZSE", "L", 0, 0, 0, 1, "2026-08-24T10:00:00+08:00"),
    )
    market_store._conn.execute(
        "INSERT INTO stock_daily_basic "
        "(code,trade_date,close,pe_ttm,pb,dv_ttm,total_mv,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("000001.SZ", "20260822", 12, 6, 0.7, 5, 230_000, "2026-08-24T10:00:00+08:00"),
    )
    market_store._conn.commit()
    routes._service = ResearchTaskService(product_store, PublicResearchService(market_store))
    yield
    routes._service = None


def _body(key: str = "research-1") -> routes.CreateResearchTaskRequest:
    return routes.CreateResearchTaskRequest(
        question="低估值 高股息",
        template_id="dividend",
        scope={"market": "A", "exclude_st": True},
        constraints=[{"field": "dividend_yield", "op": ">=", "value": 4}],
        idempotency_key=key,
    )


def test_research_task_persists_source_attributed_result() -> None:
    task = asyncio.run(routes.create_research_task(_body(), user={"id": "u1"}))

    assert task.status == "succeeded"
    assert [step.status for step in task.steps] == ["completed"] * 4
    result = asyncio.run(routes.get_research_result(task.id, user={"id": "u1"}))
    assert result.source == "local_market_store"
    assert result.as_of == "20260822"
    assert result.candidates[0].code == "000001.SZ"
    assert result.candidates[0].evidence
    assert all(item.source == "local_market_store" for item in result.candidates[0].evidence)


def test_research_task_creation_is_idempotent_and_owner_scoped() -> None:
    first = asyncio.run(routes.create_research_task(_body(), user={"id": "u1"}))
    second = asyncio.run(routes.create_research_task(_body(), user={"id": "u1"}))
    assert first.id == second.id

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.get_research_task(first.id, user={"id": "u2"}))
    assert error.value.status_code == 404


def test_unknown_constraint_is_rejected_without_fabricated_result() -> None:
    body = _body("research-invalid")
    body.constraints = [{"field": "imaginary_score", "op": ">", "value": 99}]

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.create_research_task(body, user={"id": "u1"}))
    assert error.value.status_code == 422


def test_research_router_requires_authentication() -> None:
    assert routes.router.dependencies
