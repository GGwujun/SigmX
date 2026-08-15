"""Personal plan dataset-group and credential-scope intersection tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.datahub_credentials import DataHubCredentialService
from src.product.datahub_gateway import DatasetNotEntitled, DataHubRequestGateway, ScopeDenied
from src.product.store import ProductStore


class Request:
    def __init__(self, secret: str, query=None) -> None:
        self.headers = {"authorization": f"Bearer {secret}"}
        self.query_params = query or {}
        self.client = type("Client", (), {"host": "203.0.113.8"})()


@pytest.fixture
def env(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    commerce = CommerceService(store, CreditLedger(store))
    credentials = DataHubCredentialService(store)
    return store, commerce, credentials, DataHubRequestGateway(store)


def activate(commerce: CommerceService, user_id: str, plan: str) -> None:
    code = commerce.admin_create_activation_code(plan=plan, months=3)
    commerce.activate_code(user_id, code.plaintext, f"activate-{user_id}")


def test_advanced_can_use_market_but_not_pro_dataset(env) -> None:
    _, commerce, credentials, gateway = env
    activate(commerce, "u1", "advanced")
    key = credentials.create("u1", "all", ["group:market.v1", "group:pro.v1"], [], None)
    prepared = gateway.prepare(
        Request(key.plaintext, {"limit": "100"}), "GET", "/api/v1/stocks/daily"
    )
    gateway.fail(prepared, "test_cleanup")
    with pytest.raises(DatasetNotEntitled):
        gateway.prepare(Request(key.plaintext), "GET", "/api/v1/quotes/realtime")


def test_pro_plan_still_requires_credential_scope(env) -> None:
    _, commerce, credentials, gateway = env
    activate(commerce, "u1", "pro")
    key = credentials.create("u1", "market-only", ["group:market.v1"], [], None)
    with pytest.raises(ScopeDenied):
        gateway.prepare(Request(key.plaintext), "GET", "/api/v1/quotes/realtime")


def test_group_scope_allows_endpoint_in_that_group(env) -> None:
    _, commerce, credentials, gateway = env
    activate(commerce, "u1", "pro")
    key = credentials.create("u1", "pro", ["group:pro.v1"], [], None)
    prepared = gateway.prepare(Request(key.plaintext), "GET", "/api/v1/quotes/realtime")
    gateway.fail(prepared, "test_cleanup")
