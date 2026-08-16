import asyncio
from pathlib import Path

import pytest

import src.api.cloud_task_routes as routes
from src.product.cloud_tasks import CloudTaskService
from src.product.credits import CreditLedger
from src.product.store import ProductStore
from src.product.query_history import QueryHistoryService


@pytest.fixture(autouse=True)
def service(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)
    ledger.grant("u1", 100, source="test", expires_at=None, idempotency_key="grant")
    routes._service = CloudTaskService(store, ledger)
    routes._query_history = QueryHistoryService(store)
    yield
    routes._service = None
    routes._query_history = None


def test_create_list_start_and_cancel_cloud_task_routes() -> None:
    user = {"id": "u1"}
    created = asyncio.run(routes.create_cloud_task(
        routes.CreateCloudTaskRequest(task_type="deep_research", title="研究贵州茅台", cost=10, payload={"symbol": "600519.SH"}, idempotency_key="route:1"),
        user,
    ))
    assert created.status == "queued"

    items = asyncio.run(routes.list_cloud_tasks(limit=20, user=user))
    assert [item.id for item in items.items] == [created.id]
    assert asyncio.run(routes.start_cloud_task(created.id, user)).status == "running"
    assert asyncio.run(routes.cancel_cloud_task(created.id, user)).status == "cancelled"


def test_cloud_task_routes_are_authenticated() -> None:
    for route in routes.router.routes:
        assert route.dependencies or route.dependant.dependencies


def test_record_and_list_query_execution_routes() -> None:
    user = {"id": "u1"}
    created = asyncio.run(routes.record_query_execution(
        routes.RecordQueryExecutionRequest(query="低估值 高股息", intent="screener", conditions=[{"field": "pe_ttm", "value": [0, 20]}], result_count=18, idempotency_key="web:1"),
        user,
    ))

    assert created.condition_version == 1
    assert asyncio.run(routes.list_query_executions(limit=20, user=user)).items[0].id == created.id
