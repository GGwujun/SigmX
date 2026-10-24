"""公开分享研究对话：路由行为 + 公开投影脱敏 + 幂等/撤销语义。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

import src.api.research_task_routes as routes
from src.data.market_store import MarketStore
from src.product.public_research import PublicResearchService
from src.product.research_tasks import ResearchTaskService
from src.product.research_orchestrator import ResearchOrchestrator
from src.product.shared_conversations import SharedConversationService
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def shared_conversation_routes(tmp_path: Path):
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
    routes._plan_service = None
    routes._event_bus = None
    routes._shared_conversations = None
    yield product_store
    routes._service = None
    routes._orchestrator = None
    routes._plan_service = None
    routes._event_bus = None
    routes._shared_conversations = None


def _run_task(question: str, key: str, user_id: str = "u1", parent_task_id: str | None = None):
    task = routes._orchestrator.start(
        user_id, question=question, template_id="dividend", scope={}, constraints=[],
        idempotency_key=key, plan={"execution_mode": "rules_fallback"}, parent_task_id=parent_task_id,
    )
    for _ in range(200):
        task = routes._orchestrator.get(user_id, task.id)
        if task.status in ("succeeded", "failed"):
            break
        time.sleep(.01)
    return task


def test_share_creates_slug_and_is_idempotent() -> None:
    task = _run_task("低估值 高股息", "share-1")
    first = asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
    assert first.slug and first.revoked_at is None
    second = asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
    assert (second.slug, second.id) == (first.slug, first.id)
    # 查询端点回报同一 active 分享
    known = asyncio.run(routes.get_research_share(task.id, user={"id": "u1"}))
    assert known.slug == first.slug


def test_share_by_non_owner_404() -> None:
    task = _run_task("低估值 高股息", "share-owner")
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.share_research_conversation(task.id, user={"id": "u2"}))
    assert error.value.status_code == 404


def test_revoke_then_public_410_and_reshare_new_slug() -> None:
    task = _run_task("低估值 高股息", "share-revoke")
    created = asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
    asyncio.run(routes.revoke_research_share(task.id, user={"id": "u1"}))
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.public_shared_conversation(created.slug))
    assert error.value.status_code == 410
    # 重分享生成新 slug，旧 slug 仍 410
    recreated = asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
    assert recreated.slug != created.slug
    public = asyncio.run(routes.public_shared_conversation(recreated.slug))
    assert public["slug"] == recreated.slug
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.public_shared_conversation(created.slug))
    assert error.value.status_code == 410


def test_revoke_by_non_owner_and_twice_404() -> None:
    task = _run_task("低估值 高股息", "share-revoke-2")
    asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.revoke_research_share(task.id, user={"id": "u2"}))
    assert error.value.status_code == 404
    asyncio.run(routes.revoke_research_share(task.id, user={"id": "u1"}))
    with pytest.raises(routes.HTTPException) as error:  # 二次撤销
        asyncio.run(routes.revoke_research_share(task.id, user={"id": "u1"}))
    assert error.value.status_code == 404


def test_public_read_contains_full_turn_chain_anonymously() -> None:
    parent = _run_task("低估值 高股息", "chain-parent")
    child = _run_task("再看看银行业", "chain-child", parent_task_id=parent.id)
    created = asyncio.run(routes.share_research_conversation(child.id, user={"id": "u1"}))

    public = asyncio.run(routes.public_shared_conversation(created.slug))  # 匿名：无 user 依赖

    assert public["question"] == "再看看银行业"
    assert [turn["task"]["id"] for turn in public["turns"]] == [parent.id, child.id]
    assert all(turn["result"] is not None for turn in public["turns"])
    assert all(isinstance(turn["events"], list) for turn in public["turns"])


def test_public_turn_hides_user_id_and_sanitizes_error() -> None:
    store = routes._service.store
    real = _run_task("低估值 高股息", "sanitize-real")  # FK 指向真实任务行
    # 直接用注入 thread_loader 的服务测公开投影（不经规则引擎造 failed 任务）
    turns = [{
        "task": {"id": real.id, "user_id": "u-internal-uuid", "question": "问题", "status": "failed",
                 "error": "openai.APIConnectionError: https://internal-host/v1 timeout"},
        "events": [
            {"id": 1, "type": "request_failed", "created_at": "2026-10-24T00:00:00+00:00",
             "payload": {"error": "httpx.ConnectError: https://internal-host", "stage": "m2"}},
            {"id": 2, "type": "failed", "created_at": "2026-10-24T00:00:01+00:00",
             "payload": {"message": "ValueError: boom at /opt/sigmx/agent/src/secret.py"}},
        ],
        "result": None,
    }]
    service = SharedConversationService(store, lambda user_id, task_id: turns,
                                        now=lambda: "2026-10-24T00:00:00+00:00")
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO shared_conversations (id,user_id,task_id,slug,created_at,revoked_at) "
            "VALUES ('s1','u1',?,'slug-1','2026-10-24T00:00:00+00:00',NULL)",
            (real.id,),
        )
    public = service.public_conversation("slug-1")
    turn = public["turns"][0]
    assert "user_id" not in turn["task"]
    assert "internal-host" not in turn["task"]["error"]
    assert turn["task"]["error"] == "研究任务执行失败"
    assert turn["events"][0]["payload"]["error"] == "内部错误"
    assert "secret.py" not in turn["events"][1]["payload"]["message"]


def test_unknown_slug_404() -> None:
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.public_shared_conversation("no-such-slug"))
    assert error.value.status_code == 404


def test_followup_after_share_not_exposed() -> None:
    parent = _run_task("低估值 高股息", "expose-parent")
    created = asyncio.run(routes.share_research_conversation(parent.id, user={"id": "u1"}))
    # 分享之后的新追问是子孙节点：thread 只向上回溯祖先链，不自动公开
    follow_up = _run_task("追问的新问题", "expose-child", parent_task_id=parent.id)
    public = asyncio.run(routes.public_shared_conversation(created.slug))
    assert [turn["task"]["id"] for turn in public["turns"]] == [parent.id]
    assert follow_up.id not in {turn["task"]["id"] for turn in public["turns"]}


def test_share_rejected_by_compliance_gate() -> None:
    task = _run_task("低估值 高股息", "gate-base")
    # 换成带红线表述的 thread_loader：问题文本含「建议买入」类投资动作建议
    original = routes._shared_conversations or routes._get_shared_conversations()
    turns = [{
        "task": {"id": task.id, "user_id": "u1", "question": "帮我看看", "status": "succeeded",
                 "error": None},
        "events": [],
        "result": {"summary": "该股票基本面尚可，建议买入并长期持有。", "conclusions": [], "risks": []},
    }]
    routes._shared_conversations = SharedConversationService(original.store, lambda u, t: turns)
    try:
        with pytest.raises(routes.HTTPException) as error:
            asyncio.run(routes.share_research_conversation(task.id, user={"id": "u1"}))
        assert error.value.status_code == 400
        assert "合规" in error.value.detail
    finally:
        routes._shared_conversations = original
