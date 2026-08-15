"""Tests for the lazy welcome-grant — Task 5 Step 4 (deferred, now done lazily).

A new user gets the free plan + a one-time 50-credit welcome lot on first contact
with the product surface (design §4.1: 免费版 首次注册 50 积分). Implemented as a
lazy, idempotent grant rather than wired into registration, so neither
``UserStore`` nor ``auth_routes`` is touched: the grant fires the first time the
user reads entitlements/credits, and never again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.store import ProductStore


@pytest.fixture
def commerce(tmp_path: Path) -> CommerceService:
    store = ProductStore(tmp_path / "product.db")
    ledger = CreditLedger(store)
    return CommerceService(store, ledger)


def test_new_user_gets_welcome_grant_on_first_contact(commerce: CommerceService) -> None:
    """ensure_welcome_grant seeds free plan + 50 permanent credits for a new user."""
    # Before: nothing.
    assert commerce.current_entitlements("u-new").plan_code == "free"  # default, no grant row yet
    assert commerce.ledger.balance("u-new").available == 0

    commerce.ensure_welcome_grant("u-new")

    # After: free entitlement granted + 50 welcome credits (permanent).
    snap = commerce.current_entitlements("u-new")
    assert snap.plan_code == "free"
    assert snap.valid_from is not None  # a real grant row now exists
    assert commerce.ledger.balance("u-new").available == 50
    # The welcome lot is permanent (design §4.2: 首次注册积分不随月度过期)。
    lots = commerce.ledger.list_lots("u-new")
    assert len(lots) == 1
    assert lots[0].get("expires_at") is None
    assert lots[0]["idempotency_key"] == "registration-welcome:u-new"


def test_welcome_grant_is_idempotent(commerce: CommerceService) -> None:
    """Calling ensure_welcome_grant twice does not double-grant."""
    commerce.ensure_welcome_grant("u1")
    commerce.ensure_welcome_grant("u1")
    commerce.ensure_welcome_grant("u1")

    assert commerce.ledger.balance("u1").available == 50
    assert len(commerce.ledger.list_lots("u1")) == 1


def test_user_with_existing_plan_does_not_get_welcome_grant(commerce: CommerceService) -> None:
    """A user who activated a paid plan must not also receive the free welcome grant."""
    code = commerce.admin_create_activation_code(plan="desktop_pro", months=3)
    commerce.activate_code("u1", code.plaintext, "k-1")
    assert commerce.ledger.balance("u1").available == 300  # advanced monthly only

    commerce.ensure_welcome_grant("u1")

    # Still 300 — no welcome grant added on top of a paid plan.
    assert commerce.ledger.balance("u1").available == 300
    # No welcome lot created.
    assert all(
        lot.get("idempotency_key") != "registration-welcome:u1"
        for lot in commerce.ledger.list_lots("u1")
    )


def test_welcome_grant_then_activation_stacks_credits(commerce: CommerceService) -> None:
    """Welcome credits persist when the user later activates a paid plan."""
    commerce.ensure_welcome_grant("u1")
    assert commerce.ledger.balance("u1").available == 50

    code = commerce.admin_create_activation_code(plan="pro_bundle", months=3)
    commerce.activate_code("u1", code.plaintext, "k-1")

    # 50 welcome (permanent) + 1200 pro monthly.
    assert commerce.ledger.balance("u1").available == 1250

