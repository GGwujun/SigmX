from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.product.datahub_catalog import (
    ENDPOINT_CATALOG_V1,
    DataHubEndpointCatalog,
    EndpointPricing,
    InvalidPricingRule,
    UnknownDataHubEndpoint,
)
from src.product.store import ProductStore


@pytest.fixture
def catalog(tmp_path: Path) -> DataHubEndpointCatalog:
    return DataHubEndpointCatalog(ProductStore(tmp_path / "product.db"))


def test_catalog_calculates_free_fixed_and_capped_per_unit_prices(
    catalog: DataHubEndpointCatalog,
) -> None:
    assert catalog.calculate(catalog.get("health"), 0) == 0
    assert catalog.calculate(catalog.get("stocks.metadata"), 1) == 1
    assert catalog.calculate(catalog.get("stocks.daily"), 1) == 2
    assert catalog.calculate(catalog.get("stocks.daily"), 1_001) == 12
    assert catalog.estimate(catalog.get("stocks.daily"), 50_000) == 100


def test_catalog_matches_exact_method_and_path_and_rejects_unknown(
    catalog: DataHubEndpointCatalog,
) -> None:
    assert catalog.match("GET", "/api/v1/stocks/daily").endpoint_code == "stocks.daily"
    with pytest.raises(UnknownDataHubEndpoint):
        catalog.match("POST", "/api/v1/stocks/daily")
    with pytest.raises(UnknownDataHubEndpoint):
        catalog.get("does.not.exist")


def test_catalog_rejects_negative_units(catalog: DataHubEndpointCatalog) -> None:
    with pytest.raises(ValueError, match="negative"):
        catalog.calculate(catalog.get("stocks.daily"), -1)


@pytest.mark.parametrize(
    "rule",
    [
        EndpointPricing("bad.free", 1, "GET", "/free", "basic.v1", "free", 1),
        EndpointPricing("bad.fixed", 1, "GET", "/fixed", "basic.v1", "fixed", 1, "rows", 1, 1, 1),
        EndpointPricing("bad.unit", 1, "GET", "/unit", "market.v1", "per_unit", 2, "rows", 0, 10, 100),
        EndpointPricing("bad.cap", 1, "GET", "/cap", "market.v1", "per_unit", 2, "rows", 1000, 10, 1),
    ],
)
def test_invalid_pricing_rules_fail_closed(tmp_path: Path, rule: EndpointPricing) -> None:
    with pytest.raises(InvalidPricingRule):
        DataHubEndpointCatalog(ProductStore(tmp_path / "product.db"), entries=[rule])


def test_disabled_endpoint_is_not_returned_by_default(tmp_path: Path) -> None:
    disabled = EndpointPricing(
        "disabled", 1, "GET", "/disabled", "basic.v1", "fixed", 1, enabled=False
    )
    catalog = DataHubEndpointCatalog(ProductStore(tmp_path / "product.db"), entries=[disabled])
    assert catalog.list() == []
    assert catalog.list(enabled_only=False) == [disabled]
    with pytest.raises(UnknownDataHubEndpoint):
        catalog.get("disabled")


def test_current_sigmx_get_routes_are_exactly_covered_by_v1_catalog() -> None:
    route_file = Path(__file__).parents[1] / "src" / "api" / "sigmx_routes.py"
    tree = ast.parse(route_file.read_text(encoding="utf-8"))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if decorator.func.attr != "get" or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str) and path.value.startswith("/api/v1/"):
                routes.add(("GET", path.value))

    seeded = {(entry.http_method, entry.path_pattern) for entry in ENDPOINT_CATALOG_V1}
    assert len(routes) == 49
    assert seeded == routes


def test_store_seed_contains_all_49_enabled_v1_entries(catalog: DataHubEndpointCatalog) -> None:
    entries = catalog.list(version=1)
    assert len(entries) == 49
    assert len({entry.endpoint_code for entry in entries}) == 49
