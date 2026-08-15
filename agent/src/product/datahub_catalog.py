"""Versioned Data Hub endpoint access and pricing catalog."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from src.product.store import ProductStore


class UnknownDataHubEndpoint(Exception):
    pass


class InvalidPricingRule(Exception):
    pass


@dataclass(frozen=True)
class EndpointPricing:
    endpoint_code: str
    catalog_version: int
    http_method: str
    path_pattern: str
    dataset_group: str
    pricing_mode: str
    base_cost: int
    unit_name: str | None = None
    unit_size: int | None = None
    unit_cost: int | None = None
    max_cost: int | None = None
    enabled: bool = True


def _entry(code: str, path: str, group: str, mode: str, cost: int) -> EndpointPricing:
    if mode == "per_unit":
        return EndpointPricing(code, 1, "GET", path, group, mode, cost, "rows", 1000, 10, 100)
    return EndpointPricing(code, 1, "GET", path, group, mode, cost)


_V1 = [
    ("health", "/api/v1/health", "basic.v1", "free", 0),
    ("market.latest_trade_date", "/api/v1/market/latest-trade-date", "basic.v1", "free", 0),
    ("market.overview", "/api/v1/market/overview", "basic.v1", "fixed", 1),
    ("market.breadth", "/api/v1/market/breadth", "basic.v1", "fixed", 1),
    ("market.fund_summary", "/api/v1/market/fund-summary", "basic.v1", "fixed", 1),
    ("stocks.metadata", "/api/v1/stocks/metadata", "basic.v1", "fixed", 1),
    ("boards.members", "/api/v1/boards/members", "basic.v1", "fixed", 1),
    ("stocks.unusual_types", "/api/v1/stocks/unusual/types", "basic.v1", "fixed", 1),
    ("hot_money.list", "/api/v1/hot-money/list", "basic.v1", "fixed", 1),
    ("news.finance_rss_summary", "/api/v1/news/finance/rss-summary", "basic.v1", "fixed", 1),
    ("indices.daily", "/api/v1/indices/daily", "market.v1", "per_unit", 2),
    ("stocks.daily", "/api/v1/stocks/daily", "market.v1", "per_unit", 2),
    ("stocks.daily_basic", "/api/v1/stocks/daily-basic", "market.v1", "per_unit", 2),
    ("etf.daily", "/api/v1/etf/daily", "market.v1", "per_unit", 2),
    ("fund.daily", "/api/v1/fund/daily", "market.v1", "per_unit", 2),
    ("boards.daily", "/api/v1/boards/daily", "market.v1", "per_unit", 2),
    ("stocks.financial_statement", "/api/v1/stocks/financial-statement", "finance.v1", "per_unit", 2),
    ("stocks.fq_factors", "/api/v1/stocks/fq-factors", "market.v1", "per_unit", 2),
    ("stocks.minute", "/api/v1/stocks/minute", "pro.v1", "per_unit", 2),
    ("stocks.ticks", "/api/v1/stocks/ticks", "pro.v1", "per_unit", 2),
    ("sectors.fund_flow", "/api/v1/sectors/fund-flow", "pro.v1", "fixed", 5),
    ("sectors.fund_flow_intraday", "/api/v1/sectors/fund-flow/intraday", "pro.v1", "fixed", 5),
    ("stocks.hot_pool", "/api/v1/stocks/hot-pool", "market.v1", "fixed", 2),
    ("quotes.realtime", "/api/v1/quotes/realtime", "pro.v1", "fixed", 5),
    ("stocks.fund_flow", "/api/v1/stocks/fund-flow", "pro.v1", "fixed", 5),
    ("stocks.capital_flow", "/api/v1/stocks/capital-flow", "pro.v1", "fixed", 5),
    ("stocks.capital_rank", "/api/v1/stocks/capital-rank", "pro.v1", "fixed", 5),
    ("northbound.flow", "/api/v1/northbound/flow", "pro.v1", "fixed", 5),
    ("stocks.limit_pool", "/api/v1/stocks/limit-pool", "pro.v1", "fixed", 5),
    ("dragon_tiger", "/api/v1/dragon-tiger", "pro.v1", "fixed", 5),
    ("hot_list", "/api/v1/hot-list", "pro.v1", "fixed", 5),
    ("market.regime", "/api/v1/market/regime", "market.v1", "fixed", 2),
    ("stocks.financial_snapshot", "/api/v1/stocks/financial-snapshot", "finance.v1", "fixed", 3),
    ("stocks.eps_forecast", "/api/v1/stocks/eps-forecast", "finance.v1", "fixed", 3),
    ("stocks.margin", "/api/v1/stocks/margin", "finance.v1", "fixed", 3),
    ("stocks.block_trade", "/api/v1/stocks/block-trade", "finance.v1", "fixed", 3),
    ("stocks.holder_num", "/api/v1/stocks/holder-num", "finance.v1", "fixed", 3),
    ("stocks.dividends", "/api/v1/stocks/dividends", "finance.v1", "fixed", 3),
    ("funds.premium", "/api/v1/funds/premium", "pro.v1", "fixed", 5),
    ("funds.arbitrage_signals", "/api/v1/funds/arbitrage-signals", "pro.v1", "fixed", 5),
    ("etf.share_size", "/api/v1/etf/share-size", "market.v1", "fixed", 2),
    ("option_chain", "/api/v1/option-chain", "pro.v1", "fixed", 5),
    ("market.stage_snapshot", "/api/v1/market/stage-snapshot", "market.v1", "fixed", 2),
    ("stocks.quote5", "/api/v1/stocks/quote5", "pro.v1", "fixed", 5),
    ("stocks.unusual", "/api/v1/stocks/unusual", "pro.v1", "fixed", 5),
    ("stocks.call_auction", "/api/v1/stocks/call-auction", "pro.v1", "fixed", 5),
    ("hot_money.daily", "/api/v1/hot-money/daily", "pro.v1", "fixed", 5),
    ("stocks.hot_history", "/api/v1/stocks/hot-history", "pro.v1", "fixed", 5),
    ("content.morning_briefing_triptych", "/api/v1/content/morning-briefing-triptych", "pro.v1", "fixed", 5),
]

ENDPOINT_CATALOG_V1 = tuple(_entry(*values) for values in _V1)


class DataHubEndpointCatalog:
    def __init__(
        self, store: ProductStore, entries: Iterable[EndpointPricing] | None = None
    ) -> None:
        self.store = store
        self._entries = tuple(entries) if entries is not None else None
        for entry in self._entries or ():
            self._validate(entry)

    def list(self, version: int | None = None, enabled_only: bool = True) -> list[EndpointPricing]:
        entries = list(self._entries) if self._entries is not None else self._load()
        if version is not None:
            entries = [entry for entry in entries if entry.catalog_version == version]
        if enabled_only:
            entries = [entry for entry in entries if entry.enabled]
        if version is None:
            latest: dict[str, EndpointPricing] = {}
            for entry in entries:
                if entry.endpoint_code not in latest or entry.catalog_version > latest[entry.endpoint_code].catalog_version:
                    latest[entry.endpoint_code] = entry
            entries = list(latest.values())
        return sorted(entries, key=lambda entry: (entry.endpoint_code, entry.catalog_version))

    def get(self, endpoint_code: str, version: int | None = None) -> EndpointPricing:
        matches = [entry for entry in self.list(version=version) if entry.endpoint_code == endpoint_code]
        if not matches:
            raise UnknownDataHubEndpoint(endpoint_code)
        return max(matches, key=lambda entry: entry.catalog_version)

    def match(self, method: str, path: str, version: int | None = None) -> EndpointPricing:
        matches = [
            entry for entry in self.list(version=version)
            if entry.http_method == method.upper() and entry.path_pattern == path
        ]
        if not matches:
            raise UnknownDataHubEndpoint(f"{method.upper()} {path}")
        return max(matches, key=lambda entry: entry.catalog_version)

    def estimate(self, endpoint: EndpointPricing, requested_units: int) -> int:
        return self.calculate(endpoint, requested_units)

    def calculate(self, endpoint: EndpointPricing, actual_units: int) -> int:
        self._validate(endpoint)
        if actual_units < 0:
            raise ValueError("units cannot be negative")
        if endpoint.pricing_mode == "free":
            return 0
        if endpoint.pricing_mode == "fixed":
            return endpoint.base_cost
        extra_units = max(0, actual_units - int(endpoint.unit_size))
        cost = endpoint.base_cost + ceil(extra_units / int(endpoint.unit_size)) * int(endpoint.unit_cost)
        return min(cost, int(endpoint.max_cost))

    def _load(self) -> list[EndpointPricing]:
        rows = self.store._get_conn().execute(
            "SELECT endpoint_code, catalog_version, http_method, path_pattern, dataset_group, "
            "pricing_mode, base_cost, unit_name, unit_size, unit_cost, max_cost, enabled "
            "FROM datahub_endpoint_catalog ORDER BY endpoint_code, catalog_version"
        ).fetchall()
        entries = [EndpointPricing(**{**dict(row), "enabled": bool(row["enabled"])}) for row in rows]
        for entry in entries:
            self._validate(entry)
        return entries

    @staticmethod
    def _validate(entry: EndpointPricing) -> None:
        unit_fields = (entry.unit_name, entry.unit_size, entry.unit_cost, entry.max_cost)
        if entry.base_cost < 0 or entry.catalog_version <= 0:
            raise InvalidPricingRule(entry.endpoint_code)
        if entry.pricing_mode == "free":
            valid = entry.base_cost == 0 and all(value is None for value in unit_fields)
        elif entry.pricing_mode == "fixed":
            valid = all(value is None for value in unit_fields)
        elif entry.pricing_mode == "per_unit":
            valid = (
                bool(entry.unit_name)
                and isinstance(entry.unit_size, int) and entry.unit_size > 0
                and isinstance(entry.unit_cost, int) and entry.unit_cost > 0
                and isinstance(entry.max_cost, int) and entry.max_cost >= entry.base_cost
            )
        else:
            valid = False
        if not valid:
            raise InvalidPricingRule(entry.endpoint_code)
