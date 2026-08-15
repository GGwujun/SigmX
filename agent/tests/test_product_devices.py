"""Tests for device-code authorization and product tokens — Task 4.

Design §3.1: a desktop links its cloud account through an RFC-8628-style device
flow — the client gets a device_code + human user_code, the user approves in a
browser, the client polls and receives short-lived product access + refresh
tokens. Refresh tokens are hashed, rotated, revocable, and bound by the plan's
device limit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pytest

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.devices import (
    DeviceLimitReached,
    DeviceService,
    PollStatus,
)
from src.product.store import ProductStore
from src.product.tokens import (
    PRODUCT_AUDIENCE,
    create_product_token,
    verify_product_token,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def iso(self) -> str:
        return self.now.isoformat()

    def advance(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


class Env(NamedTuple):
    store: ProductStore
    devices: DeviceService
    clock: FakeClock


@pytest.fixture
def env(tmp_path: Path) -> Env:
    store = ProductStore(tmp_path / "product.db")
    clock = FakeClock()
    devices = DeviceService(store, now=clock)
    return Env(store, devices, clock)


def _grant_free(env: Env, user_id: str) -> None:
    """Give a user a free entitlement so the device limit (1) applies."""
    env.store._get_conn().execute(
        "INSERT INTO entitlement_grants "
        "(id, user_id, plan_code, order_id, valid_from, valid_until, source, created_at) "
        "VALUES (?, ?, 'free', NULL, ?, NULL, 'test', ?)",
        (user_id, user_id, env.clock.iso(), env.clock.iso()),
    )
    env.store._get_conn().commit()


def authorize(env: Env, user_id: str, device_name: str) -> tuple[str, str]:
    """Drive the full device flow for one device; return (access, refresh)."""
    started = env.devices.start(device_name=device_name, fingerprint_hash="fp-" + device_name)
    env.devices.approve(user_id=user_id, user_code=started.user_code)
    result = env.devices.poll(device_code=started.device_code)
    assert result.status == PollStatus.APPROVED
    return result.access_token, result.refresh_token


def test_device_flow_pending_then_approved(env: Env) -> None:
    """Before approval, poll returns PENDING; after, it returns tokens."""
    _grant_free(env, "u1")
    started = env.devices.start(device_name="desktop-a", fingerprint_hash="fp-a")

    pending = env.devices.poll(device_code=started.device_code)
    assert pending.status == PollStatus.PENDING

    env.devices.approve(user_id="u1", user_code=started.user_code)
    result = env.devices.poll(device_code=started.device_code)
    assert result.status == PollStatus.APPROVED
    assert result.access_token
    assert result.refresh_token


def test_device_limit_blocks_extra_device(env: Env) -> None:
    """Plan Task 4 Step 2 contract: free plan device_limit=1 blocks a 2nd device."""
    _grant_free(env, "u1")
    authorize(env, "u1", "desktop-a")

    started = env.devices.start(device_name="desktop-b", fingerprint_hash="fp-b")
    with pytest.raises(DeviceLimitReached):
        env.devices.approve(user_id="u1", user_code=started.user_code)


def test_data_developer_does_not_unlock_desktop(env: Env) -> None:
    env.store._get_conn().execute(
        "INSERT INTO entitlement_grants "
        "(id, user_id, plan_code, order_id, valid_from, valid_until, source, created_at) "
        "VALUES (?, ?, 'data_developer', NULL, ?, NULL, 'test', ?)",
        ("grant-data", "u-data", env.clock.iso(), env.clock.iso()),
    )
    env.store._get_conn().commit()
    started = env.devices.start(device_name="desktop-a", fingerprint_hash="fp-data")
    with pytest.raises(DeviceLimitReached):
        env.devices.approve(user_id="u-data", user_code=started.user_code)


def test_revoked_device_refresh_fails(env: Env) -> None:
    """Plan Task 4 Step 2: after revoke, the refresh token is dead."""
    _grant_free(env, "u1")
    access, refresh = authorize(env, "u1", "desktop-a")

    device_id = verify_product_token(access)["device_id"]
    env.devices.revoke(user_id="u1", device_id=device_id)

    result = env.devices.refresh(refresh_token=refresh)
    assert result.status == "revoked"


def test_refresh_rotates_token_and_is_idempotent_only_once(env: Env) -> None:
    """A successful refresh issues a new refresh token; the old one is invalid."""
    _grant_free(env, "u1")
    _access, refresh = authorize(env, "u1", "desktop-a")

    first = env.devices.refresh(refresh_token=refresh)
    assert first.status == "ok"
    assert first.refresh_token and first.refresh_token != refresh

    # Old refresh token no longer works (rotated).
    replay = env.devices.refresh(refresh_token=refresh)
    assert replay.status == "revoked"


def test_device_code_expires(env: Env) -> None:
    """A device_code that is not approved within its lifetime expires."""
    started = env.devices.start(device_name="desktop-a", fingerprint_hash="fp-a")
    env.clock.advance(minutes=11)  # past the 10-minute window
    result = env.devices.poll(device_code=started.device_code)
    assert result.status == PollStatus.EXPIRED


def test_approval_is_one_time(env: Env) -> None:
    """A device_code can be consumed once; a second poll after grant is expired/denied."""
    _grant_free(env, "u1")
    started = env.devices.start(device_name="desktop-a", fingerprint_hash="fp-a")
    env.devices.approve(user_id="u1", user_code=started.user_code)

    first = env.devices.poll(device_code=started.device_code)
    assert first.status == PollStatus.APPROVED

    second = env.devices.poll(device_code=started.device_code)
    assert second.status == PollStatus.EXPIRED  # already consumed


def test_product_token_has_required_claims(env: Env) -> None:
    """Access token carries sub/aud/exp/device_id/plan/jti (plan Task 4 Step 4)."""
    _grant_free(env, "u1")
    access, _refresh = authorize(env, "u1", "desktop-a")

    claims = verify_product_token(access)
    assert claims["sub"] == "u1"
    assert claims["aud"] == PRODUCT_AUDIENCE
    assert claims["device_id"]
    assert claims["plan"] == "free"
    assert claims["jti"]
    assert claims["exp"] > 0


def test_wrong_audience_token_rejected() -> None:
    """A web-session JWT (no audience) must not pass as a product token."""
    from src.auth.jwt_utils import create_token

    web_token = create_token("u1", "u1@example.com")
    assert verify_product_token(web_token) is None


def test_tampered_token_rejected(env: Env) -> None:
    _grant_free(env, "u1")
    access, _refresh = authorize(env, "u1", "desktop-a")
    # Flip the last character — signature no longer matches.
    tampered = access[:-1] + ("A" if access[-1] != "A" else "B")
    assert verify_product_token(tampered) is None
