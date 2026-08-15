"""Route-level tests for product_routes — Task 5.

These bypass the HTTP layer (TestClient is broken in this environment — a
version mismatch between httpx/starlette, tracked separately). Instead they
drive the catalog read path directly and assert the response models serialize
the domain layer correctly. The auth-gated handlers are thin wrappers over the
already-tested domain services (Tasks 1-4), so the high-value assertion here is
that wiring + serialization is correct.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProductStore:
    """Point the route module's lazy singletons at a throwaway db."""
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger
    from src.product.devices import DeviceService

    store = ProductStore(tmp_path / "product.db")
    # Pre-build the singletons so the lazy getters all share this db.
    pr._store = store
    pr._ledger = CreditLedger(store)
    pr._commerce = CommerceService(store, pr._ledger)
    pr._devices = DeviceService(store)

    yield store

    # Reset so other tests don't see this process-wide singleton.
    pr._store = None
    pr._ledger = None
    pr._commerce = None
    pr._devices = None


def test_catalog_endpoint_serializes_personal_plans_only() -> None:
    """GET /api/catalog/plans returns only canonical personal plans."""
    result = asyncio.run(pr.list_plans())
    codes = {p.code for p in result.plans}
    assert codes == {"free", "desktop_pro", "data_developer", "pro_bundle"}
    developer = next(p for p in result.plans if p.code == "data_developer")
    assert developer.price_cny_fen == 19800
    assert developer.entitlements["datahub.monthly_credits"] == 100_000
    assert developer.entitlements["desktop.connected_mode"] is False


def test_my_entitlements_defaults_to_free_for_ungranted_user() -> None:
    """GET /api/entitlements/me reads free for a user with no activation."""
    snap = asyncio.run(pr.my_entitlements(user={"id": "u-new"}))
    assert snap.plan_code == "free"
    assert snap.entitlements["datahub.enabled"] is True


def test_my_credits_seeds_welcome_on_first_read() -> None:
    """GET /api/credits/me lazily grants the 50 welcome credits on first contact."""
    bal = asyncio.run(pr.my_credits(user={"id": "u-new"}))
    assert bal.available == 50  # one-time welcome grant (Task 5 Step 4, lazy)
    assert bal.expiring_soon == 0  # welcome lot is permanent


def test_activate_then_read_back_flow() -> None:
    """The full activate→entitlements→credits happy path through the route layer."""
    # Admin creates a code.
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger
    commerce = CommerceService(pr._get_store(), CreditLedger(pr._get_store()))
    created = commerce.admin_create_activation_code(plan="desktop_pro", months=3)

    # User activates via the route handler (no TestClient — direct call).
    resp = asyncio.run(pr.activate_order(
        body=pr.ActivateRequest(code=created.plaintext, idempotency_key="k-1"),
        user={"id": "u1"},
    ))
    assert resp.plan_code == "desktop_pro"
    assert resp.credits_granted == 300
    assert resp.replayed is False

    # Entitlements now reflect advanced; credits read 300.
    snap = asyncio.run(pr.my_entitlements(user={"id": "u1"}))
    assert snap.plan_code == "desktop_pro"
    bal = asyncio.run(pr.my_credits(user={"id": "u1"}))
    assert bal.available == 300

    # Replaying the same idempotency key does not double-grant.
    resp2 = asyncio.run(pr.activate_order(
        body=pr.ActivateRequest(code=created.plaintext, idempotency_key="k-1"),
        user={"id": "u1"},
    ))
    assert resp2.replayed is True
    assert resp2.order_id == resp.order_id
    assert asyncio.run(pr.my_credits(user={"id": "u1"})).available == 300


def test_activate_rejects_bad_code_with_400() -> None:
    """An unknown code surfaces as an ActivationError → 400 in the real handler."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(pr.activate_order(
            body=pr.ActivateRequest(code="SX-NOPE-0000", idempotency_key="k-x"),
            user={"id": "u1"},
        ))
    assert exc.value.status_code == 400


def test_my_credits_lots_lists_batches_after_activation() -> None:
    """GET /api/credits/lots returns the user's credit lots with expiry info."""
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger

    commerce = CommerceService(pr._get_store(), CreditLedger(pr._get_store()))
    created = commerce.admin_create_activation_code(plan="pro_bundle", months=3)
    asyncio.run(pr.activate_order(
        body=pr.ActivateRequest(code=created.plaintext, idempotency_key="k-lots"),
        user={"id": "u1"},
    ))

    lots = asyncio.run(pr.my_credits_lots(user={"id": "u1"}))
    assert len(lots.lots) == 1
    lot = lots.lots[0]
    assert lot.amount_total == 1200           # pro monthly
    assert lot.amount_remaining == 1200
    assert lot.source == "monthly"
    assert lot.expires_at is not None          # monthly lots expire at month-end

    # New user has no lots.
    empty = asyncio.run(pr.my_credits_lots(user={"id": "nobody"}))
    assert empty.lots == []


def test_my_credits_ledger_records_grant_and_consume() -> None:
    """GET /api/credits/ledger returns the immutable ledger entries."""
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger

    store = pr._get_store()
    ledger = CreditLedger(store)
    commerce = CommerceService(store, ledger)
    code = commerce.admin_create_activation_code(plan="desktop_pro", months=3)
    asyncio.run(pr.activate_order(
        body=pr.ActivateRequest(code=code.plaintext, idempotency_key="k-ledger"),
        user={"id": "u2"},
    ))
    # Consume some credits through the ledger directly.
    res = ledger.reserve("u2", 50, operation="alpha", idempotency_key="run-1")
    ledger.settle(res.reservation_id, idempotency_key="run-1")

    entries = asyncio.run(pr.my_credits_ledger(user={"id": "u2"}))
    operations = [e.operation for e in entries.entries]
    assert "grant" in operations       # the activation monthly grant
    assert "reserve" in operations     # the AlphaForge reservation
    assert "settle" in operations      # the settlement

