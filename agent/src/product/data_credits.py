"""Independent Data Hub credit lots and reservation ledger."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from src.product.store import ProductStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DataGrantResult:
    lot_id: str
    idempotent_replay: bool


@dataclass(frozen=True)
class DataCreditBalance:
    owner_id: str
    available: int
    expiring_soon: int


@dataclass(frozen=True)
class DataCreditAuthorization:
    reservation_id: str
    owner_id: str
    endpoint_code: str
    amount_authorized: int
    allocations: tuple[tuple[str, int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DataCreditSettlement:
    reservation_id: str
    amount_authorized: int
    amount_settled: int
    amount_released: int
    status: str


class InsufficientDataCredits(Exception):
    pass


class UnknownDataCreditReservation(Exception):
    pass


class InvalidDataCreditSettlement(Exception):
    pass


class DataCreditLedger:
    def __init__(self, store: ProductStore, now: Callable[[], str] = _now_iso) -> None:
        self.store = store
        self._now = now

    def grant(
        self,
        owner_id: str,
        amount: int,
        *,
        source: str,
        expires_at: str | None,
        idempotency_key: str,
    ) -> DataGrantResult:
        if amount <= 0:
            raise ValueError("grant amount must be positive")
        with self.store.transaction() as conn:
            prior = conn.execute(
                "SELECT id FROM data_credit_lots WHERE owner_id = ? AND idempotency_key = ?",
                (owner_id, idempotency_key),
            ).fetchone()
            if prior:
                return DataGrantResult(prior["id"], True)
            lot_id = uuid.uuid4().hex
            created_at = self._now()
            conn.execute(
                """
                INSERT INTO data_credit_lots
                    (id, owner_id, amount_total, amount_remaining, source, expires_at,
                     idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (lot_id, owner_id, amount, amount, source, expires_at, idempotency_key, created_at),
            )
            self._ledger(conn, owner_id, lot_id, None, amount, "grant", idempotency_key)
        return DataGrantResult(lot_id, False)

    def balance(self, owner_id: str) -> DataCreditBalance:
        now = datetime.now(timezone.utc)
        lots = self._available_lots(self.store._get_conn(), owner_id, now)
        soon = now + timedelta(days=7)
        return DataCreditBalance(
            owner_id=owner_id,
            available=sum(row[2] for row in lots),
            expiring_soon=sum(
                row[2]
                for row in lots
                if row[3] is not None and datetime.fromisoformat(row[3]) <= soon
            ),
        )

    def list_lots(self, owner_id: str) -> list[dict[str, Any]]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM data_credit_lots WHERE owner_id = ? ORDER BY created_at, id",
            (owner_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_entries(self, owner_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.store._get_conn().execute(
            "SELECT * FROM data_credit_ledger WHERE owner_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (owner_id, max(1, min(limit, 500))),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _available_lots(conn, owner_id: str, now: datetime):
        rows = conn.execute(
            "SELECT id, idempotency_key, amount_remaining, expires_at "
            "FROM data_credit_lots WHERE owner_id = ? AND amount_remaining > 0",
            (owner_id,),
        ).fetchall()
        usable = []
        for row in rows:
            expires_at = row["expires_at"]
            if expires_at is not None:
                try:
                    if datetime.fromisoformat(expires_at) <= now:
                        continue
                except ValueError:
                    pass
            usable.append((row["id"], row["idempotency_key"], int(row["amount_remaining"]), expires_at))
        usable.sort(key=lambda item: item[3] or "9999")
        return usable

    def _ledger(
        self,
        conn,
        owner_id: str,
        lot_id: str | None,
        reservation_id: str | None,
        delta: int,
        operation: str,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO data_credit_ledger
                (id, owner_id, lot_id, reservation_id, delta, operation,
                 idempotency_key, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                owner_id,
                lot_id,
                reservation_id,
                delta,
                operation,
                idempotency_key,
                json.dumps(metadata, sort_keys=True) if metadata is not None else None,
                self._now(),
            ),
        )


def grant_monthly_data_credits(
    ledger: DataCreditLedger,
    owner_id: str,
    plan_code: str,
    period: date,
) -> DataGrantResult | None:
    plan = ledger.store.get_plan(plan_code)
    if plan is None:
        raise ValueError(f"unknown plan {plan_code}")
    amount = int(plan["entitlements"].get("datahub.monthly_credits", 0))
    if amount <= 0:
        return None
    if period.month == 12:
        expires = date(period.year + 1, 1, 1)
    else:
        expires = date(period.year, period.month + 1, 1)
    expires_at = datetime(expires.year, expires.month, expires.day, tzinfo=timezone.utc).isoformat()
    return ledger.grant(
        owner_id,
        amount,
        source="data_monthly",
        expires_at=expires_at,
        idempotency_key=f"data-plan-month:{owner_id}:{plan_code}:{period:%Y-%m}",
    )
