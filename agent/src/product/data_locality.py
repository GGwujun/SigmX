"""Executable ownership and locality boundary for personal SigmX data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DataClass(StrEnum):
    PUBLIC = "public"
    PERSONAL = "personal"
    PRIVATE = "private"
    SECRET = "secret"


@dataclass(frozen=True)
class DataPolicy:
    object_type: str
    data_class: DataClass
    owner: str
    cloud_allowed: bool
    local_only: bool


class UnsafeCloudPayload(ValueError):
    pass


_POLICIES = {
    "public_instrument": DataPolicy("public_instrument", DataClass.PUBLIC, "platform", True, False),
    "public_report": DataPolicy("public_report", DataClass.PUBLIC, "author", True, False),
    "watchlist": DataPolicy("watchlist", DataClass.PERSONAL, "user", True, False),
    "saved_query": DataPolicy("saved_query", DataClass.PERSONAL, "user", True, False),
    "cloud_task": DataPolicy("cloud_task", DataClass.PERSONAL, "user", True, False),
    "portfolio_file": DataPolicy("portfolio_file", DataClass.PRIVATE, "user", False, True),
    "local_research": DataPolicy("local_research", DataClass.PRIVATE, "user", False, True),
    "broker_credential": DataPolicy("broker_credential", DataClass.SECRET, "user", False, True),
    "datahub_credential": DataPolicy("datahub_credential", DataClass.SECRET, "user", False, True),
}

_FORBIDDEN_CLOUD_KEYS = {
    "api_key", "access_token", "refresh_token", "password", "secret", "credential",
    "local_path", "file_path", "file_content", "portfolio_content", "broker_token",
}


class DataLocalityPolicy:
    def classify(self, object_type: str) -> DataPolicy:
        try:
            return _POLICIES[object_type]
        except KeyError as exc:
            raise KeyError(f"data locality is not declared for {object_type}") from exc

    def assert_cloud_safe(self, payload: Any, *, path: str = "payload") -> None:
        if isinstance(payload, dict):
            for key, value in payload.items():
                normalized = str(key).strip().casefold()
                if normalized in _FORBIDDEN_CLOUD_KEYS or normalized.endswith(("_secret", "_password", "_credential")):
                    raise UnsafeCloudPayload(f"{path}.{key} is not allowed across the cloud boundary")
                self.assert_cloud_safe(value, path=f"{path}.{key}")
        elif isinstance(payload, (list, tuple)):
            for index, value in enumerate(payload):
                self.assert_cloud_safe(value, path=f"{path}[{index}]")
