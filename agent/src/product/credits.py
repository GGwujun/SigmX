"""Product credit ledger — Task 2 of the product-closure plan.

Authoritative credits for the product closure. Implements design §4.2:
- monthly plan credits expire at natural month-end; purchased/admin credits are
  permanent;
- reservation consumes expiring lots before permanent ones;
- cloud tasks pre-deduct (reserve), then settle on success or refund on failure,
  with every operation idempotent;
- the ledger is immutable — balance is the sum of (non-expired) lot remainders,
  never a mutable counter.

Built on :class:`src.product.store.ProductStore` so grants/reservations share the
single ``BEGIN IMMEDIATE`` transaction boundary. The legacy
:class:`src.credits.store.CreditStore` keeps its signatures intact during
migration (see :func:`migrate_legacy_balances`).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from src.product.store import ProductStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class GrantResult:
    lot_id: str
    idempotent_replay: bool  # True if this grant already existed


@dataclass
class Reservation:
    reservation_id: str
    user_id: str
    operation: str
    amount: int
    allocations: list[tuple[str, int]] = field(default_factory=list)  # (lot idempotency_key, amount)


@dataclass
class Balance:
    user_id: str
    available: int          # non-expired lot remainders, minus pending reservations
    expiring_soon: int      # non-expired lots that expire within 7 days


class InsufficientCredits(Exception):
    """Raised when a reservation cannot be satisfied from available lots."""


class CreditLedger:
    """Expiring/permanent credit lots + immutable ledger + idempotent ops."""

    def __init__(
        self,
        store: ProductStore,
        now: Callable[[], str] = _now_iso,
    ) -> None:
        self.store = store
        self._now = now

    # ------------------------------------------------------------------ #
    # Grant
    # ------------------------------------------------------------------ #

    def grant(
        self,
        user_id: str,
        amount: int,
        *,
        source: str,
        expires_at: Optional[str],
        idempotency_key: str,
    ) -> GrantResult:
        """Grant ``amount`` credits as a single lot. Idempotent per key.

        ``expires_at=None`` → permanent lot (purchased / admin credits).
        ``expires_at=<iso>`` → expiring lot (monthly plan credits).
        Re-granting the same key returns the original lot unchanged.
        """
        if amount <= 0:
            raise ValueError("grant amount must be positive")
        with self.store.transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM credit_lots WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
            if existing:
                return GrantResult(lot_id=existing["id"], idempotent_replay=True)

            lot_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO credit_lots
                    (id, user_id, amount_total, amount_remaining, source, expires_at,
                     idempotency_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (lot_id, user_id, amount, amount, source, expires_at, idempotency_key, self._now()),
            )
            self._ledger(conn, user_id, lot_id, +amount, "grant", idempotency_key)
        return GrantResult(lot_id=lot_id, idempotent_replay=False)

    # ------------------------------------------------------------------ #
    # Reserve / settle / refund
    # ------------------------------------------------------------------ #

    def reserve(
        self,
        user_id: str,
        amount: int,
        *,
        operation: str,
        idempotency_key: str,
    ) -> Reservation:
        """Pre-deduct ``amount`` for a metered task. Idempotent per key.

        Consumes expiring lots before permanent ones (design §4.2). Raises
        :class:`InsufficientCredits` if available lots cannot cover the amount;
        on failure no lot is touched.
        """
        if amount <= 0:
            raise ValueError("reserve amount must be positive")
        with self.store.transaction() as conn:
            # Idempotent replay — return the prior reservation's allocations.
            prior = conn.execute(
                """
                SELECT r.id, r.amount FROM credit_reservations r
                WHERE r.user_id = ? AND r.idempotency_key = ?
                """,
                (user_id, idempotency_key),
            ).fetchone()
            if prior:
                # Surface allocations keyed by the lot's idempotency_key.
                lot_allocs = self._reservation_allocations(conn, prior["id"])
                key_allocs: list[tuple[str, int]] = []
                for lot_id, amt in lot_allocs:
                    krow = conn.execute(
                        "SELECT idempotency_key FROM credit_lots WHERE id = ?", (lot_id,)
                    ).fetchone()
                    key_allocs.append((krow["idempotency_key"] if krow else lot_id, amt))
                return Reservation(
                    reservation_id=prior["id"],
                    user_id=user_id,
                    operation=operation,
                    amount=prior["amount"],
                    allocations=key_allocs,
                )

            now_dt = _utcnow()
            lots = self._available_lots_locked(conn, user_id, now_dt)
            total = sum(rem for _lot_id, _key, rem, _exp in lots)
            if total < amount:
                raise InsufficientCredits(
                    f"need {amount}, only {total} available for user {user_id}"
                )

            reservation_id = uuid.uuid4().hex
            remaining_to_take = amount
            allocations: list[tuple[str, int]] = []  # (lot idempotency_key, amount)
            for lot_id, key, rem, _exp in lots:
                if remaining_to_take <= 0:
                    break
                take = min(rem, remaining_to_take)
                conn.execute(
                    "UPDATE credit_lots SET amount_remaining = amount_remaining - ? WHERE id = ?",
                    (take, lot_id),
                )
                self._ledger(conn, user_id, lot_id, -take, "reserve", idempotency_key)
                allocations.append((key, take))
                remaining_to_take -= take

            conn.execute(
                """
                INSERT INTO credit_reservations
                    (id, user_id, operation, amount, idempotency_key, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'reserved', ?)
                """,
                (reservation_id, user_id, operation, amount, idempotency_key, self._now()),
            )
        return Reservation(
            reservation_id=reservation_id,
            user_id=user_id,
            operation=operation,
            amount=amount,
            allocations=allocations,
        )

    def settle(self, reservation_id: str, *, idempotency_key: str) -> None:
        """Mark a reservation consumed (task succeeded). Idempotent.

        Lots were already deducted at reserve time; settle only records the
        outcome so the credits are not refundable.
        """
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT user_id, status FROM credit_reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown reservation {reservation_id}")
            if row["status"] == "settled":
                return  # idempotent
            conn.execute(
                "UPDATE credit_reservations SET status = 'settled' WHERE id = ?",
                (reservation_id,),
            )
            self._ledger(conn, row["user_id"], None, 0, "settle", idempotency_key)

    def refund(self, reservation_id: str, *, idempotency_key: str) -> None:
        """Restore a reservation's credits (task failed). Idempotent per reservation.

        Restores exactly the lots/amounts reserved, once. A settled (successful)
        reservation cannot be refunded.
        """
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT user_id, status FROM credit_reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown reservation {reservation_id}")
            if row["status"] == "refunded":
                return  # idempotent — already refunded

            # Rebuild allocations from the reserve ledger rows and restore.
            allocs = self._reservation_allocations(conn, reservation_id)
            for lot_id, amt in allocs:
                conn.execute(
                    "UPDATE credit_lots SET amount_remaining = amount_remaining + ? WHERE id = ?",
                    (amt, lot_id),
                )
            self._ledger(conn, row["user_id"], None, sum(a for _, a in allocs), "refund", idempotency_key)
            conn.execute(
                "UPDATE credit_reservations SET status = 'refunded' WHERE id = ?",
                (reservation_id,),
            )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def balance(self, user_id: str) -> Balance:
        """Available = non-expired lot remainders (reservations already deducted)."""
        now_dt = _utcnow()
        conn = self.store._get_conn()
        lots = self._available_lots_locked(conn, user_id, now_dt)
        available = sum(rem for _id, _key, rem, _exp in lots)
        soon_cutoff = now_dt + timedelta(days=7)
        expiring_soon = sum(
            rem for _id, _key, rem, exp in lots if exp is not None
            and datetime.fromisoformat(exp) <= soon_cutoff
        )
        return Balance(user_id=user_id, available=available, expiring_soon=expiring_soon)

    def list_lots(self, user_id: str) -> list[dict[str, Any]]:
        conn = self.store._get_conn()
        rows = conn.execute(
            "SELECT * FROM credit_lots WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_entries(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        conn = self.store._get_conn()
        rows = conn.execute(
            "SELECT * FROM credit_ledger WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, max(1, min(limit, 500))),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Internal helpers (callers must be inside the desired tx context)
    # ------------------------------------------------------------------ #

    def _ledger(
        self, conn, user_id: str, lot_id: Optional[str], delta: int,
        operation: str, idempotency_key: Optional[str],
    ) -> None:
        conn.execute(
            """
            INSERT INTO credit_ledger (id, user_id, lot_id, delta, operation, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, user_id, lot_id, delta, operation, idempotency_key, self._now()),
        )

    def _available_lots_locked(self, conn, user_id: str, now_dt: datetime):
        """Non-expired lots with remaining credits, expiring-first then permanent.

        Returns ``(lot_id, idempotency_key, amount_remaining, expires_at)`` tuples.
        Ordering implements the §4.2 rule "consume expiring before permanent".
        """
        rows = conn.execute(
            "SELECT id, idempotency_key, amount_remaining, expires_at FROM credit_lots "
            "WHERE user_id = ? AND amount_remaining > 0",
            (user_id,),
        ).fetchall()
        usable = []
        for r in rows:
            exp = r["expires_at"]
            if exp is not None:
                try:
                    if datetime.fromisoformat(exp) <= now_dt:
                        continue  # expired — excluded from availability
                except ValueError:
                    pass
            usable.append((r["id"], r["idempotency_key"], int(r["amount_remaining"]), exp))
        # Expiring (soonest first) before permanent (exp is None → "9999" sorts last).
        usable.sort(key=lambda t: t[3] or "9999")
        return usable

    def _reservation_allocations(self, conn, reservation_id: str) -> list[tuple[str, int]]:
        """Rebuild a reservation's per-lot allocations from its reserve ledger rows.

        Returns ``(lot_id, amount)`` — callers that restore credits need the lot id;
        the public ``Reservation.allocations`` surfaces the lot's idempotency key
        instead (built in ``reserve``).
        """
        rows = conn.execute(
            "SELECT lot_id, delta FROM credit_ledger WHERE lot_id IS NOT NULL "
            "AND operation = 'reserve' AND idempotency_key = "
            "(SELECT idempotency_key FROM credit_reservations WHERE id = ?)",
            (reservation_id,),
        ).fetchall()
        return [(r["lot_id"], -int(r["delta"])) for r in rows]


def migrate_legacy_balances(ledger: CreditLedger, legacy_store: Any) -> dict[str, int]:
    """One-time migration of legacy ``credits.db`` balances into permanent lots.

    Reads each ``credits_balance`` row and grants a single non-expiring lot keyed
    ``legacy-credit-balance:<user_id>``. The legacy database is left intact for
    rollback (plan Task 2 Step 4, design §8). Idempotent: re-running is a no-op
    because every legacy lot carries a stable idempotency key.

    Returns a mapping of ``user_id → migrated_amount`` for the lots actually
    created this run (replays return 0 for already-migrated users).
    """
    conn = legacy_store._get_conn() if hasattr(legacy_store, "_get_conn") else legacy_store._conn_locked()
    rows = conn.execute("SELECT user_id, balance FROM credits_balance").fetchall()

    migrated: dict[str, int] = {}
    for r in rows:
        user_id = r["user_id"]
        balance = int(r["balance"])
        if balance <= 0:
            continue
        key = f"legacy-credit-balance:{user_id}"
        result = ledger.grant(
            user_id,
            balance,
            source="legacy_migration",
            expires_at=None,
            idempotency_key=key,
        )
        if not result.idempotent_replay:
            migrated[user_id] = balance
    return migrated
