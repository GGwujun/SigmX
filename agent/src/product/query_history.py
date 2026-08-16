"""Versioned personal query execution history."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.product.store import ProductStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class QueryExecution:
    id: str
    user_id: str
    query: str
    intent: str
    conditions: tuple[dict[str, Any], ...]
    condition_version: int
    result_count: int
    executed_at: str


class QueryHistoryService:
    def __init__(self, store: ProductStore, now: Callable[[], str] = _now_iso) -> None:
        self.store = store
        self._now = now

    def record(
        self,
        user_id: str,
        *,
        query: str,
        intent: str,
        conditions: list[dict[str, Any]],
        result_count: int,
        idempotency_key: str | None = None,
    ) -> QueryExecution:
        key = idempotency_key or uuid.uuid4().hex
        existing = self.store._get_conn().execute(
            "SELECT * FROM query_executions WHERE user_id=? AND idempotency_key=?", (user_id, key)
        ).fetchone()
        if existing:
            return self._execution(existing)
        normalized = " ".join(query.strip().split())
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(condition_version),0) AS version FROM query_executions WHERE user_id=? AND query=?",
                (user_id, normalized),
            ).fetchone()
            version = int(row["version"]) + 1
            execution_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO query_executions (id,user_id,query,intent,conditions_json,condition_version,result_count,idempotency_key,executed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (execution_id, user_id, normalized, intent, json.dumps(conditions, ensure_ascii=False), version, max(0, int(result_count)), key, self._now()),
            )
        return self.get(user_id, execution_id)

    def get(self, user_id: str, execution_id: str) -> QueryExecution:
        row = self.store._get_conn().execute(
            "SELECT * FROM query_executions WHERE user_id=? AND id=?", (user_id, execution_id)
        ).fetchone()
        if row is None:
            raise KeyError(execution_id)
        return self._execution(row)

    def list(self, user_id: str, limit: int = 100) -> list[QueryExecution]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM query_executions WHERE user_id=? ORDER BY executed_at DESC,condition_version DESC LIMIT ?",
            (user_id, max(1, min(limit, 500))),
        ).fetchall()
        return [self._execution(row) for row in rows]

    @staticmethod
    def _execution(row) -> QueryExecution:
        return QueryExecution(
            id=row["id"], user_id=row["user_id"], query=row["query"], intent=row["intent"],
            conditions=tuple(json.loads(row["conditions_json"])), condition_version=int(row["condition_version"]),
            result_count=int(row["result_count"]), executed_at=row["executed_at"],
        )
