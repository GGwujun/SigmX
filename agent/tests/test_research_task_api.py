from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.api.research_task_routes as routes
from src.data.market_store import MarketStore
from src.product.public_research import PublicResearchService
from src.product.research_tasks import ResearchTaskService
from src.product.research_plans import ResearchPlanService
from src.product.research_orchestrator import ResearchOrchestrator
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
    routes._orchestrator = ResearchOrchestrator(product_store, routes._service)
    routes._plan_service = ResearchPlanService()
    routes._event_bus = None
    yield
    routes._service = None
    routes._orchestrator = None
    routes._plan_service = None
    routes._event_bus = None


def _body(key: str = "research-1") -> routes.CreateResearchTaskRequest:
    return routes.CreateResearchTaskRequest(
        question="低估值 高股息",
        template_id="dividend",
        scope={"market": "A", "exclude_st": True},
        constraints=[{"field": "dividend_yield", "op": ">=", "value": 4}],
        idempotency_key=key,
    )


def test_create_plan_reports_unavailable_conditions_before_task_creation() -> None:
    body = routes.CreateResearchPlanRequest(
        question="寻找经营现金流持续改善且低估值的A股公司",
        template_id=None,
        scope={"market": "A股", "exclude_st": True},
    )

    plan = asyncio.run(routes.create_research_plan(body))

    assert plan.executable is False
    statuses = {item.metric: item.status for item in plan.conditions}
    assert statuses["operating_cashflow_trend"] == "unavailable"
    assert statuses["pe_ttm"] == "supported"
    assert plan.suggested_question
    assert plan.execution_mode == "rules_fallback"


def test_create_plan_returns_normalized_constraints_for_supported_question() -> None:
    body = routes.CreateResearchPlanRequest(
        question="寻找市盈率不高于20且股息率不低于3%的A股",
        template_id=None,
        scope={"market": "A股", "exclude_st": True},
    )

    plan = asyncio.run(routes.create_research_plan(body))

    assert plan.executable is True
    assert plan.constraints == [
        {"field": "pe_ttm", "op": "<=", "value": 20.0},
        {"field": "dividend_yield", "op": ">=", "value": 3.0},
    ]


def test_research_plan_router_is_public_preflight() -> None:
    assert routes.plan_router.dependencies == []


def test_cached_plan_service_reads_latest_platform_model_for_each_call(monkeypatch) -> None:
    import src.product.ai_runtime_config as runtime_config

    seen = []
    configs = [
        SimpleNamespace(planning=SimpleNamespace(model="model-a"), temperature=.2,
                        timeout_seconds=30, max_retries=1, reasoning_effort="low"),
        SimpleNamespace(planning=SimpleNamespace(model="model-b"), temperature=.2,
                        timeout_seconds=45, max_retries=2, reasoning_effort="high"),
    ]

    class FakeConfigService:
        def __init__(self, store):
            del store

        def get_effective(self):
            return configs.pop(0)

    def fake_build(binding, **kwargs):
        seen.append((binding.model, kwargs["timeout_seconds"], kwargs["reasoning_effort"]))
        return SimpleNamespace()

    monkeypatch.setattr(runtime_config, "AIRuntimeConfigService", FakeConfigService)
    monkeypatch.setattr(runtime_config, "build_configured_chat", fake_build)
    routes._plan_service = None

    service = routes._get_plan_service()
    service.llm_factory()
    service.llm_factory()

    assert seen == [("model-a", 30, "low"), ("model-b", 45, "high")]


def test_research_task_persists_source_attributed_result() -> None:
    task = asyncio.run(routes.create_research_task(_body(), user={"id": "u1"}))

    assert task.status == "succeeded"
    assert [step.status for step in task.steps] == ["completed"] * 4
    result = asyncio.run(routes.get_research_result(task.id, user={"id": "u1"}))
    assert result.source == "local_market_store"
    assert result.as_of == "20260822"
    assert result.candidates[0].code == "000001.SZ"
    assert "市盈率 0-20" in result.candidates[0].reason
    assert "股息率 ≥ 3%" in result.candidates[0].reason
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


def test_quality_cash_flow_question_reports_unsupported_data_instead_of_empty_success() -> None:
    body = routes.CreateResearchTaskRequest(
        question="寻找经营现金流持续改善、盈利质量高于行业中位数的 A 股公司",
        template_id="quality",
        scope={"market": "A股", "exclude_st": True},
        constraints=[],
        idempotency_key="research-quality",
    )

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.create_research_task(body, user={"id": "u1"}))

    assert error.value.status_code == 422
    assert "经营现金流" in str(error.value.detail)
    assert "无法可靠执行" in str(error.value.detail)


def test_other_unsupported_financial_factor_reports_capability_gap() -> None:
    body = routes.CreateResearchTaskRequest(
        question="寻找 ROE 连续三年提升且毛利率稳定的公司",
        template_id=None,
        scope={"market": "A股", "exclude_st": True},
        constraints=[],
        idempotency_key="research-unsupported-factor",
    )

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.create_research_task(body, user={"id": "u1"}))

    assert error.value.status_code == 422
    assert "当前只支持" in str(error.value.detail)


