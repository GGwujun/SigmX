"""Tests for the product domain store — Task 1 of the product-closure plan.

Covers the server-driven plan catalog and migration idempotency. These are the
DTOs/seed values every later task (credits, activation, devices, routes) builds
on, so the assertions here are the contract for the whole closure.
"""

from __future__ import annotations

from pathlib import Path

from src.product.store import ProductStore


def test_catalog_is_seeded_and_server_driven(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    plans = {plan["code"]: plan for plan in store.list_plans()}

    # Prices come from the server catalog, not from frontend hard-coding.
    assert plans["free"]["price_cny_fen"] == 0
    assert plans["advanced"]["price_cny_fen"] == 26800
    assert plans["pro"]["price_cny_fen"] == 51800

    # Entitlements are stable keys with numeric quotas (design §4.1, §6).
    assert plans["advanced"]["entitlements"]["datahub.daily_quota"] == 1000
    assert plans["pro"]["entitlements"]["desktop.device_limit"] == 3


def test_enterprise_plan_present(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    enterprise = store.get_plan("enterprise")
    assert enterprise is not None
    assert enterprise["price_cny_fen"] == 0  # contract-priced, not a fixed sticker
    # Enterprise is configured per-contract, so it still advertises the external-API
    # entitlement key even though its quota is not a fixed number.
    assert "datahub.external_api" in enterprise["entitlements"]


def test_get_plan_unknown_returns_none(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    assert store.get_plan("nonexistent") is None


def test_migration_is_idempotent_when_reopened(tmp_path: Path) -> None:
    """Opening the same db twice must not duplicate the seed or error out."""
    db_path = tmp_path / "product.db"

    first = ProductStore(db_path)
    first_codes = {p["code"] for p in first.list_plans()}
    assert first_codes == {"free", "advanced", "pro", "enterprise"}

    second = ProductStore(db_path)  # re-open against the populated db
    second_codes = {p["code"] for p in second.list_plans()}
    assert second_codes == first_codes

    # The advanced plan was seeded exactly once — no duplicated rows.
    assert len(second.list_plans()) == 4
    advanced = second.get_plan("advanced")
    assert advanced is not None
    assert advanced["price_cny_fen"] == 26800


def test_transaction_commits_atomically(tmp_path: Path) -> None:
    """The transaction() context manager is the single write boundary for later tasks."""
    store = ProductStore(tmp_path / "product.db")
    with store.transaction() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS scratch (k TEXT PRIMARY KEY, v INTEGER)")
        conn.execute("INSERT OR REPLACE INTO scratch (k, v) VALUES (?, ?)", ("a", 1))

    rows = store._get_conn().execute("SELECT v FROM scratch WHERE k = ?", ("a",)).fetchone()
    assert rows is not None
    assert rows[0] == 1
