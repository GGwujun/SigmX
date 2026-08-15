"""Strict request sizing and response counting for Data Hub billing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from src.product.datahub_catalog import EndpointPricing


class BillingContractError(Exception):
    pass


class RequestRowsExceeded(Exception):
    pass


class HistoryDepthExceeded(Exception):
    pass


@dataclass(frozen=True)
class RequestedUsage:
    requested_units: int


class RequestContract:
    @staticmethod
    def evaluate(
        endpoint: EndpointPricing,
        query_params: Mapping[str, str],
        plan: Mapping[str, Any],
        *,
        today: date | None = None,
    ) -> RequestedUsage:
        if endpoint.pricing_mode != "per_unit":
            return RequestedUsage(0)
        if not endpoint.request_limit_params or endpoint.default_units <= 0 or not endpoint.result_path:
            raise BillingContractError(f"incomplete request contract for {endpoint.endpoint_code}")
        raw_units = None
        for name in endpoint.request_limit_params:
            value = query_params.get(name)
            if value not in (None, ""):
                raw_units = value
                break
        try:
            units = endpoint.default_units if raw_units is None else int(raw_units)
        except (TypeError, ValueError) as exc:
            raise BillingContractError("requested row count must be an integer") from exc
        if units <= 0:
            raise BillingContractError("requested row count must be positive")
        maximum = int(plan.get("datahub.max_rows_per_request", 0))
        if maximum <= 0 or units > maximum:
            raise RequestRowsExceeded(f"requested {units} rows exceeds plan maximum {maximum}")
        if endpoint.date_params is not None:
            start_name, _ = endpoint.date_params
            raw_start = query_params.get(start_name)
            if raw_start:
                try:
                    start = date.fromisoformat(raw_start)
                except ValueError as exc:
                    raise BillingContractError("start date must use YYYY-MM-DD") from exc
                depth = int(plan.get("datahub.history_depth_days", 0))
                current = today or date.today()
                if depth <= 0 or (current - start).days > depth:
                    raise HistoryDepthExceeded("requested history exceeds plan depth")
        return RequestedUsage(units)


class ResponseContract:
    @staticmethod
    def count(endpoint: EndpointPricing, response_json: Any) -> int:
        if endpoint.pricing_mode != "per_unit":
            return 0
        if not endpoint.result_path:
            raise BillingContractError(f"missing result path for {endpoint.endpoint_code}")
        value = response_json
        for key in endpoint.result_path:
            if not isinstance(value, dict) or key not in value:
                raise BillingContractError(f"response path is missing for {endpoint.endpoint_code}")
            value = value[key]
        if not isinstance(value, list):
            raise BillingContractError(f"response path is not a list for {endpoint.endpoint_code}")
        return len(value)
