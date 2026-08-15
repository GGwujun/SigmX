from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.product.datahub_catalog import DataHubEndpointCatalog
from src.product.datahub_contracts import (
    BillingContractError,
    HistoryDepthExceeded,
    RequestContract,
    RequestRowsExceeded,
    ResponseContract,
)
from src.product.store import ProductStore


@pytest.fixture
def catalog(tmp_path: Path) -> DataHubEndpointCatalog:
    return DataHubEndpointCatalog(ProductStore(tmp_path / "product.db"))


ADVANCED = {
    "datahub.max_rows_per_request": 10_000,
    "datahub.history_depth_days": 1_825,
}


def test_all_per_unit_endpoints_have_explicit_contracts(catalog: DataHubEndpointCatalog) -> None:
    current = catalog.list()
    assert len(current) == 49
    per_unit = [entry for entry in current if entry.pricing_mode == "per_unit"]
    assert len(per_unit) == 10
    assert all(entry.request_limit_params for entry in per_unit)
    assert all(entry.default_units > 0 for entry in per_unit)
    assert all(entry.result_path for entry in per_unit)
    assert {entry.catalog_version for entry in current} == {2}


def test_request_contract_uses_limit_and_default(catalog: DataHubEndpointCatalog) -> None:
    endpoint = catalog.get("stocks.daily")
    assert RequestContract.evaluate(endpoint, {"limit": "1500"}, ADVANCED).requested_units == 1500
    assert RequestContract.evaluate(endpoint, {}, ADVANCED).requested_units == 250


def test_request_contract_rejects_rows_above_plan(catalog: DataHubEndpointCatalog) -> None:
    endpoint = catalog.get("stocks.daily")
    with pytest.raises(RequestRowsExceeded):
        RequestContract.evaluate(
            endpoint, {"limit": "10001"}, ADVANCED
        )


def test_request_contract_rejects_history_older_than_plan(catalog: DataHubEndpointCatalog) -> None:
    endpoint = catalog.get("stocks.daily")
    today = date(2026, 8, 15)
    with pytest.raises(HistoryDepthExceeded):
        RequestContract.evaluate(
            endpoint,
            {"start": "2020-01-01", "end": "2026-08-15", "limit": "100"},
            ADVANCED,
            today=today,
        )


def test_fixed_endpoint_has_zero_requested_units(catalog: DataHubEndpointCatalog) -> None:
    assert RequestContract.evaluate(catalog.get("stocks.metadata"), {}, ADVANCED).requested_units == 0


def test_response_contract_counts_configured_list(catalog: DataHubEndpointCatalog) -> None:
    endpoint = catalog.get("stocks.daily")
    assert ResponseContract.count(endpoint, {"ok": True, "data": [{}, {}, {}]}) == 3
    assert ResponseContract.count(endpoint, {"ok": True, "data": []}) == 0


def test_response_contract_fails_closed_on_wrong_shape(catalog: DataHubEndpointCatalog) -> None:
    endpoint = catalog.get("stocks.daily")
    with pytest.raises(BillingContractError):
        ResponseContract.count(endpoint, {"ok": True, "rows": []})
    with pytest.raises(BillingContractError):
        ResponseContract.count(endpoint, {"ok": True, "data": {"row": 1}})
