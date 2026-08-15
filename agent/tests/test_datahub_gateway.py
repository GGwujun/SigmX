from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.responses import JSONResponse

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.datahub_credentials import DataHubCredentialService
from src.product.datahub_gateway import (
    CredentialRequired,
    DatasetNotEntitled,
    DataHubRequestGateway,
)
from src.product.store import ProductStore


class FakeRequest:
    def __init__(
        self,
        authorization: str | None = None,
        query: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> None:
        self.headers = {}
        if authorization:
            self.headers["authorization"] = authorization
        if request_id:
            self.headers["x-request-id"] = request_id
        self.query_params = query or {}
        self.client = type("Client", (), {"host": "203.0.113.8"})()


@pytest.fixture
def env(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    credentials = DataHubCredentialService(store)
    gateway = DataHubRequestGateway(store)
    return store, credentials, gateway


def bearer(secret: str) -> str:
    return f"Bearer {secret}"


def test_gateway_requires_new_bearer_credential(env) -> None:
    _, _, gateway = env
    with pytest.raises(CredentialRequired):
        gateway.prepare(FakeRequest(), "GET", "/api/v1/health")
    with pytest.raises(CredentialRequired):
        gateway.prepare(FakeRequest("Bearer sx_deadbeef"), "GET", "/api/v1/health")


def test_fixed_endpoint_authorizes_and_settles_one_credit(env) -> None:
    store, credentials, gateway = env
    created = credentials.create("u1", "basic", ["stocks.metadata"], [], None)
    CommerceService(store, CreditLedger(store)).ensure_monthly_data_grant(
        "u1", "free", __import__("datetime").date(2026, 8, 15)
    )
    prepared = gateway.prepare(
        FakeRequest(bearer(created.plaintext)), "GET", "/api/v1/stocks/metadata"
    )
    response = gateway.complete(prepared, JSONResponse({"ok": True, "data": [{"code": "1"}]}))
    assert DataCreditLedger(store).balance("u1").available == 999
    assert response.headers["X-DataHub-Credits-Charged"] == "1"
    assert response.headers["X-DataHub-Endpoint"] == "stocks.metadata"
    assert store._get_conn().execute("SELECT COUNT(*) FROM datahub_request_usage").fetchone()[0] == 1


def test_per_unit_endpoint_releases_unused_authorization(env) -> None:
    store, credentials, gateway = env
    commerce = CommerceService(store, CreditLedger(store))
    code = commerce.admin_create_activation_code(plan="advanced", months=3)
    commerce.activate_code("u1", code.plaintext, "activation")
    created = credentials.create("u1", "daily", ["stocks.daily"], [], None)
    prepared = gateway.prepare(
        FakeRequest(bearer(created.plaintext), {"limit": "10000"}),
        "GET",
        "/api/v1/stocks/daily",
    )
    assert prepared.credits_authorized == 92
    response = gateway.complete(
        prepared, JSONResponse({"ok": True, "data": [{} for _ in range(1001)]})
    )
    assert response.headers["X-DataHub-Credits-Charged"] == "12"
    assert DataCreditLedger(store).balance("u1").available == 30_000 - 12


def test_failed_request_releases_authorization(env) -> None:
    store, credentials, gateway = env
    created = credentials.create("u1", "basic", ["stocks.metadata"], [], None)
    CommerceService(store, CreditLedger(store)).ensure_monthly_data_grant(
        "u1", "free", __import__("datetime").date(2026, 8, 15)
    )
    prepared = gateway.prepare(
        FakeRequest(bearer(created.plaintext)), "GET", "/api/v1/stocks/metadata"
    )
    gateway.fail(prepared, "handler_error", status_code=500)
    assert DataCreditLedger(store).balance("u1").available == 1_000


def test_dataset_group_is_enforced_before_handler(env) -> None:
    _, credentials, gateway = env
    created = credentials.create("u1", "pro-only", ["quotes.realtime"], [], None)
    with pytest.raises(DatasetNotEntitled):
        gateway.prepare(
            FakeRequest(bearer(created.plaintext)), "GET", "/api/v1/quotes/realtime"
        )


def test_usage_audit_failure_does_not_undo_settlement(env, monkeypatch) -> None:
    store, credentials, gateway = env
    created = credentials.create("u1", "basic", ["stocks.metadata"], [], None)
    CommerceService(store, CreditLedger(store)).ensure_monthly_data_grant(
        "u1", "free", __import__("datetime").date(2026, 8, 15)
    )
    prepared = gateway.prepare(
        FakeRequest(bearer(created.plaintext)), "GET", "/api/v1/stocks/metadata"
    )
    monkeypatch.setattr(gateway, "_write_usage", lambda *args: (_ for _ in ()).throw(RuntimeError("audit down")))
    response = gateway.complete(prepared, JSONResponse({"ok": True, "data": []}))
    assert response.status_code == 200
    assert DataCreditLedger(store).balance("u1").available == 999
