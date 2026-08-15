from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.datahub_credentials import DataHubCredentialService
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def services(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._ledger = CreditLedger(store)
    pr._commerce = CommerceService(store, pr._ledger)
    pr._data_ledger = DataCreditLedger(store)
    pr._credential_service = DataHubCredentialService(store)
    yield store
    pr._store = pr._ledger = pr._commerce = pr._data_ledger = pr._credential_service = None


def test_create_lists_prefix_but_never_lists_secret_or_hash() -> None:
    created = asyncio.run(
        pr.create_datahub_credential(
            pr.CreateDataHubCredentialRequest(
                name="研究脚本", scopes=["health"], ip_allowlist=[], expires_at=None
            ),
            user={"id": "u1"},
        )
    )
    assert created.plaintext.startswith("sxd_live_")
    listed = asyncio.run(pr.list_datahub_credentials(user={"id": "u1"}))
    assert len(listed.items) == 1
    assert listed.items[0].key_prefix == created.key_prefix
    dumped = listed.model_dump_json()
    assert created.plaintext not in dumped
    assert "key_hash" not in dumped


def test_credential_routes_are_owner_isolated() -> None:
    created = asyncio.run(
        pr.create_datahub_credential(
            pr.CreateDataHubCredentialRequest(
                name="u1", scopes=["health"], ip_allowlist=[], expires_at=None
            ),
            user={"id": "u1"},
        )
    )
    assert asyncio.run(pr.list_datahub_credentials(user={"id": "u2"})).items == []
    with pytest.raises(pr.HTTPException) as error:
        asyncio.run(pr.revoke_datahub_credential(created.id, user={"id": "u2"}))
    assert error.value.status_code == 404


def test_rotate_returns_new_one_time_secret_and_revokes_old() -> None:
    created = asyncio.run(
        pr.create_datahub_credential(
            pr.CreateDataHubCredentialRequest(
                name="rotate", scopes=["health"], ip_allowlist=[], expires_at=None
            ),
            user={"id": "u1"},
        )
    )
    rotated = asyncio.run(pr.rotate_datahub_credential(created.id, user={"id": "u1"}))
    assert rotated.id != created.id
    assert rotated.plaintext != created.plaintext
    listed = asyncio.run(pr.list_datahub_credentials(user={"id": "u1"}))
    assert len([item for item in listed.items if item.revoked_at is None]) == 1


def test_usage_is_aggregated_for_current_user_only(services: ProductStore) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = services._get_conn()
    rows = [
        ("r1", "u1", "k1", "stocks.daily", 200, 100, 80, 12, 5, 10, None, now),
        ("r2", "u1", "k1", "stocks.daily", 500, 100, 0, 12, 0, 10, "http_500", now),
        ("r3", "u2", "k2", "health", 200, 0, 0, 0, 0, 1, None, now),
    ]
    conn.executemany(
        "INSERT INTO datahub_request_usage "
        "(request_id,user_id,credential_id,endpoint_code,status_code,requested_units,"
        "actual_units,credits_authorized,credits_charged,duration_ms,error_code,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    usage = asyncio.run(pr.datahub_usage(user={"id": "u1"}))
    assert usage.total_requests == 2
    assert usage.successful_requests == 1
    assert usage.credits_charged == 5
    assert [(item.endpoint_code, item.requests) for item in usage.by_endpoint] == [
        ("stocks.daily", 2)
    ]


def test_legacy_usage_route_is_not_registered() -> None:
    assert all(route.path != "/api/usage/me" for route in pr._router.routes)
