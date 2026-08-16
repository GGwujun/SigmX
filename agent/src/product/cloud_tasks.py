"""Authoritative personal cloud-task lifecycle with Research Credit settlement."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.product.credits import CreditLedger
from src.product.store import ProductStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvalidTaskTransition(Exception):
    pass


@dataclass(frozen=True)
class CloudTask:
    id: str
    user_id: str
    task_type: str
    title: str
    status: str
    payload: dict[str, Any]
    reserved_credits: int
    reservation_id: str
    result_ref: str | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class CloudTaskService:
    def __init__(self, store: ProductStore, ledger: CreditLedger, now: Callable[[], str] = _now_iso) -> None:
        self.store = store
        self.ledger = ledger
        self._now = now

    def create(
        self,
        user_id: str,
        *,
        task_type: str,
        title: str,
        cost: int,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> CloudTask:
        existing = self._by_key(user_id, idempotency_key)
        if existing:
            return existing
        reservation = self.ledger.reserve(
            user_id,
            cost,
            operation=f"cloud_task:{task_type}",
            idempotency_key=f"cloud-task:{idempotency_key}",
        )
        task_id = uuid.uuid4().hex
        try:
            with self.store.transaction() as conn:
                conn.execute(
                    "INSERT INTO cloud_tasks (id,user_id,task_type,title,status,payload_json,reserved_credits,"
                    "reservation_id,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (task_id, user_id, task_type, title, "queued", json.dumps(payload, ensure_ascii=False),
                     cost, reservation.reservation_id, idempotency_key, self._now()),
                )
        except Exception:
            self.ledger.refund(reservation.reservation_id, idempotency_key=f"cloud-task-create-refund:{task_id}")
            raise
        return self.get(user_id, task_id)

    def start(self, user_id: str, task_id: str) -> CloudTask:
        return self._transition(user_id, task_id, allowed={"queued"}, target="running", started_at=self._now())

    def succeed(self, user_id: str, task_id: str, *, result_ref: str) -> CloudTask:
        task = self.get(user_id, task_id)
        if task.status == "succeeded":
            return task
        if task.status not in {"queued", "running"}:
            raise InvalidTaskTransition(f"cannot succeed task from {task.status}")
        self.ledger.settle(task.reservation_id, idempotency_key=f"cloud-task-settle:{task.id}")
        return self._transition(user_id, task_id, allowed={"queued", "running"}, target="succeeded", result_ref=result_ref, finished_at=self._now())

    def fail(self, user_id: str, task_id: str, *, error: str) -> CloudTask:
        task = self.get(user_id, task_id)
        if task.status == "failed":
            return task
        if task.status not in {"queued", "running"}:
            raise InvalidTaskTransition(f"cannot fail task from {task.status}")
        self.ledger.refund(task.reservation_id, idempotency_key=f"cloud-task-refund:{task.id}")
        return self._transition(user_id, task_id, allowed={"queued", "running"}, target="failed", error=error, finished_at=self._now())

    def cancel(self, user_id: str, task_id: str) -> CloudTask:
        task = self.get(user_id, task_id)
        if task.status == "cancelled":
            return task
        if task.status not in {"queued", "running"}:
            raise InvalidTaskTransition(f"cannot cancel task from {task.status}")
        self.ledger.refund(task.reservation_id, idempotency_key=f"cloud-task-cancel:{task.id}")
        return self._transition(user_id, task_id, allowed={"queued", "running"}, target="cancelled", finished_at=self._now())

    def get(self, user_id: str, task_id: str) -> CloudTask:
        row = self.store._get_conn().execute(
            "SELECT * FROM cloud_tasks WHERE id=? AND user_id=?", (task_id, user_id)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task(row)

    def list(self, user_id: str, limit: int = 50) -> list[CloudTask]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM cloud_tasks WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, max(1, min(limit, 200))),
        ).fetchall()
        return [self._task(row) for row in rows]

    def _by_key(self, user_id: str, idempotency_key: str) -> CloudTask | None:
        row = self.store._get_conn().execute(
            "SELECT * FROM cloud_tasks WHERE user_id=? AND idempotency_key=?", (user_id, idempotency_key)
        ).fetchone()
        return self._task(row) if row else None

    def _transition(self, user_id: str, task_id: str, *, allowed: set[str], target: str, **values: str) -> CloudTask:
        task = self.get(user_id, task_id)
        if task.status not in allowed:
            raise InvalidTaskTransition(f"cannot transition task from {task.status} to {target}")
        assignments = ["status=?", *(f"{key}=?" for key in values)]
        params = [target, *values.values(), task_id, user_id, *sorted(allowed)]
        placeholders = ",".join("?" for _ in allowed)
        with self.store.transaction() as conn:
            cursor = conn.execute(
                f"UPDATE cloud_tasks SET {','.join(assignments)} WHERE id=? AND user_id=? AND status IN ({placeholders})",
                params,
            )
            if cursor.rowcount != 1:
                raise InvalidTaskTransition("task state changed concurrently")
        return self.get(user_id, task_id)

    @staticmethod
    def _task(row) -> CloudTask:
        return CloudTask(
            id=row["id"], user_id=row["user_id"], task_type=row["task_type"], title=row["title"],
            status=row["status"], payload=json.loads(row["payload_json"]),
            reserved_credits=int(row["reserved_credits"]), reservation_id=row["reservation_id"],
            result_ref=row["result_ref"], error=row["error"], created_at=row["created_at"],
            started_at=row["started_at"], finished_at=row["finished_at"],
        )
