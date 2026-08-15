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

    def authorize(
        self,
        owner_id: str,
        endpoint_code: str,
        max_cost: int,
        idempotency_key: str,
    ) -> DataCreditAuthorization:
        if max_cost <= 0:
            raise ValueError("authorization amount must be positive")
        with self.store.transaction() as conn:
            prior = conn.execute(
                "SELECT * FROM data_credit_reservations WHERE owner_id = ? AND idempotency_key = ?",
                (owner_id, idempotency_key),
            ).fetchone()
            if prior:
                if prior["endpoint_code"] != endpoint_code or prior["amount_authorized"] != max_cost:
                    raise ValueError("idempotency key conflicts with an existing authorization")
                return self._authorization(conn, prior)

            lots = self._available_lots(conn, owner_id, datetime.now(timezone.utc))
            if sum(lot[2] for lot in lots) < max_cost:
                raise InsufficientDataCredits(
                    f"requires {max_cost} data credits, but available balance is insufficient"
                )
            reservation_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO data_credit_reservations "
                "(id, owner_id, endpoint_code, amount_authorized, amount_settled, "
                "idempotency_key, status, created_at, settled_at) "
                "VALUES (?, ?, ?, ?, NULL, ?, 'authorized', ?, NULL)",
                (reservation_id, owner_id, endpoint_code, max_cost, idempotency_key, self._now()),
            )
            remaining = max_cost
            allocations: list[tuple[str, int]] = []
            for lot_id, _, available, _ in lots:
                amount = min(available, remaining)
                if amount <= 0:
                    continue
                conn.execute(
                    "UPDATE data_credit_lots SET amount_remaining = amount_remaining - ? WHERE id = ?",
                    (amount, lot_id),
                )
                conn.execute(
                    "INSERT INTO data_credit_allocations (reservation_id, lot_id, amount) VALUES (?, ?, ?)",
                    (reservation_id, lot_id, amount),
                )
                self._ledger(
                    conn, owner_id, lot_id, reservation_id, -amount, "authorize", idempotency_key
                )
                allocations.append((lot_id, amount))
                remaining -= amount
                if remaining == 0:
                    break
        return DataCreditAuthorization(
            reservation_id, owner_id, endpoint_code, max_cost, tuple(allocations)
        )

    def settle(
        self, reservation_id: str, actual_cost: int, idempotency_key: str
    ) -> DataCreditSettlement:
        if actual_cost < 0:
            raise InvalidDataCreditSettlement("actual cost cannot be negative")
        with self.store.transaction() as conn:
            reservation = conn.execute(
                "SELECT * FROM data_credit_reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            if reservation is None:
                raise UnknownDataCreditReservation(reservation_id)
            if reservation["status"] != "authorized":
                if reservation["status"] == "settled" and reservation["amount_settled"] == actual_cost:
                    return self._settlement(reservation)
                raise InvalidDataCreditSettlement("reservation has already been finalized")
            authorized = int(reservation["amount_authorized"])
            if actual_cost > authorized:
                raise InvalidDataCreditSettlement("actual cost exceeds authorized amount")
            released = authorized - actual_cost
            self._restore_allocations(
                conn, reservation, released, "release", f"{idempotency_key}:release"
            )
            conn.execute(
                "UPDATE data_credit_reservations SET status = 'settled', amount_settled = ?, "
                "settled_at = ? WHERE id = ?",
                (actual_cost, self._now(), reservation_id),
            )
            self._ledger(
                conn,
                reservation["owner_id"],
                None,
                reservation_id,
                0,
                "settle",
                idempotency_key,
                {"actual_cost": actual_cost, "released": released},
            )
            finalized = conn.execute(
                "SELECT * FROM data_credit_reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            return self._settlement(finalized)

    def release(self, reservation_id: str, idempotency_key: str) -> DataCreditSettlement:
        with self.store.transaction() as conn:
            reservation = conn.execute(
                "SELECT * FROM data_credit_reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            if reservation is None:
                raise UnknownDataCreditReservation(reservation_id)
            if reservation["status"] == "released":
                return self._settlement(reservation)
            if reservation["status"] != "authorized":
                raise InvalidDataCreditSettlement("reservation has already been finalized")
            authorized = int(reservation["amount_authorized"])
            self._restore_allocations(conn, reservation, authorized, "release", idempotency_key)
            conn.execute(
                "UPDATE data_credit_reservations SET status = 'released', amount_settled = 0, "
                "settled_at = ? WHERE id = ?",
                (self._now(), reservation_id),
            )
            finalized = conn.execute(
                "SELECT * FROM data_credit_reservations WHERE id = ?", (reservation_id,)
            ).fetchone()
            return self._settlement(finalized)

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
    def _authorization(conn, reservation) -> DataCreditAuthorization:
        allocations = conn.execute(
            "SELECT lot_id, amount FROM data_credit_allocations WHERE reservation_id = ? "
            "ORDER BY rowid",
            (reservation["id"],),
        ).fetchall()
        return DataCreditAuthorization(
            reservation["id"],
            reservation["owner_id"],
            reservation["endpoint_code"],
            int(reservation["amount_authorized"]),
            tuple((row["lot_id"], int(row["amount"])) for row in allocations),
        )

    @staticmethod
    def _settlement(reservation) -> DataCreditSettlement:
        authorized = int(reservation["amount_authorized"])
        settled = int(reservation["amount_settled"] or 0)
        return DataCreditSettlement(
            reservation["id"], authorized, settled, authorized - settled, reservation["status"]
        )

    def _restore_allocations(
        self, conn, reservation, amount_to_restore: int, operation: str, idempotency_key: str
    ) -> None:
        rows = conn.execute(
            "SELECT a.lot_id, a.amount, l.expires_at, l.created_at "
            "FROM data_credit_allocations a JOIN data_credit_lots l ON l.id = a.lot_id "
            "WHERE a.reservation_id = ? "
            "ORDER BY CASE WHEN l.expires_at IS NULL THEN 1 ELSE 0 END DESC, "
            "l.expires_at DESC, l.created_at DESC",
            (reservation["id"],),
        ).fetchall()
        remaining = amount_to_restore
        for row in rows:
            restored = min(int(row["amount"]), remaining)
            if restored <= 0:
                continue
            conn.execute(
                "UPDATE data_credit_lots SET amount_remaining = amount_remaining + ? WHERE id = ?",
                (restored, row["lot_id"]),
            )
            self._ledger(
                conn,
                reservation["owner_id"],
                row["lot_id"],
                reservation["id"],
                restored,
                operation,
                idempotency_key,
            )
            remaining -= restored
            if remaining == 0:
                break

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
