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


def test_catalog_endpoint_serializes_all_four_plans() -> None:
    """GET /api/catalog/plans returns the four canonical plans with entitlements."""
    result = asyncio.run(pr.list_plans())
    codes = {p.code for p in result.plans}
    assert codes == {"free", "advanced", "pro", "enterprise"}
    advanced = next(p for p in result.plans if p.code == "advanced")
    assert advanced.price_cny_fen == 26800
    assert advanced.entitlements["datahub.daily_quota"] == 1000


def test_my_entitlements_defaults_to_free_for_ungranted_user() -> None:
    """GET /api/entitlements/me reads free for a user with no activation."""
    snap = asyncio.run(pr.my_entitlements(user={"id": "u-new"}))
    assert snap.plan_code == "free"
    assert "datahub.basic" in snap.entitlements


def test_my_credits_reads_zero_for_new_user() -> None:
    """GET /api/credits/me reads 0 for a user with no lots."""
    bal = asyncio.run(pr.my_credits(user={"id": "u-new"}))
    assert bal.available == 0
    assert bal.expiring_soon == 0


def test_activate_then_read_back_flow() -> None:
    """The full activate→entitlements→credits happy path through the route layer."""
    # Admin creates a code.
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger
    commerce = CommerceService(pr._get_store(), CreditLedger(pr._get_store()))
    created = commerce.admin_create_activation_code(plan="advanced", months=3)

    # User activates via the route handler (no TestClient — direct call).
    resp = asyncio.run(pr.activate_order(
        body=pr.ActivateRequest(code=created.plaintext, idempotency_key="k-1"),
        user={"id": "u1"},
    ))
    assert resp.plan_code == "advanced"
    assert resp.credits_granted == 300
    assert resp.replayed is False

    # Entitlements now reflect advanced; credits read 300.
    snap = asyncio.run(pr.my_entitlements(user={"id": "u1"}))
    assert snap.plan_code == "advanced"
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
