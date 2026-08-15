from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.product_routes as pr
from src.product.data_credits import DataCreditLedger
from src.product.datahub_catalog import DataHubEndpointCatalog
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def isolated_data_services(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._data_ledger = DataCreditLedger(store)
    pr._endpoint_catalog = DataHubEndpointCatalog(store)
    yield store
    pr._store = None
    pr._data_ledger = None
    pr._endpoint_catalog = None


def test_data_credit_reads_are_user_isolated() -> None:
    ledger = pr._get_data_ledger()
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="u1")
    ledger.grant("u2", 200, source="purchase", expires_at=None, idempotency_key="u2")

    balance = asyncio.run(pr.my_data_credits(user={"id": "u1"}))
    lots = asyncio.run(pr.my_data_credit_lots(user={"id": "u1"}))
    entries = asyncio.run(pr.my_data_credit_ledger(user={"id": "u1"}))

    assert balance.available == 100
    assert [lot.idempotency_key for lot in lots.lots] == ["u1"]
    assert len(entries.entries) == 1
    assert entries.entries[0].delta == 100


def test_public_datahub_catalog_serializes_all_current_entries() -> None:
    response = asyncio.run(pr.datahub_catalog())
    assert len(response.items) == 49
    assert len({item.endpoint_code for item in response.items}) == 49
    daily = next(item for item in response.items if item.endpoint_code == "stocks.daily")
    assert daily.dataset_group == "market.v1"
    assert daily.pricing_mode == "per_unit"
    assert daily.unit_size == 1000
    assert daily.max_cost == 100
