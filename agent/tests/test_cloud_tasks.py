from pathlib import Path

import pytest

from src.product.cloud_tasks import CloudTaskService, InvalidTaskTransition
from src.product.credits import CreditLedger
from src.product.store import ProductStore


@pytest.fixture
def task_service(tmp_path: Path) -> tuple[CloudTaskService, CreditLedger]:
    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store, now=lambda: "2026-08-16T01:00:00+00:00")
    ledger.grant("u1", 100, source="test", expires_at=None, idempotency_key="grant:u1")
    return CloudTaskService(store, ledger, now=lambda: "2026-08-16T01:00:00+00:00"), ledger


def test_creating_cloud_task_reserves_research_credits(task_service) -> None:
    service, ledger = task_service

    task = service.create("u1", task_type="deep_research", title="研究贵州茅台", cost=10, payload={"symbol": "600519.SH"}, idempotency_key="task:1")

    assert task.status == "queued"
    assert task.reserved_credits == 10
    assert task.reservation_id
    assert ledger.balance("u1").available == 90


def test_successful_cloud_task_settles_reserved_credits(task_service) -> None:
    service, ledger = task_service
    task = service.create("u1", task_type="deep_research", title="研究贵州茅台", cost=10, payload={}, idempotency_key="task:2")

    running = service.start("u1", task.id)
    completed = service.succeed("u1", task.id, result_ref="report://r1")

    assert running.status == "running"
    assert completed.status == "succeeded"
    assert completed.result_ref == "report://r1"
    assert ledger.balance("u1").available == 90


@pytest.mark.parametrize("terminal", ["fail", "cancel"])
def test_failed_or_cancelled_cloud_task_refunds_reserved_credits(task_service, terminal: str) -> None:
    service, ledger = task_service
    task = service.create("u1", task_type="deep_research", title="研究贵州茅台", cost=10, payload={}, idempotency_key=f"task:{terminal}")
    service.start("u1", task.id)

    completed = service.fail("u1", task.id, error="provider unavailable") if terminal == "fail" else service.cancel("u1", task.id)

    assert completed.status == ("failed" if terminal == "fail" else "cancelled")
    assert ledger.balance("u1").available == 100


def test_terminal_cloud_task_cannot_be_restarted(task_service) -> None:
    service, _ = task_service
    task = service.create("u1", task_type="deep_research", title="研究贵州茅台", cost=10, payload={}, idempotency_key="task:terminal")
    service.cancel("u1", task.id)

    with pytest.raises(InvalidTaskTransition):
        service.start("u1", task.id)


def test_cloud_task_reads_are_owner_scoped(task_service) -> None:
    service, _ = task_service
    service.create("u1", task_type="deep_research", title="研究贵州茅台", cost=10, payload={}, idempotency_key="task:owner")

    assert len(service.list("u1")) == 1
    assert service.list("u2") == []
