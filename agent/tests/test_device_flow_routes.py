"""Route tests for the device-authorization flow — Task 9 backend.

The device flow has two actors (design §3.1):
- the desktop client, which starts the flow and polls (no user JWT — it only
  knows its device_code);
- the user, who approves in a browser (require_user JWT).

These tests drive the handlers directly (TestClient is broken in this env) to
verify wiring + idempotency + the limit/revocation contract.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

import src.api.product_routes as pr
from src.product.devices import DeviceLimitReached
from src.product.store import ProductStore


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def iso(self) -> str:
        return self.now.isoformat()

    def advance(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


@pytest.fixture
def product(tmp_path: Path) -> tuple:
    from src.product.commerce import CommerceService
    from src.product.credits import CreditLedger
    from src.product.devices import DeviceService

    store = ProductStore(tmp_path / "product.db")
    clock = FakeClock()
    ledger = CreditLedger(store, now=clock.iso)
    commerce = CommerceService(store, ledger)
    devices = DeviceService(store, now=clock)
    pr._store = store
    pr._ledger = ledger
    pr._commerce = commerce
    pr._devices = devices
    yield store, devices, clock
    pr._store = pr._ledger = pr._commerce = pr._devices = None


def _grant_free(store, clock, user_id):
    store._get_conn().execute(
        "INSERT INTO entitlement_grants (id,user_id,plan_code,order_id,valid_from,valid_until,source,created_at) "
        "VALUES (?,?,?,?,?,NULL,'test',?)",
        (f"g-{user_id}", user_id, "free", None, clock.iso(), clock.iso()),
    )
    store._get_conn().commit()


def test_device_flow_start_returns_codes(product):
    _, _, _ = product
    started = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="my-desk", fingerprint_hash="fp-1"),
    ))
    assert started.device_code
    assert started.user_code
    assert started.verification_url
    assert started.interval_seconds > 0
    assert started.expires_in_seconds > 0


def test_device_flow_poll_is_pending_before_approval(product):
    store, _, _ = product
    started = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d", fingerprint_hash="fp"),
    ))
    result = asyncio.run(pr.device_authorize_poll(
        body=pr.DeviceAuthorizePollRequest(device_code=started.device_code),
    ))
    assert result.status == "pending"
    assert result.access_token is None


def test_device_flow_approve_then_poll_returns_tokens(product):
    store, devices, _ = product
    _grant_free(store, product[2], "u1")
    started = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d", fingerprint_hash="fp"),
    ))
    # User approves in-browser.
    asyncio.run(pr.device_authorize_approve(
        body=pr.DeviceAuthorizeApproveRequest(user_code=started.user_code),
        user={"id": "u1"},
    ))
    # Desktop polls and gets tokens.
    result = asyncio.run(pr.device_authorize_poll(
        body=pr.DeviceAuthorizePollRequest(device_code=started.device_code),
    ))
    assert result.status == "approved"
    assert result.access_token
    assert result.refresh_token


def test_device_flow_poll_expired_after_window(product):
    _, _, clock = product
    started = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d", fingerprint_hash="fp"),
    ))
    clock.advance(minutes=11)  # past the 10-minute window
    result = asyncio.run(pr.device_authorize_poll(
        body=pr.DeviceAuthorizePollRequest(device_code=started.device_code),
    ))
    assert result.status == "expired"


def test_device_flow_refresh_rotates_token(product):
    store, _, clock = product
    _grant_free(store, clock, "u1")
    started = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d", fingerprint_hash="fp"),
    ))
    asyncio.run(pr.device_authorize_approve(
        body=pr.DeviceAuthorizeApproveRequest(user_code=started.user_code),
        user={"id": "u1"},
    ))
    tokens = asyncio.run(pr.device_authorize_poll(
        body=pr.DeviceAuthorizePollRequest(device_code=started.device_code),
    ))

    refreshed = asyncio.run(pr.device_token_refresh(
        body=pr.DeviceTokenRefreshRequest(refresh_token=tokens.refresh_token),
    ))
    assert refreshed.status == "ok"
    assert refreshed.access_token
    assert refreshed.refresh_token != tokens.refresh_token  # rotated

    # Old refresh token no longer works.
    replay = asyncio.run(pr.device_token_refresh(
        body=pr.DeviceTokenRefreshRequest(refresh_token=tokens.refresh_token),
    ))
    assert replay.status == "revoked"


def test_device_flow_approve_enforces_device_limit(product):
    store, _, clock = product
    _grant_free(store, clock, "u1")  # free → limit 1
    # First device.
    s1 = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d1", fingerprint_hash="fp1"),
    ))
    asyncio.run(pr.device_authorize_approve(
        body=pr.DeviceAuthorizeApproveRequest(user_code=s1.user_code), user={"id": "u1"},
    ))
    asyncio.run(pr.device_authorize_poll(body=pr.DeviceAuthorizePollRequest(device_code=s1.device_code)))
    # Second device exceeds the limit.
    s2 = asyncio.run(pr.device_authorize_start(
        body=pr.DeviceAuthorizeStartRequest(device_name="d2", fingerprint_hash="fp2"),
    ))
    with pytest.raises(Exception):
        asyncio.run(pr.device_authorize_approve(
            body=pr.DeviceAuthorizeApproveRequest(user_code=s2.user_code), user={"id": "u1"},
        ))
