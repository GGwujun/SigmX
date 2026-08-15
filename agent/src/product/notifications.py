"""Unified user-owned notification inbox and delivery preferences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.product.store import ProductStore


@dataclass(frozen=True)
class NotificationPreferences:
    budget_alerts: bool
    product_updates: bool
    cloud_tasks: bool


@dataclass(frozen=True)
class PersonalNotification:
    id: str
    kind: str
    title: str
    body: str
    read_at: str | None
    created_at: str


class PersonalNotificationService:
    def __init__(self, store: ProductStore) -> None:
        self.store = store

    def preferences(self, user_id: str) -> NotificationPreferences:
        row = self.store._get_conn().execute(
            "SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is None:
            return NotificationPreferences(True, True, True)
        return NotificationPreferences(
            bool(row["budget_alerts"]), bool(row["product_updates"]), bool(row["cloud_tasks"])
        )

    def set_preferences(
        self, user_id: str, *, budget_alerts: bool, product_updates: bool, cloud_tasks: bool
    ) -> NotificationPreferences:
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO notification_preferences "
                "(user_id,budget_alerts,product_updates,cloud_tasks,updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET budget_alerts=excluded.budget_alerts,"
                "product_updates=excluded.product_updates,cloud_tasks=excluded.cloud_tasks,"
                "updated_at=excluded.updated_at",
                (user_id, int(budget_alerts), int(product_updates), int(cloud_tasks), self._now()),
            )
        return self.preferences(user_id)

    def emit(
        self, user_id: str, kind: str, title: str, body: str, *, event_id: str, conn=None
    ) -> bool:
        preference = {
            "budget": "budget_alerts", "product": "product_updates", "cloud": "cloud_tasks"
        }.get(kind)
        preferences = self.preferences(user_id)
        if preference and not getattr(preferences, preference):
            return False
        if conn is not None:
            return self._insert(conn, user_id, kind, title, body, event_id)
        with self.store.transaction() as tx:
            return self._insert(tx, user_id, kind, title, body, event_id)

    def list(self, user_id: str, limit: int = 100) -> list[PersonalNotification]:
        rows = self.store._get_conn().execute(
            "SELECT id,kind,title,body,read_at,created_at FROM personal_notifications "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, max(1, min(limit, 500))),
        ).fetchall()
        return [PersonalNotification(**dict(row)) for row in rows]

    def mark_read(self, user_id: str, notification_id: str) -> bool:
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "UPDATE personal_notifications SET read_at=COALESCE(read_at,?) "
                "WHERE id=? AND user_id=?",
                (self._now(), notification_id, user_id),
            )
            return cursor.rowcount > 0

    def _insert(self, conn, user_id: str, kind: str, title: str, body: str, event_id: str) -> bool:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO personal_notifications "
            "(id,user_id,kind,title,body,read_at,created_at) VALUES (?,?,?,?,?,NULL,?)",
            (event_id, user_id, kind, title, body, self._now()),
        )
        return cursor.rowcount > 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
