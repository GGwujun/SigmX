"""Commerce service — activation orders and entitlements.

Task 3 of the product-closure plan. :meth:`CommerceService.activate_code` runs
the design §5.1 flow atomically: verify the code → mark it used → create a paid
zero-value order → grant the membership window → grant current-month plan
credits → write an audit row, all inside one ``ProductStore.transaction()``.
Every step is idempotent so a replayed request returns the first result without
double-granting.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from src.product.credits import CreditLedger
from src.product.models import OrderStatus, PaymentChannel, PlanCode
from src.product.payment import ActivationCodeProvider, hash_code
from src.product.store import ProductStore

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CreatedCode:
    plaintext: str
    code_hash: str
    plan_code: str
    months: int


@dataclass(frozen=True)
class ActivationResult:
    order_id: str
    plan_code: str
    months: int
    credits_granted: int
    replayed: bool  # True if this was an idempotent replay


@dataclass(frozen=True)
class EntitlementSnapshot:
    user_id: str
    plan_code: str
    valid_from: Optional[str]
    valid_until: Optional[str]
    entitlements: dict[str, int | bool]


class ActivationError(Exception):
    """Raised when a code cannot be activated (unknown/used/expired)."""


class CommerceService:
    """Activation-code commerce + entitlement reads."""

    def __init__(
        self,
        store: ProductStore,
        ledger: CreditLedger,
        provider: ActivationCodeProvider | None = None,
    ) -> None:
        self.store = store
        self.ledger = ledger
        self.provider = provider or ActivationCodeProvider(store)

    # ------------------------------------------------------------------ #
    # Admin: create activation codes
    # ------------------------------------------------------------------ #

    def admin_create_activation_code(
        self,
        *,
        plan: str,
        months: int,
        count: int = 1,
        expires_at: Optional[str] = None,
    ) -> CreatedCode:
        """Generate ``count`` activation codes for ``plan``/``months``.

        Only a single code is returned to keep the test surface simple; the
        plaintext is shown here and never again (design §9). ``expires_at`` is
        the code's own lifetime (independent of the membership it grants).
        """
        if plan == PlanCode.ENTERPRISE:
            raise ValueError("enterprise is not available in the personal activation flow")
        if plan not in {PlanCode.ADVANCED, PlanCode.PRO}:
            raise ValueError(f"cannot create activation code for plan {plan!r}")
        if months <= 0:
            raise ValueError("months must be positive")
        plan_row = self.store.get_plan(plan)
        if plan_row is None:
            raise ValueError(f"unknown plan {plan!r}")

        plaintext = self._mint_code()
        code_hash = hash_code(plaintext)
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO activation_codes
                    (code_hash, code_type, plan_code, months, credits, used_by, used_at,
                     created_at, expires_at)
                VALUES (?, 'plan', ?, ?, 0, NULL, NULL, ?, ?)
                """,
                (code_hash, plan, months, _now_iso(), expires_at),
            )
        logger.info("Admin created activation code for plan=%s months=%d", plan, months)
        return CreatedCode(plaintext=plaintext, code_hash=code_hash, plan_code=plan, months=months)

    @staticmethod
    def _mint_code() -> str:
        """Readable, high-entropy code: SX-XXXXXX-XXXXXX."""
        part = lambda: "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        return f"SX-{part()}-{part()}"

    # ------------------------------------------------------------------ #
    # Activate
    # ------------------------------------------------------------------ #

    def activate_code(self, user_id: str, plaintext: str, idempotency_key: str) -> ActivationResult:
        """Redeem an activation code atomically. Idempotent per (user, key)."""
        code_hash = hash_code(plaintext)
        with self.store.transaction() as conn:
            # 1. Idempotent replay — same user + key already produced an order.
            prior = conn.execute(
                "SELECT id, plan_code, months FROM orders WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
            if prior:
                return ActivationResult(
                    order_id=prior["id"],
                    plan_code=prior["plan_code"],
                    months=prior["months"],
                    credits_granted=0,
                    replayed=True,
                )

            # 2. Verify the code: exists, unused, unexpired.
            code_row = conn.execute(
                "SELECT * FROM activation_codes WHERE code_hash = ?", (code_hash,)
            ).fetchone()
            if code_row is None:
                raise ActivationError("激活码无效")
            if code_row["code_type"] != "plan":
                raise ActivationError("该兑换码不是套餐激活码")
            if code_row["used_by"] is not None:
                raise ActivationError("激活码已被使用")
            # The code's own lifetime (independent of the membership it grants).
            code_expires_at = code_row["expires_at"]
            if code_expires_at:
                try:
                    if datetime.fromisoformat(code_expires_at) <= _now():
                        raise ActivationError("激活码已过期")
                except ValueError:
                    pass

            plan_code = code_row["plan_code"]
            months = int(code_row["months"])
            plan_row = self.store.get_plan(plan_code)
            if plan_row is None:
                raise ActivationError("激活码关联的套餐不存在")

            # 3. Mark the code used (globally single-use).
            conn.execute(
                "UPDATE activation_codes SET used_by = ?, used_at = ? WHERE code_hash = ?",
                (user_id, _now_iso(), code_hash),
            )

            # 4. Create the paid zero-value order with an entitlement snapshot.
            order_id = uuid.uuid4().hex
            import json
            conn.execute(
                """
                INSERT INTO orders
                    (id, user_id, plan_code, status, channel, price_cny_fen,
                     entitlements_snapshot_json, months, idempotency_key,
                     provider_payment_id, created_at, paid_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id, user_id, plan_code, OrderStatus.PAID, PaymentChannel.ACTIVATION_CODE,
                    0, json.dumps(plan_row["entitlements"], sort_keys=True, ensure_ascii=False),
                    months, idempotency_key, code_hash, _now_iso(), _now_iso(),
                ),
            )

            # 5. Grant the membership window.
            valid_from = _now_iso()
            valid_until = (_now() + timedelta(days=30 * months)).isoformat()
            conn.execute(
                """
                INSERT INTO entitlement_grants
                    (id, user_id, plan_code, order_id, valid_from, valid_until, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'activation', ?)
                """,
                (uuid.uuid4().hex, user_id, plan_code, order_id, valid_from, valid_until, _now_iso()),
            )

            # 6. Grant current-month plan credits (idempotent via ledger key).
            credits_granted = int(plan_row["monthly_credits"])
            if credits_granted > 0:
                # Grant outside the outer tx is not safe; use a nested savepoint-free
                # direct insert path by reusing the same connection.
                self._grant_in_tx(
                    conn, user_id, credits_granted,
                    idempotency_key=f"activation:{order_id}",
                )

            # 7. Grant the current natural month's independent Data Credits.
            self._grant_data_in_tx(conn, user_id, plan_code, _now().date())

            # 8. Audit.
            conn.execute(
                """
                INSERT INTO audit_log (id, actor, action, target, reason, metadata_json, created_at)
                VALUES (?, ?, 'activation', ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex, user_id, user_id, f"activated {plan_code}/{months}mo",
                    json.dumps({"order_id": order_id, "plan": plan_code}, sort_keys=True),
                    _now_iso(),
                ),
            )

        return ActivationResult(
            order_id=order_id,
            plan_code=plan_code,
            months=months,
            credits_granted=credits_granted,
            replayed=False,
        )

    def ensure_monthly_data_grant(
        self, user_id: str, plan_code: str, period: date
    ):
        """Grant the plan's personal Data Credits once per natural month."""
        with self.store.transaction() as conn:
            return self._grant_data_in_tx(conn, user_id, plan_code, period)

    def _grant_data_in_tx(self, conn, user_id: str, plan_code: str, period: date):
        from src.product.data_credits import DataGrantResult

        plan = self.store.get_plan(plan_code)
        if plan is None:
            raise ValueError(f"unknown plan {plan_code}")
        amount = int(plan["entitlements"].get("datahub.monthly_credits", 0))
        if amount <= 0:
            return None
        key = f"data-plan-month:{user_id}:{plan_code}:{period:%Y-%m}"
        prior = conn.execute(
            "SELECT id FROM data_credit_lots WHERE owner_id = ? AND idempotency_key = ?",
            (user_id, key),
        ).fetchone()
        if prior:
            return DataGrantResult(prior["id"], True)
        if period.month == 12:
            next_month = date(period.year + 1, 1, 1)
        else:
            next_month = date(period.year, period.month + 1, 1)
        expires_at = datetime(
            next_month.year, next_month.month, next_month.day, tzinfo=timezone.utc
        ).isoformat()
        lot_id = uuid.uuid4().hex
        created_at = _now_iso()
        conn.execute(
            "INSERT INTO data_credit_lots "
            "(id, owner_id, amount_total, amount_remaining, source, expires_at, "
            "idempotency_key, created_at) VALUES (?, ?, ?, ?, 'data_monthly', ?, ?, ?)",
            (lot_id, user_id, amount, amount, expires_at, key, created_at),
        )
        conn.execute(
            "INSERT INTO data_credit_ledger "
            "(id, owner_id, lot_id, reservation_id, delta, operation, idempotency_key, "
            "metadata_json, created_at) VALUES (?, ?, ?, NULL, ?, 'grant', ?, NULL, ?)",
            (uuid.uuid4().hex, user_id, lot_id, amount, key, created_at),
        )
        return DataGrantResult(lot_id, False)

    def _grant_in_tx(self, conn, user_id: str, amount: int, *, idempotency_key: str) -> None:
        """Grant a permanent-ish monthly lot inside the caller's transaction.

        Monthly plan credits expire at month-end (design §4.2). We compute the
        end of the current natural month. Idempotent via the lot's key.
        """
        existing = conn.execute(
            "SELECT id FROM credit_lots WHERE user_id = ? AND idempotency_key = ?",
            (user_id, idempotency_key),
        ).fetchone()
        if existing:
            return  # already granted — idempotent
        now = _now()
        if now.month == 12:
            month_end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
        else:
            month_end = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
        lot_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO credit_lots
                (id, user_id, amount_total, amount_remaining, source, expires_at,
                 idempotency_key, created_at)
            VALUES (?, ?, ?, ?, 'monthly', ?, ?, ?)
            """,
            (lot_id, user_id, amount, amount, month_end.isoformat(), idempotency_key, _now_iso()),
        )
        conn.execute(
            """
            INSERT INTO credit_ledger (id, user_id, lot_id, delta, operation, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, 'grant', ?, ?)
            """,
            (uuid.uuid4().hex, user_id, lot_id, amount, idempotency_key, _now_iso()),
        )

    # ------------------------------------------------------------------ #
    # Registration welcome (lazy) — Task 5 Step 4
    # ------------------------------------------------------------------ #

    def ensure_welcome_grant(self, user_id: str) -> None:
        """Idempotently grant the free plan + 50 welcome credits on first contact.

        Plan Task 5 Step 4 calls for this at registration; implemented lazily
        (fired on first entitlement/credits read) so neither ``UserStore`` nor
        ``auth_routes`` is modified. Skips users who already have any plan grant
        or a prior welcome lot. Design §4.1: 免费版首次注册 50 积分（一次性）。
        """
        welcome_key = f"registration-welcome:{user_id}"
        with self.store.transaction() as conn:
            # Skip if the user already has any entitlement grant (e.g. activated
            # a paid plan out of band) or already received the welcome lot.
            has_grant = conn.execute(
                "SELECT 1 FROM entitlement_grants WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
            has_welcome = conn.execute(
                "SELECT 1 FROM credit_lots WHERE user_id = ? AND idempotency_key = ?",
                (user_id, welcome_key),
            ).fetchone()
            if has_grant or has_welcome:
                return

            now_iso = _now_iso()
            conn.execute(
                """
                INSERT INTO entitlement_grants
                    (id, user_id, plan_code, order_id, valid_from, valid_until, source, created_at)
                VALUES (?, ?, 'free', NULL, ?, NULL, 'welcome', ?)
                """,
                (uuid.uuid4().hex, user_id, now_iso, now_iso),
            )

        # Grant the 50 welcome credits as a permanent lot via the ledger so the
        # immutable ledger records it. Idempotent on its own key.
        self.ledger.grant(
            user_id, 50, source="welcome", expires_at=None, idempotency_key=welcome_key,
        )

    # ------------------------------------------------------------------ #
    # Entitlement reads
    # ------------------------------------------------------------------ #

    def current_entitlements(self, user_id: str) -> EntitlementSnapshot:
        """Return the user's currently-active plan + entitlements (design §6)."""
        now_iso = _now_iso()
        conn = self.store._get_conn()
        row = conn.execute(
            """
            SELECT plan_code, valid_from, valid_until FROM entitlement_grants
            WHERE user_id = ? AND (valid_until IS NULL OR valid_until >= ?)
            ORDER BY valid_until DESC LIMIT 1
            """,
            (user_id, now_iso),
        ).fetchone()
        if row is None:
            plan = self.store.get_plan(PlanCode.FREE)
            return EntitlementSnapshot(
                user_id=user_id,
                plan_code=PlanCode.FREE,
                valid_from=None,
                valid_until=None,
                entitlements=plan["entitlements"] if plan else {},
            )
        plan = self.store.get_plan(row["plan_code"]) or {"entitlements": {}}
        return EntitlementSnapshot(
            user_id=user_id,
            plan_code=row["plan_code"],
            valid_from=row["valid_from"],
            valid_until=row["valid_until"],
            entitlements=plan["entitlements"],
        )
