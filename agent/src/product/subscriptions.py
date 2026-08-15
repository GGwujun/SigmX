"""Personal saved-query review subscriptions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from src.product.notifications import PersonalNotificationService
from src.product.store import ProductStore


@dataclass(frozen=True)
class SavedQuerySubscription:
    id: str
    saved_query_id: str
    query: str
    frequency: str
    next_run_at: str
    last_run_at: str | None
    created_at: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SavedQuerySubscriptionService:
    def __init__(self, store: ProductStore, now: Callable[[], datetime] = _now) -> None:
        self.store = store
        self._now = now

    def create(self, user_id: str, saved_query_id: str, frequency: str) -> SavedQuerySubscription:
        if frequency not in {"daily", "weekly"}:
            raise ValueError("frequency must be daily or weekly")
        now = self._now()
        with self.store.transaction() as conn:
            query = conn.execute(
                "SELECT query FROM saved_queries WHERE id=? AND user_id=?",
                (saved_query_id, user_id),
            ).fetchone()
            if query is None:
                raise ValueError("saved query not found")
            existing = conn.execute(
                "SELECT id FROM saved_query_subscriptions WHERE saved_query_id=? AND user_id=?",
                (saved_query_id, user_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE saved_query_subscriptions SET frequency=?,next_run_at=? WHERE id=?",
                    (frequency, self._next(now, frequency).isoformat(), existing["id"]),
                )
                subscription_id = existing["id"]
            else:
                subscription_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO saved_query_subscriptions "
                    "(id,user_id,saved_query_id,frequency,next_run_at,last_run_at,created_at) "
                    "VALUES (?,?,?,?,?,NULL,?)",
                    (
                        subscription_id, user_id, saved_query_id, frequency,
                        self._next(now, frequency).isoformat(), now.isoformat(),
                    ),
                )
        return next(item for item in self.list(user_id) if item.id == subscription_id)

    def list(self, user_id: str) -> list[SavedQuerySubscription]:
        rows = self.store._get_conn().execute(
            "SELECT s.*,q.query FROM saved_query_subscriptions s JOIN saved_queries q "
            "ON q.id=s.saved_query_id WHERE s.user_id=? ORDER BY s.created_at DESC",
            (user_id,),
        ).fetchall()
        return [SavedQuerySubscription(
            row["id"], row["saved_query_id"], row["query"], row["frequency"],
            row["next_run_at"], row["last_run_at"], row["created_at"],
        ) for row in rows]

    def delete(self, user_id: str, subscription_id: str) -> bool:
        with self.store.transaction() as conn:
            return conn.execute(
                "DELETE FROM saved_query_subscriptions WHERE id=? AND user_id=?",
                (subscription_id, user_id),
            ).rowcount > 0

    def process_due(self, user_id: str) -> int:
        now = self._now()
        processed = 0
        with self.store.transaction() as conn:
            rows = conn.execute(
                "SELECT s.*,q.query FROM saved_query_subscriptions s JOIN saved_queries q "
                "ON q.id=s.saved_query_id WHERE s.user_id=? AND s.next_run_at<=?",
                (user_id, now.isoformat()),
            ).fetchall()
            for row in rows:
                event_id = f"subscription:{row['id']}:{row['next_run_at']}"
                PersonalNotificationService(self.store).emit(
                    user_id, "cloud", "保存查询复查提醒",
                    f"“{row['query']}”已到复查时间，可在 Web 查看或交给 Desktop 继续研究。",
                    event_id=event_id, conn=conn,
                )
                conn.execute(
                    "UPDATE saved_query_subscriptions SET last_run_at=?,next_run_at=? WHERE id=?",
                    (now.isoformat(), self._next(now, row["frequency"]).isoformat(), row["id"]),
                )
                processed += 1
        return processed

    @staticmethod
    def _next(now: datetime, frequency: str) -> datetime:
        return now + timedelta(days=1 if frequency == "daily" else 7)
