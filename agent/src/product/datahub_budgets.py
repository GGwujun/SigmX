"""Per-personal-Credential daily Data Credit budgets and threshold events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from src.product.store import ProductStore


class DailyBudgetExceeded(Exception):
    pass


@dataclass(frozen=True)
class CredentialBudget:
    credential_id: str
    daily_limit: int
    spent_today: int
    remaining_today: int
    utc_date: str


@dataclass(frozen=True)
class BudgetAlert:
    credential_id: str
    credential_name: str
    utc_date: str
    threshold_percent: int
    spent: int
    daily_limit: int
    created_at: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataHubBudgetService:
    def __init__(self, store: ProductStore, now: Callable[[], datetime] = _utc_now) -> None:
        self.store = store
        self._now = now

    def set(self, user_id: str, credential_id: str, daily_limit: int | None) -> CredentialBudget | None:
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM datahub_credentials WHERE id=? AND user_id=? "
                "AND credential_kind='personal'",
                (credential_id, user_id),
            ).fetchone()
            if row is None:
                raise ValueError("personal credential not found")
            if daily_limit is None:
                conn.execute("DELETE FROM datahub_credential_budgets WHERE credential_id=?", (credential_id,))
                return None
            if not isinstance(daily_limit, int) or daily_limit < 1:
                raise ValueError("daily_limit must be a positive integer")
            conn.execute(
                "INSERT INTO datahub_credential_budgets (credential_id,user_id,daily_limit,updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(credential_id) DO UPDATE SET "
                "daily_limit=excluded.daily_limit,updated_at=excluded.updated_at",
                (credential_id, user_id, daily_limit, self._now().isoformat()),
            )
        return self.get(user_id, credential_id)

    def get(self, user_id: str, credential_id: str) -> CredentialBudget | None:
        row = self.store._get_conn().execute(
            "SELECT daily_limit FROM datahub_credential_budgets WHERE credential_id=? AND user_id=?",
            (credential_id, user_id),
        ).fetchone()
        if row is None:
            return None
        spent = self._spent(self.store._get_conn(), credential_id)
        limit = int(row["daily_limit"])
        return CredentialBudget(credential_id, limit, spent, max(0, limit - spent), self._now().date().isoformat())

    def list(self, user_id: str) -> list[CredentialBudget]:
        rows = self.store._get_conn().execute(
            "SELECT credential_id FROM datahub_credential_budgets WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [budget for row in rows if (budget := self.get(user_id, row["credential_id"])) is not None]

    def check(self, user_id: str, credential_id: str, credits_authorized: int) -> None:
        budget = self.get(user_id, credential_id)
        if budget and budget.spent_today + credits_authorized > budget.daily_limit:
            raise DailyBudgetExceeded(
                f"daily Data Credit budget exceeded ({budget.spent_today}/{budget.daily_limit})"
            )

    def reserve(self, user_id: str, credential_id: str, request_id: str, credits_authorized: int) -> None:
        if credits_authorized <= 0:
            return
        now = self._now()
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM datahub_budget_holds WHERE expires_at<=?", (now.isoformat(),))
            budget = conn.execute(
                "SELECT daily_limit FROM datahub_credential_budgets WHERE credential_id=? AND user_id=?",
                (credential_id, user_id),
            ).fetchone()
            if budget is None:
                return
            spent = self._spent(conn, credential_id)
            held = conn.execute(
                "SELECT COALESCE(SUM(credits_authorized),0) held FROM datahub_budget_holds "
                "WHERE credential_id=? AND expires_at>?",
                (credential_id, now.isoformat()),
            ).fetchone()["held"]
            limit = int(budget["daily_limit"])
            if spent + int(held or 0) + credits_authorized > limit:
                raise DailyBudgetExceeded(f"daily Data Credit budget exceeded ({spent}/{limit})")
            conn.execute(
                "INSERT INTO datahub_budget_holds "
                "(request_id,credential_id,user_id,credits_authorized,expires_at,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    request_id,
                    credential_id,
                    user_id,
                    credits_authorized,
                    (now + timedelta(minutes=30)).isoformat(),
                    now.isoformat(),
                ),
            )

    def release(self, request_id: str, conn=None) -> None:
        if conn is not None:
            conn.execute("DELETE FROM datahub_budget_holds WHERE request_id=?", (request_id,))
            return
        with self.store.transaction() as tx:
            tx.execute("DELETE FROM datahub_budget_holds WHERE request_id=?", (request_id,))

    def record_events(self, conn, user_id: str, credential_id: str) -> None:
        row = conn.execute(
            "SELECT daily_limit FROM datahub_credential_budgets WHERE credential_id=? AND user_id=?",
            (credential_id, user_id),
        ).fetchone()
        if row is None:
            return
        limit = int(row["daily_limit"])
        spent = self._spent(conn, credential_id)
        date = self._now().date().isoformat()
        now = self._now().isoformat()
        for threshold in (50, 80, 100):
            if spent * 100 >= limit * threshold:
                conn.execute(
                    "INSERT OR IGNORE INTO datahub_budget_events "
                    "(credential_id,user_id,utc_date,threshold_percent,spent,daily_limit,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (credential_id, user_id, date, threshold, spent, limit, now),
                )

    def list_events(self, user_id: str, limit: int = 100) -> list[BudgetAlert]:
        rows = self.store._get_conn().execute(
            "SELECT e.*, c.name credential_name FROM datahub_budget_events e "
            "JOIN datahub_credentials c ON c.id=e.credential_id WHERE e.user_id=? "
            "ORDER BY e.created_at DESC, e.threshold_percent DESC LIMIT ?",
            (user_id, max(1, min(limit, 500))),
        ).fetchall()
        return [BudgetAlert(row["credential_id"], row["credential_name"], row["utc_date"], row["threshold_percent"], row["spent"], row["daily_limit"], row["created_at"]) for row in rows]

    def _spent(self, conn, credential_id: str) -> int:
        day = self._now().date()
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        row = conn.execute(
            "SELECT COALESCE(SUM(credits_charged),0) spent FROM datahub_request_usage "
            "WHERE credential_id=? AND created_at>=? AND created_at<?",
            (credential_id, start.isoformat(), end.isoformat()),
        ).fetchone()
        return int(row["spent"] or 0)
