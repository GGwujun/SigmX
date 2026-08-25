import time

from src.product.research_orchestrator import ResearchOrchestrator
from src.product.research_tasks import ResearchTaskService
from src.product.store import ProductStore


class _Search:
    def search(self, question, limit=10):
        from types import SimpleNamespace

        return SimpleNamespace(items=[], source="data_hub", interpretation=[])


def _wait(orchestrator, user_id, task_id):
    for _ in range(100):
        task = orchestrator.get(user_id, task_id)
        if task.status in {"succeeded", "failed", "cancelled"}:
            return task
        time.sleep(0.01)
    raise AssertionError("task did not finish")


def test_async_research_persists_public_events(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    service = ResearchTaskService(store, _Search())
    orchestrator = ResearchOrchestrator(store, service)

    task = orchestrator.start(
        "u1", question="低估值高股息", template_id=None, scope={}, constraints=[],
        idempotency_key="run-1", plan={"execution_mode": "rules_fallback"},
    )

    assert task.status in {"queued", "running"}
    finished = _wait(orchestrator, "u1", task.id)
    assert finished.status == "succeeded"
    events = orchestrator.events("u1", task.id)
    assert [event["type"] for event in events][0] == "queued"
    assert events[-1]["type"] == "completed"
    assert all("api_key" not in str(event).lower() for event in events)


def test_retry_creates_child_task(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    service = ResearchTaskService(store, _Search())
    orchestrator = ResearchOrchestrator(store, service)
    first = orchestrator.start(
        "u1", question="银行", template_id=None, scope={}, constraints=[],
        idempotency_key="run-1", plan={"execution_mode": "rules_fallback"},
    )
    _wait(orchestrator, "u1", first.id)

    retried = orchestrator.retry("u1", first.id)

    assert retried.id != first.id
    assert orchestrator.metadata("u1", retried.id)["parent_task_id"] == first.id


def test_agent_mode_uses_research_runner_and_persists_conclusions(tmp_path):
    from src.research_agent.runner import AgentResearchOutput
    class _Runner:
        def run(self, request, emit, cancel=None):
            emit({"type": "tool_completed", "tool": "search_market_data", "evidence_count": 1})
            return AgentResearchOutput(
                summary="现金流质量改善", conclusions=[{"text": "候选值得继续研究", "evidence_ids": ["e1"]}],
                evidence=[{"id": "e1", "field": "operating_cashflow", "value": 10, "source": "data_hub", "as_of": "20260824"}],
                risks=["历史数据不代表未来"], model="test-model",
            )
    store = ProductStore(tmp_path / "product.db")
    service = ResearchTaskService(store, _Search())
    orchestrator = ResearchOrchestrator(store, service, runner_factory=lambda: _Runner())
    task = orchestrator.start(
        "u1", question="现金流", template_id=None, scope={}, constraints=[], idempotency_key="agent-1",
        plan={"execution_mode": "agent", "model": "test-model", "skills": ["cashflow-quality"]},
    )
    assert _wait(orchestrator, "u1", task.id).status == "succeeded"
    result = service.result("u1", task.id)
    assert result.conclusions[0]["evidence_ids"] == ["e1"]
    assert result.model == "test-model"
