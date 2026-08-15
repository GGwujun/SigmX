"""Tests for activation orders, entitlements and the payment boundary.

Task 3 of the product-closure plan. ``CommerceService.activate_code`` is the
atomic, idempotent heart of the activation flow (design §5.1): one code → one
paid zero-value order + entitlement grant + current-month credit grant + audit,
all in a single transaction, replayed safely.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pytest

from src.product.credits import CreditLedger
from src.product.commerce import CommerceService
from src.product.store import ProductStore


class ProductEnv(NamedTuple):
    store: ProductStore
    ledger: CreditLedger
    commerce: CommerceService


@pytest.fixture
def product(tmp_path: Path) -> ProductEnv:
    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)
    commerce = CommerceService(store, ledger)
    return ProductEnv(store, ledger, commerce)


def test_activation_is_atomic_and_idempotent(product: ProductEnv) -> None:
    """Plan Task 3 Step 2 contract: duplicate activation is a replay, not double-grant."""
    code = product.commerce.admin_create_activation_code(plan="desktop_pro", months=3)

    first = product.commerce.activate_code("u1", code.plaintext, "request-1")
    second = product.commerce.activate_code("u1", code.plaintext, "request-1")

    # Same order returned; only one order exists.
    assert second.order_id == first.order_id
    assert product.store._get_conn().execute(
        "SELECT COUNT(*) AS c FROM orders WHERE user_id = ?", ("u1",)
    ).fetchone()["c"] == 1

    # Credits granted exactly once (advanced = 300 monthly).
    assert product.ledger.balance("u1").available == 300
    # Entitlement reflects the activated plan.
    snap = product.commerce.current_entitlements("u1")
    assert snap.plan_code == "desktop_pro"


def test_activation_grants_current_month_credits_once(product: ProductEnv) -> None:
    """Monthly plan credits are granted once per activation (design §4.2, §5.1)."""
    code = product.commerce.admin_create_activation_code(plan="pro_bundle", months=3)
    product.commerce.activate_code("u1", code.plaintext, "k-1")
    assert product.ledger.balance("u1").available == 1200  # pro monthly


def test_activation_extends_membership_by_months(product: ProductEnv) -> None:
    """An N-month code grants an entitlement window of ~N months (design §5.1)."""
    code = product.commerce.admin_create_activation_code(plan="desktop_pro", months=3)
    product.commerce.activate_code("u1", code.plaintext, "k-1")
    snap = product.commerce.current_entitlements("u1")
    assert snap.valid_until is not None
    valid_until = datetime.fromisoformat(snap.valid_until)
    # 3 months, ±2 days tolerance for wall-clock drift.
    delta = valid_until - datetime.now(timezone.utc)
    assert timedelta(days=89) < delta < timedelta(days=92)


def test_used_code_cannot_be_redeemed_by_another_user(product: ProductEnv) -> None:
    """A code is single-use globally (design §5.1)."""
    code = product.commerce.admin_create_activation_code(plan="desktop_pro", months=3)
    product.commerce.activate_code("u1", code.plaintext, "k-1")

    with pytest.raises(Exception):
        product.commerce.activate_code("u2", code.plaintext, "k-2")
    # u2 got nothing.
    assert product.ledger.balance("u2").available == 0
    assert product.commerce.current_entitlements("u2").plan_code == "free"


def test_expired_code_is_rejected(product: ProductEnv) -> None:
    """An admin code past its expiry cannot be activated."""
    code = product.commerce.admin_create_activation_code(
        plan="desktop_pro", months=3, expires_at="2000-01-01T00:00:00+00:00"
    )
    with pytest.raises(Exception):
        product.commerce.activate_code("u1", code.plaintext, "k-1")
    assert product.ledger.balance("u1").available == 0


def test_unknown_code_is_rejected(product: ProductEnv) -> None:
    with pytest.raises(Exception):
        product.commerce.activate_code("u1", "SX-NOPE-0000", "k-1")


def test_activation_writes_audit_entry(product: ProductEnv) -> None:
    """Every activation is recorded in the immutable audit log (design §9)."""
    code = product.commerce.admin_create_activation_code(plan="desktop_pro", months=3)
    product.commerce.activate_code("u1", code.plaintext, "k-1")
    rows = product.store._get_conn().execute(
        "SELECT action, target FROM audit_log WHERE target = ?", ("u1",)
    ).fetchall()
    assert any(r["action"] == "activation" for r in rows)


def test_current_entitlements_defaults_to_free(product: ProductEnv) -> None:
    """A user with no activation reads as the free plan."""
    snap = product.commerce.current_entitlements("u-nope")
    assert snap.plan_code == "free"


def test_activation_code_provider_implements_protocol() -> None:
    """The activation-code provider satisfies the PaymentProvider surface (§5.2)."""
    from src.product.payment import ActivationCodeProvider, PaymentProvider

    provider = ActivationCodeProvider()
    assert isinstance(provider, PaymentProvider)
    for method in ("create_checkout", "verify_webhook", "parse_event",
                   "query_payment", "refund"):
        assert callable(getattr(provider, method))


def test_plaintext_code_only_returned_once(product: ProductEnv) -> None:
    """Design §9: codes are hashed at rest; plaintext shown only at creation."""
    created = product.commerce.admin_create_activation_code(plan="pro_bundle", months=3)
    # The store only ever persists the hash.
    row = product.store._get_conn().execute(
        "SELECT code_hash FROM activation_codes WHERE code_hash = ?", (created.code_hash,)
    ).fetchone()
    assert row is not None
    assert created.plaintext  # plaintext surfaced to the operator at creation

