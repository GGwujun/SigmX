"""Destructive Data Hub credential cutover tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.sigmx_routes as routes
from src.product.datahub_credentials import DataHubCredentialService
from src.product.datahub_gateway import DataHubBillingRoute, DataHubRequestGateway
from src.product.store import ProductStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = ProductStore(tmp_path / "product.db")
    routes._gateway = DataHubRequestGateway(store)
    monkeypatch.setenv("VIBE_TRADING_DATA_HUB_MODE", "1")
    app = FastAPI()
    routes.register_sigmx_routes(app)
    yield TestClient(app), DataHubCredentialService(store), app
    routes._gateway = None


def test_data_hub_requires_sxd_bearer_even_on_loopback(client) -> None:
    http, _, _ = client
    assert http.get("/api/v1/health").status_code == 401
    assert http.get("/api/v1/health", headers={"X-API-Key": "sx_dead"}).status_code == 401
    assert http.get("/api/v1/health?api_key=sx_dead").status_code == 401
    assert http.get("/api/v1/health", headers={"Authorization": "Bearer desktop.jwt"}).status_code == 401


def test_valid_personal_key_reaches_handler(client) -> None:
    http, credentials, _ = client
    created = credentials.create("u1", "health", ["health"], [], None)
    response = http.get(
        "/api/v1/health", headers={"Authorization": f"Bearer {created.plaintext}"}
    )
    assert response.status_code == 200
    assert response.headers["X-DataHub-Endpoint"] == "health"


def test_every_v1_route_uses_billing_route(client) -> None:
    _, _, app = client
    data_routes = [route for route in app.routes if getattr(route, "path", "").startswith("/api/v1/")]
    assert len(data_routes) == 49
    assert all(isinstance(route, DataHubBillingRoute) for route in data_routes)


def test_non_data_hub_mode_is_explicit_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIBE_TRADING_DATA_HUB_MODE", raising=False)
    routes._gateway = DataHubRequestGateway(ProductStore(tmp_path / "product.db"))
    app = FastAPI()
    routes.register_sigmx_routes(app)
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    routes._gateway = None
