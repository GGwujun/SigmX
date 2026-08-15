from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.data_credits import DataCreditLedger
from src.product.datahub_catalog import DataHubEndpointCatalog
from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def isolated_data_services(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._ledger = CreditLedger(store)
    pr._commerce = CommerceService(store, pr._ledger)
    pr._data_ledger = DataCreditLedger(store)
    pr._endpoint_catalog = DataHubEndpointCatalog(store)
    yield store
    pr._store = None
    pr._ledger = None
    pr._commerce = None
    pr._data_ledger = None
    pr._endpoint_catalog = None


def test_data_credit_reads_are_user_isolated() -> None:
    ledger = pr._get_data_ledger()
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="u1")
    ledger.grant("u2", 200, source="purchase", expires_at=None, idempotency_key="u2")

    balance = asyncio.run(pr.my_data_credits(user={"id": "u1"}))
    lots = asyncio.run(pr.my_data_credit_lots(user={"id": "u1"}))
    entries = asyncio.run(pr.my_data_credit_ledger(user={"id": "u1"}))

    assert balance.available == 1_100
    assert {lot.idempotency_key for lot in lots.lots} == {
        "u1",
        f"data-plan-month:u1:free:{datetime.now(timezone.utc):%Y-%m}",
    }
    assert sorted(entry.delta for entry in entries.entries) == [100, 1_000]


def test_first_data_credit_read_grants_free_monthly_lot() -> None:
    first = asyncio.run(pr.my_data_credits(user={"id": "new-user"}))
    second = asyncio.run(pr.my_data_credits(user={"id": "new-user"}))
    assert first.available == 1_000
    assert second.available == 1_000


def test_public_datahub_catalog_serializes_all_current_entries() -> None:
    response = asyncio.run(pr.datahub_catalog())
    assert len(response.items) == 49
    assert len({item.endpoint_code for item in response.items}) == 49
    daily = next(item for item in response.items if item.endpoint_code == "stocks.daily")
    assert daily.dataset_group == "market.v1"
    assert daily.pricing_mode == "per_unit"
    assert daily.unit_size == 1000
    assert daily.max_cost == 100