def test_research_router_requires_authentication() -> None:
    assert routes.router.dependencies


def test_lists_only_current_users_research_tasks() -> None:
    first = asyncio.run(routes.create_research_task(_body("first-task"), user={"id": "u1"}))
    asyncio.run(routes.create_research_task(_body("second-task"), user={"id": "u2"}))

    tasks = asyncio.run(routes.list_research_tasks(limit=10, user={"id": "u1"}))

    assert [task.id for task in tasks] == [first.id]


def test_confirmed_plan_uses_async_task_and_exposes_events_and_retry() -> None:
    body = _body("async-task")
    body.plan = {"execution_mode": "rules_fallback", "conditions": []}
    task = asyncio.run(routes.create_research_task(body, user={"id": "u1"}))
    assert task.status in {"queued", "running", "succeeded"}

    events = asyncio.run(routes.list_research_events(task.id, after=0, user={"id": "u1"}))
    assert events
    retried = asyncio.run(routes.retry_research_task(task.id, user={"id": "u1"}))
    assert retried.id != task.id


def test_research_thread_restores_parent_and_follow_up_oldest_first() -> None:
    parent = routes._orchestrator.start(
        "u1", question="低估值 高股息", template_id="dividend", scope={}, constraints=[],
        idempotency_key="thread-parent", plan={"execution_mode": "rules_fallback"},
    )
    for _ in range(100):
        parent = routes._orchestrator.get("u1", parent.id)
        if parent.status == "succeeded":
            break
        time.sleep(.01)
    child = routes._orchestrator.start(
        "u1", question="再看看银行业", template_id="dividend", scope={}, constraints=[],
        idempotency_key="thread-child", plan={"execution_mode": "rules_fallback"}, parent_task_id=parent.id,
    )
    for _ in range(100):
        child = routes._orchestrator.get("u1", child.id)
        if child.status == "succeeded":
            break
        time.sleep(.01)

    thread = asyncio.run(routes.get_research_thread(child.id, user={"id": "u1"}))

    assert [turn["task"]["id"] for turn in thread["turns"]] == [parent.id, child.id]
    assert all(turn["result"] is not None for turn in thread["turns"])
    assert all(isinstance(turn["events"], list) for turn in thread["turns"])


class _DummyRequest:
    async def is_disconnected(self) -> bool:
        return False


async def _collect_frames(response) -> list[str]:
    return [frame async for frame in response.body_iterator]


def test_stream_replays_persisted_events_for_finished_task() -> None:
    body = _body("stream-done")
    body.plan = {"execution_mode": "rules_fallback", "conditions": []}
    task = asyncio.run(routes.create_research_task(body, user={"id": "u1"}))
    for _ in range(200):
        task = routes._orchestrator.get("u1", task.id)
        if task.status == "succeeded":
            break
        time.sleep(.01)
    assert task.status == "succeeded"

    async def run() -> list[str]:
        response = await routes.stream_research_events(task.id, _DummyRequest(), after=0, user={"id": "u1"})
        return await _collect_frames(response)

    frames = asyncio.run(run())

    assert frames, "expected replayed SSE frames"
    assert all(frame.startswith("id: ") for frame in frames)
    assert any("event: completed" in frame for frame in frames)


def test_stream_pushes_live_events_until_terminal_event() -> None:
    routes._orchestrator = ResearchOrchestrator(
        routes._service.store, routes._service, publisher=routes._publish_task_event,
    )
    task = routes._service.create(
        "u1", question="低估值 高股息", template_id="dividend", scope={}, constraints=[],
        idempotency_key="stream-live", agent_mode=False,
    )
    assert task.status == "queued"

    async def run() -> list[str]:
        response = await routes.stream_research_events(task.id, _DummyRequest(), after=0, user={"id": "u1"})
        stream = asyncio.ensure_future(_collect_frames(response))
        await asyncio.sleep(0.05)  # let the generator finish replay and subscribe
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, routes._orchestrator._event, task.id, "running", {"message": "go"})
        await loop.run_in_executor(None, routes._orchestrator._event, task.id, "thinking_delta", {"delta": "分析中", "iter": 1})
        await loop.run_in_executor(None, routes._orchestrator._event, task.id, "completed", {"message": "done"})
        return await asyncio.wait_for(stream, timeout=5)

    frames = asyncio.run(run())

    assert any("event: running" in frame for frame in frames)
    assert any("event: thinking_delta" in frame and "分析中" in frame for frame in frames)
    assert frames[-1].startswith("id: ") and "event: completed" in frames[-1]


def test_stream_rejects_other_users_task() -> None:
    task = asyncio.run(routes.create_research_task(_body("stream-owner"), user={"id": "u1"}))

    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.stream_research_events(task.id, _DummyRequest(), after=0, user={"id": "u2"}))
    assert error.value.status_code == 404
