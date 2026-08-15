import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import src.api.product_routes as product_routes

from src.product.datahub_credentials import (
    CredentialLimitReached,
    CredentialRevoked,
    DataHubCredentialService,
)
from src.product.store import ProductStore


def test_desktop_session_is_device_bound_short_lived_and_rotated(tmp_path):
    now = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)
    service = DataHubCredentialService(
        ProductStore(tmp_path / "product.db"), now=lambda: now
    )

    first = service.create_desktop_session(
        "user-1", "device-1", ["group:market", "group:fundamentals"]
    )
    second = service.create_desktop_session(
        "user-1", "device-1", ["group:market"]
    )

    assert first.plaintext.startswith("sxd_live_")
    assert datetime.fromisoformat(first.expires_at) == now + timedelta(hours=24)
    with pytest.raises(CredentialRevoked):
        service.authenticate(first.plaintext, "127.0.0.1")
    assert service.authenticate(second.plaintext, "127.0.0.1").scopes == (
        "group:market",
    )


def test_desktop_session_does_not_consume_personal_key_limit(tmp_path):
    service = DataHubCredentialService(ProductStore(tmp_path / "product.db"))
    for index in range(10):
        service.create("user-1", f"key-{index}", ["group:market"], [], None)

    session = service.create_desktop_session(
        "user-1", "device-1", ["group:market"]
    )

    assert service.authenticate(session.plaintext, "127.0.0.1").user_id == "user-1"
    with pytest.raises(CredentialLimitReached):
        service.create("user-1", "key-11", ["group:market"], [], None)
    assert len(service.list("user-1")) == 10


def test_desktop_session_route_requires_owned_active_device_and_plan_scopes(tmp_path):
    store = ProductStore(tmp_path / "route.db")
    store._get_conn().execute(
        "INSERT INTO devices (id, user_id, name, fingerprint_hash, created_at, revoked_at) "
        "VALUES ('device-1', 'user-1', 'Laptop', 'hash', ?, NULL)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    store._get_conn().commit()
    product_routes._store = store
    product_routes._commerce = None
    product_routes._ledger = None
    product_routes._credential_service = None

    response = asyncio.run(
        product_routes.create_desktop_datahub_session(
            product_routes.CreateDesktopDataHubSessionRequest(device_id="device-1"),
            user={"id": "user-1"},
        )
    )

    assert response.scopes == ["group:basic.v1"]
    assert response.plaintext.startswith("sxd_live_")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            product_routes.create_desktop_datahub_session(
                product_routes.CreateDesktopDataHubSessionRequest(device_id="device-1"),
                user={"id": "other-user"},
            )
        )
    assert exc.value.status_code == 404
