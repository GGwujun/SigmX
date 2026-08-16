from pathlib import Path

from src.product.query_history import QueryHistoryService
from src.product.store import ProductStore


def test_query_history_records_versions_and_is_owner_scoped(tmp_path: Path) -> None:
    service = QueryHistoryService(ProductStore(tmp_path / "product.db"), now=lambda: "2026-08-16T02:00:00+00:00")

    first = service.record("u1", query="低估值 高股息", intent="screener", conditions=[{"field": "pe_ttm", "value": [0, 20]}], result_count=18)
    second = service.record("u1", query="低估值 高股息", intent="screener", conditions=[{"field": "pe_ttm", "value": [0, 15]}], result_count=9)

    assert first.condition_version == 1
    assert second.condition_version == 2
    assert [item.result_count for item in service.list("u1")] == [9, 18]
    assert service.list("u2") == []


def test_query_history_replays_same_execution_idempotently(tmp_path: Path) -> None:
    service = QueryHistoryService(ProductStore(tmp_path / "product.db"))

    first = service.record("u1", query="600519", intent="instrument", conditions=[], result_count=1, idempotency_key="exec:1")
    replay = service.record("u1", query="600519", intent="instrument", conditions=[], result_count=1, idempotency_key="exec:1")

    assert replay.id == first.id
    assert len(service.list("u1")) == 1
