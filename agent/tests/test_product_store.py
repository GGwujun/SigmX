"""Tests for the product domain store — Task 1 of the product-closure plan.

Covers the server-driven plan catalog and migration idempotency. These are the
DTOs/seed values every later task (credits, activation, devices, routes) builds
on, so the assertions here are the contract for the whole closure.
"""

from __future__ import annotations

from pathlib import Path

from src.product.store import ProductStore


OLD_DATAHUB_KEYS = {
    "datahub.daily_quota",
    "datahub.basic",
    "datahub.featured",
    "datahub.external_api",
}


def test_catalog_is_seeded_and_server_driven(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    plans = {plan["code"]: plan for plan in store.list_plans()}

    # Prices come from the server catalog, not from frontend hard-coding.
    assert plans["free"]["price_cny_fen"] == 0
    assert plans["advanced"]["price_cny_fen"] == 26800
    assert plans["pro"]["price_cny_fen"] == 51800

    assert plans["free"]["entitlements"]["datahub.monthly_credits"] == 1_000
    assert plans["advanced"]["entitlements"]["datahub.dataset_groups"] == ["basic.v1", "market.v1"]
    assert plans["pro"]["entitlements"]["datahub.monthly_credits"] == 150_000
    for plan in plans.values():
        assert OLD_DATAHUB_KEYS.isdisjoint(plan["entitlements"])
    assert plans["pro"]["entitlements"]["desktop.device_limit"] == 3


def test_enterprise_plan_is_removed_from_personal_catalog(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    assert store.get_plan("enterprise") is None


def test_schema_v2_tables_exist(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    names = {
        row[0]
        for row in store._get_conn().execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "data_credit_lots",
        "data_credit_reservations",
        "data_credit_allocations",
        "data_credit_ledger",
        "datahub_endpoint_catalog",
        "datahub_credentials",
        "datahub_rate_buckets",
        "datahub_concurrency_leases",
        "datahub_request_usage",
    } <= names
    versions = {
        row[0]
        for row in store._get_conn().execute(
            "SELECT version FROM product_migrations"
        )
    }
    assert {1, 2, 3, 4, 5, 6} <= versions
    assert "usage_daily" not in names


def test_schema_v2_replaces_old_datahub_keys_only(tmp_path: Path) -> None:
    db_path = tmp_path / "product.db"
    first = ProductStore(db_path)
    conn = first._get_conn()
    conn.execute("DELETE FROM product_migrations WHERE version = 2")
    conn.execute(
        "UPDATE plans SET entitlements_json = ? WHERE code = 'advanced'",
        ('{"datahub.basic":true,"datahub.daily_quota":999,"desktop.device_limit":7}',),
    )
    conn.commit()
    conn.close()
    first._conn = None

    migrated = ProductStore(db_path).get_plan("advanced")
    assert migrated is not None
    assert OLD_DATAHUB_KEYS.isdisjoint(migrated["entitlements"])
    assert migrated["entitlements"]["datahub.monthly_credits"] == 30_000
    assert migrated["entitlements"]["desktop.device_limit"] == 7


def test_get_plan_unknown_returns_none(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    assert store.get_plan("nonexistent") is None


def test_migration_is_idempotent_when_reopened(tmp_path: Path) -> None:
    """Opening the same db twice must not duplicate the seed or error out."""
    db_path = tmp_path / "product.db"

    first = ProductStore(db_path)
    first_codes = {p["code"] for p in first.list_plans()}
    assert first_codes == {"free", "advanced", "pro"}

    second = ProductStore(db_path)  # re-open against the populated db
    second_codes = {p["code"] for p in second.list_plans()}
    assert second_codes == first_codes

    # The advanced plan was seeded exactly once — no duplicated rows.
    assert len(second.list_plans()) == 3
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
