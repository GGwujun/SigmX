"""Tests for Data Hub product-token authentication — Task 6.

Design §6 + plan Task 6: Data Hub accepts either a legacy ``sx_`` API key or a
short-lived product access token (issued by the device flow, Task 4). Both are
normalized to a ``DataHubPrincipal``; product quotas come from the plan's
``datahub.daily_quota`` entitlement, enforced atomically against ``usage_daily``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pytest

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.datahub_auth import (
    DataHubPrincipal,
    acquire_product_quota,
    resolve_product_principal,
)
from src.product.devices import DeviceService
from src.product.tokens import create_product_token, verify_product_token
from src.product.store import ProductStore


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def iso(self) -> str:
        return self.now.isoformat()

    def advance(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


class FakeRequest:
    """Minimal stand-in for starlette.Request — only headers + client are read."""

    def __init__(self, headers: dict[str, str] | None = None, auth: str | None = None) -> None:
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        if auth is not None:
            self.headers["authorization"] = auth
        # Pretend non-loopback so the data-hub gate applies.
        self.client = type("C", (), {"host": "203.0.113.7"})()


class Env(NamedTuple):
    store: ProductStore
    ledger: CreditLedger
    commerce: CommerceService
    devices: DeviceService
    clock: FakeClock


@pytest.fixture
def env(tmp_path: Path) -> Env:
    store = ProductStore(tmp_path / "product.db")
    clock = FakeClock()
    ledger = CreditLedger(store, now=clock.iso)
    commerce = CommerceService(store, ledger)
    devices = DeviceService(store, now=clock)
    return Env(store, ledger, commerce, devices, clock)


def _activate_and_link(env: Env, user_id: str, plan: str) -> str:
    """Grant a plan + complete the device flow; return a product access token.

    Paid plans go through activation; free is granted directly (free has no
    activation code — it is the default tier).
    """
    if plan == "free":
        env.store._get_conn().execute(
            "INSERT INTO entitlement_grants (id,user_id,plan_code,order_id,valid_from,valid_until,source,created_at) "
            "VALUES (?,?,?,?,?,NULL,'test',?)",
            (f"g-{user_id}", user_id, "free", None, env.clock.iso(), env.clock.iso()),
        )
        env.store._get_conn().commit()
    else:
        code = env.commerce.admin_create_activation_code(plan=plan, months=3)
        env.commerce.activate_code(user_id, code.plaintext, f"k-{user_id}")
    started = env.devices.start(device_name=f"desk-{user_id}", fingerprint_hash="fp")
    env.devices.approve(user_id=user_id, user_code=started.user_code)
    result = env.devices.poll(device_code=started.device_code)
    assert result.status.value == "approved"
    return result.access_token


def test_valid_product_token_resolves_to_principal(env: Env) -> None:
    """An advanced-plan product token resolves to a DataHubPrincipal."""
    token = _activate_and_link(env, "u1", "advanced")
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    assert principal is not None
    assert principal.source == "product_token"
    assert principal.plan == "advanced"
    assert principal.quota_daily == 1000
    assert principal.subject == "u1"


def test_free_plan_token_has_basic_quota(env: Env) -> None:
    """A free user's token resolves but with the free-tier daily quota."""
    # No activation → free plan via current_entitlements default; still need a device.
    env.store._get_conn().execute(
        "INSERT INTO entitlement_grants (id,user_id,plan_code,order_id,valid_from,valid_until,source,created_at) "
        "VALUES (?,?,?,?,?,NULL,'test',?)",
        ("g1", "u1", "free", None, env.clock.iso(), env.clock.iso()),
    )
    env.store._get_conn().commit()
    started = env.devices.start(device_name="d", fingerprint_hash="fp")
    env.devices.approve(user_id="u1", user_code=started.user_code)
    token = env.devices.poll(device_code=started.device_code).access_token

    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    assert principal is not None
    assert principal.plan == "free"
    assert principal.quota_daily == 100
    assert principal.featured is False


def test_pro_plan_token_has_featured_access(env: Env) -> None:
    """Pro plan grants featured-data entitlement (design §6)."""
    token = _activate_and_link(env, "u1", "pro")
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    assert principal is not None
    assert principal.featured is True
    assert principal.quota_daily == 10000


def test_no_bearer_header_returns_none(env: Env) -> None:
    """No Authorization header → no product principal (legacy API-key path takes over)."""
    assert resolve_product_principal(FakeRequest(), env.store) is None


def test_non_product_audience_token_returns_none(env: Env) -> None:
    """A web-session JWT (wrong audience) is not a Data Hub principal."""
    from src.auth.jwt_utils import create_token

    web_token = create_token("u1", "u1@example.com")
    assert resolve_product_principal(FakeRequest(auth=f"Bearer {web_token}"), env.store) is None


def test_revoked_device_token_rejected(env: Env) -> None:
    """A token whose device was revoked must not resolve."""
    token = _activate_and_link(env, "u1", "advanced")
    claims = verify_product_token(token)
    env.devices.revoke(user_id="u1", device_id=claims["device_id"])
    assert resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store) is None


def test_expired_entitlement_token_rejected(env: Env) -> None:
    """A token whose plan window has passed must not resolve."""
    token = _activate_and_link(env, "u1", "advanced")
    env.clock.advance(days=95)  # past the 3-month window
    assert resolve_product_principal(
        FakeRequest(auth=f"Bearer {token}"), env.store, now=env.clock()
    ) is None


def test_product_quota_enforced_atomically(env: Env) -> None:
    """acquire_product_quota returns True up to quota, then False (429 path)."""
    token = _activate_and_link(env, "u1", "free")  # quota = 100
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    assert principal is not None

    for _ in range(100):
        assert acquire_product_quota(env.store, principal) is True
    # 101st request is rejected.
    assert acquire_product_quota(env.store, principal) is False


def test_quota_resets_per_day(env: Env) -> None:
    """usage_daily is keyed by day — a new day resets the counter."""
    token = _activate_and_link(env, "u1", "free")
    principal = resolve_product_principal(FakeRequest(auth=f"Bearer {token}"), env.store)
    for _ in range(100):
        acquire_product_quota(env.store, principal)
    assert acquire_product_quota(env.store, principal) is False

    env.clock.advance(days=1)  # next day
    assert acquire_product_quota(env.store, principal, now=env.clock()) is True
