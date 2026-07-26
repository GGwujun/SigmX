"""Data Hub API-key auth + atomic quota tests.

Covers the four-way gate in ``_data_hub_auth`` (non-Data-Hub passthrough,
loopback passthrough, no-key-remote 401, invalid-key 401) and the atomic
``acquire_quota`` that replaces the TOCTOU check-then-record pair.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.sigmx_routes import register_sigmx_routes
from src.data.subscription_store import SubscriptionStore


def _app() -> FastAPI:
    app = FastAPI()
    register_sigmx_routes(app)
    return app


def test_non_data_hub_mode_passthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When VIBE_TRADING_DATA_HUB_MODE is unset, no auth is required."""
    monkeypatch.delenv("VIBE_TRADING_DATA_HUB_MODE", raising=False)
    # Point the market DB at an empty file so endpoints return 404 (not 500).
    empty = tmp_path / "market.db"
    empty.touch()
    monkeypatch.setenv("VIBE_TRADING_MARKET_DB_PATH", str(empty))
    with mock.patch("src.api.sigmx_routes.get_db"):  # avoid real DB hits
        client = TestClient(_app())
        # No API key, simulated remote client — still allowed (mode off).
        res = client.get("/api/v1/market/latest-trade-date")
        # 404 from DATA_NOT_FOUND is fine; 401 would mean the gate wrongly fired.
        assert res.status_code != 401


def test_data_hub_mode_rejects_remote_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Data Hub mode + non-loopback + no key → 401."""
    monkeypatch.setenv("VIBE_TRADING_DATA_HUB_MODE", "1")
    client = TestClient(_app())
    res = client.get("/api/v1/market/latest-trade-date")  # TestClient is loopback
    # TestClient appears as 127.0.0.1 → loopback passes. Force a non-loopback
    # client host to simulate a public request.
    with mock.patch("src.api.sigmx_routes._is_loopback", return_value=False):
        res = client.get("/api/v1/market/latest-trade-date")
    assert res.status_code == 401
    assert "API key required" in res.json()["detail"]


def test_data_hub_mode_loopback_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Data Hub mode + loopback (server's own healthcheck) → no key needed."""
    monkeypatch.setenv("VIBE_TRADING_DATA_HUB_MODE", "1")
    with mock.patch("src.api.sigmx_routes.get_db"):
        client = TestClient(_app())
        res = client.get("/api/v1/market/latest-trade-date")
    assert res.status_code != 401  # loopback passthrough


def test_invalid_key_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBE_TRADING_DATA_HUB_MODE", "1")
    client = TestClient(_app())
    with mock.patch("src.api.sigmx_routes._is_loopback", return_value=False):
        res = client.get(
            "/api/v1/market/latest-trade-date",
            headers={"X-API-Key": "sx_deadbeef"},
        )
    assert res.status_code == 401


def test_acquire_quota_atomic_and_bounded(tmp_path: Path) -> None:
    """acquire_quota reserves exactly quota slots, then refuses (no TOCTOU)."""
    store = SubscriptionStore(tmp_path / "subs.db")
    created = store.create("u@x.com", tier="free", quota_daily=3)
    sub_id = created["id"]
    key = created["api_key"]

    # First 3 succeed.
    assert store.acquire_quota(sub_id) is True
    assert store.acquire_quota(sub_id) is True
    assert store.acquire_quota(sub_id) is True
    # 4th refused — even though check_quota + record_usage would have raced.
    assert store.acquire_quota(sub_id) is False
    assert store.acquire_quota(sub_id) is False

    # Usage recorded exactly 3 (no over-count).
    allowed, used, quota = store.check_quota(sub_id)
    assert (used, quota) == (3, 3)
    assert allowed is False

    # Key still validates (quota refusal does not revoke the key).
    assert store.validate_api_key(key) is not None
