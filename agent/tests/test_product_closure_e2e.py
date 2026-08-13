"""End-to-end product-closure verification — Task 10.

Drives the full loop across domain + route layers (TestClient is broken in this
env, so we call handlers/services directly — the same code path an HTTP request
takes, minus the socket). This is the design §11 acceptance path:

    new user → welcome grant → activate plan → device authorize → Data Hub
    principal → quota → metered AlphaForge charge → failure refund-once.

Plus migration / duplicate-activation / revocation-degradation cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.credits import CreditLedger
from src.product.datahub_auth import acquire_product_quota, resolve_product_principal
from src.product.store import ProductStore


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def iso(self) -> str:
        return self.now.isoformat()


@pytest.fixture
def env(tmp_path: Path):
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger
    from src.product.devices import DeviceService

    store = ProductStore(tmp_path / "product.db")
    clock = FakeClock()
    ledger = CreditLedger(store, now=clock.iso)
    commerce = CommerceService(store, ledger)
    devices = DeviceService(store, now=clock)
    # Wire the route module's singletons so handlers share this db.
    pr._store = store
    pr._ledger = ledger
    pr._commerce = commerce
    pr._devices = devices
    yield type("E", (), dict(store=store, ledger=ledger, commerce=commerce,
                             devices=devices, clock=clock))
    pr._store = pr._ledger = pr._commerce = pr._devices = None


class FakeRequest:
    def __init__(self, auth: str | None = None) -> None:
        self.headers = {"authorization": auth} if auth else {}
        self.client = type("C", (), {"host": "203.0.113.9"})()


def test_full_product_closure_loop(env):
    """The acceptance path: register → activate → device link → Data Hub → metered."""
    user_id = "u-closure"

    # 1. New user first contact → welcome grant (free + 50 credits).
    env.commerce.ensure_welcome_grant(user_id)
    assert env.ledger.balance(user_id).available == 50

    # 2. Admin creates an activation code; user activates advanced.
    code = env.commerce.admin_create_activation_code(plan="advanced", months=3)
    result = env.commerce.activate_code(user_id, code.plaintext, "e2e-activate")
    assert result.plan_code == "advanced"
    # 50 welcome (permanent) + 300 advanced monthly.
    assert env.ledger.balance(user_id).available == 350

    # 3. Device-code flow → product access token.
    started = env.devices.start(device_name="Windows desktop", fingerprint_hash="fp")
    env.devices.approve(user_id=user_id, user_code=started.user_code)
    poll = env.devices.poll(device_code=started.device_code)
    assert poll.status.value == "approved"
    access_token = poll.access_token
    assert access_token

    # 4. The token resolves to a Data Hub principal with advanced quota (1000/day).
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {access_token}"), env.store)
    assert principal is not None
    assert principal.plan == "advanced"
    assert principal.quota_daily == 1000

    # 5. Data Hub quota is metered atomically.
    assert acquire_product_quota(env.store, principal) is True

    # 6. Metered AlphaForge: reserve 50 → settle on success.
    res = env.ledger.reserve(user_id, 50, operation="alphaforge", idempotency_key="run-e2e")
    assert dict(res.allocations)  # allocated from some lot
    env.ledger.settle(res.reservation_id, idempotency_key="run-e2e")
    assert env.ledger.balance(user_id).available == 300  # 350 − 50


def test_activation_idempotent_no_double_grant(env):
    """Replaying the same activation does not duplicate entitlements or credits."""
    code = env.commerce.admin_create_activation_code(plan="pro", months=3)
    first = env.commerce.activate_code("u1", code.plaintext, "k-1")
    second = env.commerce.activate_code("u1", code.plaintext, "k-1")
    assert second.order_id == first.order_id
    assert env.ledger.balance("u1").available == 1200  # pro monthly, once


def test_failed_task_refunds_exactly_once(env):
    """A failed metered task refunds its reservation exactly once (design §9)."""
    env.commerce.ensure_welcome_grant("u1")
    assert env.ledger.balance("u1").available == 50

    res = env.ledger.reserve("u1", 20, operation="fund_arb", idempotency_key="run-fail")
    env.ledger.refund(res.reservation_id, idempotency_key="run-fail")
    env.ledger.refund(res.reservation_id, idempotency_key="run-fail")  # replay
    assert env.ledger.balance("u1").available == 50  # restored, not doubled


def test_device_revocation_blocks_data_hub(env):
    """Revoking a device kills its Data Hub access immediately."""
    env.commerce.ensure_welcome_grant("u1")
    started = env.devices.start(device_name="d", fingerprint_hash="fp")
    env.devices.approve(user_id="u1", user_code=started.user_code)
    token = env.devices.poll(device_code=started.device_code).access_token

    # Before revoke: resolves.
    assert resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store) is not None

    # After revoke: rejected.
    claims = pr.verify_product_token(token) if hasattr(pr, "verify_product_token") else None
    # Resolve device_id from the token directly.
    from src.product.tokens import verify_product_token
    device_id = verify_product_token(token)["device_id"]
    env.devices.revoke(user_id="u1", device_id=device_id)
    assert resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store) is None


def test_legacy_balance_migration_then_activation_stacks(env):
    """A migrated legacy balance + a fresh activation stack correctly."""
    from src.credits.store import CreditStore

    legacy = CreditStore(Path(env.store.db_path).parent / "credits.db")
    legacy.add_credits("u1", 75, "admin", "seed", "t")

    from src.product.credits import migrate_legacy_balances
    migrated = migrate_legacy_balances(env.ledger, legacy)
    assert migrated == {"u1": 75}
    assert env.ledger.balance("u1").available == 75  # permanent migrated lot

    # Now activate advanced on top.
    code = env.commerce.admin_create_activation_code(plan="advanced", months=3)
    env.commerce.activate_code("u1", code.plaintext, "k-1")
    assert env.ledger.balance("u1").available == 375  # 75 legacy + 300 monthly


def test_free_quota_smaller_than_paid(env):
    """A free user's Data Hub quota (100/day) is enforced separately from paid."""
    env.commerce.ensure_welcome_grant("u-free")
    started = env.devices.start(device_name="d", fingerprint_hash="fp")
    env.devices.approve(user_id="u-free", user_code=started.user_code)
    token = env.devices.poll(device_code=started.device_code).access_token
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    assert principal is not None
    assert principal.quota_daily == 100  # free tier
    assert principal.featured is False
