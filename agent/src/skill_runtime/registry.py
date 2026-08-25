from __future__ import annotations

from src.product.datahub_catalog import ENDPOINT_CATALOG_V2


DATA_HUB_PATHS = {entry.endpoint_code: entry.path_pattern for entry in ENDPOINT_CATALOG_V2}


def endpoint_path(endpoint_code: str) -> str:
    try:
        return DATA_HUB_PATHS[endpoint_code]
    except KeyError as exc:
        raise KeyError(f"unknown Data Hub endpoint: {endpoint_code}") from exc
