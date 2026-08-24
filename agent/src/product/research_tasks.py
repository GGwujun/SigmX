"""Persisted, evidence-backed Web research tasks."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.product.public_research import PublicResearchService, PublicSearchItem
from src.product.store import ProductStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvalidResearchConstraint(ValueError):
    pass


@dataclass(frozen=True)
class ResearchStep:
    key: str
    label: str
    status: str


@dataclass(frozen=True)
class ResearchTask:
    id: str
    user_id: str
    question: str
    template_id: str | None
    scope: dict[str, Any]
    constraints: list[dict[str, Any]]
    status: str
    steps: list[ResearchStep]
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True)
class ResearchEvidence:
    field: str
    value: Any
    source: str
    as_of: str | None


@dataclass(frozen=True)
class ResearchCandidate:
    code: str
    name: str
    industry: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    reason: str
    evidence: list[ResearchEvidence]


@dataclass(frozen=True)
class ResearchResult:
    task_id: str
    question: str
    template_id: str | None
    summary: str
    source: str
    as_of: str | None
    scope: dict[str, Any]
    candidates: list[ResearchCandidate]
    risks: list[str]
    created_at: str


class ResearchTaskService:
    _FIELDS = {
        "close",
        "pe_ttm",
        "pb",
        "dividend_yield",
        "total_market_value",
    }
    _OPS = {">", ">=", "<", "<=", "=", "=="}

    def __init__(
        self,
        store: ProductStore,
        research: PublicResearchService,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        self.store = store
        self.research = research
        self._now = now

    def create_and_run(
        self,
        user_id: str,
        *,
        question: str,
        template_id: str | None,
        scope: dict[str, Any],
        constraints: list[dict[str, Any]],
        idempotency_key: str,
    ) -> ResearchTask:
        self._validate_constraints(constraints)
        existing = self._by_key(user_id, idempotency_key)
        if existing:
            return existing
        task_id = uuid.uuid4().hex
        created_at = self._now()
        steps = self._steps("queued")
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO research_tasks "
                "(id,user_id,question,template_id,scope_json,constraints_json,status,steps_json,idempotency_key,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    task_id,
                    user_id,
                    question,
                    template_id,
                    json.dumps(scope, ensure_ascii=False),
                    json.dumps(constraints, ensure_ascii=False),
                    "queued",
                    json.dumps([asdict(step) for step in steps], ensure_ascii=False),
                    idempotency_key,
                    created_at,
                ),
            )
        return self._run(user_id, task_id)

    def get(self, user_id: str, task_id: str) -> ResearchTask:
        row = self.store._get_conn().execute(
            "SELECT * FROM research_tasks WHERE id=? AND user_id=?", (task_id, user_id)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task(row)

    def result(self, user_id: str, task_id: str) -> ResearchResult:
        task = self.get(user_id, task_id)
        if task.status != "succeeded":
            raise RuntimeError(f"research task is {task.status}")
        row = self.store._get_conn().execute(
            "SELECT * FROM research_results WHERE task_id=? AND user_id=?", (task_id, user_id)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        candidates = [
            ResearchCandidate(
                **{
                    **item,
                    "evidence": [ResearchEvidence(**evidence) for evidence in item["evidence"]],
                }
            )
            for item in json.loads(row["candidates_json"])
        ]
        return ResearchResult(
            task_id=task.id,
            question=task.question,
            template_id=task.template_id,
            summary=row["summary"],
            source=row["source"],
            as_of=row["as_of"],
            scope=json.loads(row["scope_json"]),
            candidates=candidates,
            risks=json.loads(row["risks_json"]),
            created_at=row["created_at"],
        )

    def cancel(self, user_id: str, task_id: str) -> ResearchTask:
        task = self.get(user_id, task_id)
        if task.status not in {"queued", "running"}:
            raise RuntimeError(f"cannot cancel research task from {task.status}")
        finished_at = self._now()
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE research_tasks SET status='cancelled',steps_json=?,finished_at=? WHERE id=? AND user_id=?",
                (json.dumps([asdict(step) for step in self._steps("cancelled")], ensure_ascii=False), finished_at, task_id, user_id),
            )
        return self.get(user_id, task_id)

    def _run(self, user_id: str, task_id: str) -> ResearchTask:
        task = self.get(user_id, task_id)
        started_at = self._now()
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE research_tasks SET status='running',steps_json=?,started_at=? WHERE id=? AND user_id=?",
                (json.dumps([asdict(step) for step in self._steps("running")], ensure_ascii=False), started_at, task_id, user_id),
            )
        try:
            search = self.research.search(task.question, limit=10)
            items = [item for item in search.items if self._matches(item, task.constraints)]
            now = self._now()
            candidates = [self._candidate(item) for item in items]
            observed = [item.as_of for item in items if item.as_of]
            as_of = max(observed) if observed else None
            summary = (
                f"基于 {search.source} 的可用数据，本次研究找到 {len(candidates)} 个满足已确认条件的候选。"
                if candidates
                else f"基于 {search.source} 的当前可用数据，没有找到满足已确认条件的候选。"
            )
            risks = ["公开市场数据可能延迟；结果不构成投资建议。"]
            with self.store.transaction() as conn:
                conn.execute(
                    "INSERT INTO research_results "
                    "(task_id,user_id,summary,source,as_of,scope_json,candidates_json,risks_json,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        user_id,
                        summary,
                        search.source,
                        as_of,
                        json.dumps(task.scope, ensure_ascii=False),
                        json.dumps([asdict(item) for item in candidates], ensure_ascii=False),
                        json.dumps(risks, ensure_ascii=False),
                        now,
                    ),
                )
                for candidate in candidates:
                    for evidence in candidate.evidence:
                        conn.execute(
                            "INSERT INTO research_evidence "
                            "(id,task_id,candidate_code,field,value_json,source,as_of,created_at) VALUES (?,?,?,?,?,?,?,?)",
                            (uuid.uuid4().hex, task_id, candidate.code, evidence.field, json.dumps(evidence.value, ensure_ascii=False), evidence.source, evidence.as_of, now),
                        )
                conn.execute(
                    "UPDATE research_tasks SET status='succeeded',steps_json=?,finished_at=? WHERE id=? AND user_id=?",
                    (json.dumps([asdict(step) for step in self._steps("succeeded")], ensure_ascii=False), now, task_id, user_id),
                )
        except Exception as exc:
            now = self._now()
            with self.store.transaction() as conn:
                conn.execute(
                    "UPDATE research_tasks SET status='failed',steps_json=?,error=?,finished_at=? WHERE id=? AND user_id=?",
                    (json.dumps([asdict(step) for step in self._steps("failed")], ensure_ascii=False), str(exc), now, task_id, user_id),
                )
            raise
        return self.get(user_id, task_id)

    def _candidate(self, item: PublicSearchItem) -> ResearchCandidate:
        evidence = [
            ResearchEvidence(field=field, value=getattr(item, field), source="local_market_store", as_of=item.as_of)
            for field in ("close", "pe_ttm", "pb", "dividend_yield", "total_market_value")
            if getattr(item, field) is not None
        ]
        return ResearchCandidate(
            code=item.code,
            name=item.name,
            industry=item.industry,
            close=item.close,
            pe_ttm=item.pe_ttm,
            pb=item.pb,
            dividend_yield=item.dividend_yield,
            total_market_value=item.total_market_value,
            reason=f"满足 {len(evidence)} 项当前可核验指标。",
            evidence=evidence,
        )

    def _validate_constraints(self, constraints: list[dict[str, Any]]) -> None:
        for constraint in constraints:
            field = str(constraint.get("field") or "")
            op = str(constraint.get("op") or "")
            value = constraint.get("value")
            if field not in self._FIELDS or op not in self._OPS or not isinstance(value, (int, float)):
                raise InvalidResearchConstraint(f"unsupported research constraint: {field} {op}")

    @staticmethod
    def _matches(item: PublicSearchItem, constraints: list[dict[str, Any]]) -> bool:
        operations = {
            ">": lambda left, right: left > right,
            ">=": lambda left, right: left >= right,
            "<": lambda left, right: left < right,
            "<=": lambda left, right: left <= right,
            "=": lambda left, right: left == right,
            "==": lambda left, right: left == right,
        }
        for constraint in constraints:
            current = getattr(item, constraint["field"])
            if current is None or not operations[constraint["op"]](current, constraint["value"]):
                return False
        return True

    @staticmethod
    def _steps(state: str) -> list[ResearchStep]:
        labels = (
            ("interpret", "解析研究问题"),
            ("scan", "扫描市场与基本面数据"),
            ("verify", "核验证据与约束"),
            ("persist", "保存研究结果"),
        )
        if state == "queued":
            statuses = ("pending",) * 4
        elif state == "running":
            statuses = ("completed", "running", "pending", "pending")
        elif state == "succeeded":
            statuses = ("completed",) * 4
        elif state == "cancelled":
            statuses = ("cancelled",) * 4
        else:
            statuses = ("completed", "failed", "pending", "pending")
        return [ResearchStep(key, label, status) for (key, label), status in zip(labels, statuses)]

    def _by_key(self, user_id: str, idempotency_key: str) -> ResearchTask | None:
        row = self.store._get_conn().execute(
            "SELECT * FROM research_tasks WHERE user_id=? AND idempotency_key=?",
            (user_id, idempotency_key),
        ).fetchone()
        return self._task(row) if row else None

    @staticmethod
    def _task(row) -> ResearchTask:
        return ResearchTask(
            id=row["id"],
            user_id=row["user_id"],
            question=row["question"],
            template_id=row["template_id"],
            scope=json.loads(row["scope_json"]),
            constraints=json.loads(row["constraints_json"]),
            status=row["status"],
            steps=[ResearchStep(**item) for item in json.loads(row["steps_json"])],
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )
