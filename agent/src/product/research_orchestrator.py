"""Asynchronous lifecycle and public event log for Web research tasks."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from src.product.research_tasks import ResearchTask, ResearchTaskService
from src.product.store import ProductStore
from src.research_agent.runner import ResearchRunRequest


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchOrchestrator:
    def __init__(self, store: ProductStore, service: ResearchTaskService, *, workers: int = 2, runner_factory=None) -> None:
        self.store = store
        self.service = service
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sigmx-research")
        self.runner_factory = runner_factory

    def start(self, user_id: str, *, question: str, template_id: str | None,
              scope: dict[str, Any], constraints: list[dict[str, Any]], idempotency_key: str,
              plan: dict[str, Any], parent_task_id: str | None = None) -> ResearchTask:
        task = self.service.create(user_id, question=question, template_id=template_id, scope=scope,
                                   constraints=constraints, idempotency_key=idempotency_key)
        if task.status != "queued":
            return task
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO research_task_runtime(task_id,plan_json,parent_task_id,created_at) VALUES (?,?,?,?)",
                (task.id, json.dumps(plan, ensure_ascii=False), parent_task_id, _now()),
            )
        self._event(task.id, "queued", {"message": "研究任务已进入执行队列"})
        self.pool.submit(self._execute, user_id, task.id)
        return self.service.get(user_id, task.id)

    def _execute(self, user_id: str, task_id: str) -> None:
        self._event(task_id, "running", {"message": "正在检索和核验证据"})
        try:
            meta = self.metadata(user_id, task_id)
            plan = meta["plan"]
            if plan.get("execution_mode") == "agent" and self.runner_factory is not None:
                runner = self.runner_factory()
                task = self.service.get(user_id, task_id)
                output = runner.run(
                    ResearchRunRequest(question=task.question, plan=plan),
                    lambda event: self._event(task_id, str(event.get("type", "progress")), event),
                    lambda: self.service.get(user_id, task_id).status == "cancelled",
                )
                self.service.save_agent_result(user_id, task_id, output, skills=list(plan.get("skills") or []))
            else:
                self.service.run(user_id, task_id)
            self._event(task_id, "completed", {"message": "研究结果已生成"})
        except Exception as exc:
            self._event(task_id, "failed", {"message": str(exc)[:300]})

    def get(self, user_id: str, task_id: str) -> ResearchTask:
        return self.service.get(user_id, task_id)

    def cancel(self, user_id: str, task_id: str) -> ResearchTask:
        task = self.service.cancel(user_id, task_id)
        self._event(task_id, "cancelled", {"message": "研究任务已取消"})
        return task

    def retry(self, user_id: str, task_id: str) -> ResearchTask:
        task = self.service.get(user_id, task_id)
        meta = self.metadata(user_id, task_id)
        return self.start(
            user_id, question=task.question, template_id=task.template_id, scope=task.scope,
            constraints=task.constraints, idempotency_key=f"retry-{task_id}-{uuid.uuid4().hex}",
            plan=meta["plan"], parent_task_id=task_id,
        )

    def metadata(self, user_id: str, task_id: str) -> dict[str, Any]:
        self.service.get(user_id, task_id)
        with self.store._lock:
            row = self.store._get_conn().execute(
                "SELECT * FROM research_task_runtime WHERE task_id=?", (task_id,)
            ).fetchone()
        return {"plan": json.loads(row["plan_json"]) if row else {},
                "parent_task_id": row["parent_task_id"] if row else None}

    def events(self, user_id: str, task_id: str, after: int = 0) -> list[dict[str, Any]]:
        self.service.get(user_id, task_id)
        with self.store._lock:
            rows = self.store._get_conn().execute(
                "SELECT id,event_type,payload_json,created_at FROM research_task_events WHERE task_id=? AND id>? ORDER BY id",
                (task_id, after),
            ).fetchall()
        return [{"id": row["id"], "type": row["event_type"],
                 "payload": json.loads(row["payload_json"]), "created_at": row["created_at"]} for row in rows]

    def _event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        safe = {key: value for key, value in payload.items() if key.lower() not in {"api_key", "secret", "token"}}
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO research_task_events(task_id,event_type,payload_json,created_at) VALUES (?,?,?,?)",
                (task_id, event_type, json.dumps(safe, ensure_ascii=False), _now()),
            )
