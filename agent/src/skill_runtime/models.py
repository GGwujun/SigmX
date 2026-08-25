from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OWNERSHIPS = frozenset({"official", "adapted", "third_party", "community"})
EXECUTION_MODES = frozenset({"executable", "instructional"})
PRIMARY_SOURCES = frozenset({"data_hub", "public_source", "user_source", "none"})
FALLBACK_SOURCES = frozenset({"akshare", "mootdx", "yfinance", "okx", "ccxt", "sec", "cninfo", "rsshub", "bing"})


@dataclass(frozen=True)
class SkillDataPolicy:
    schema_version: int
    ownership: str
    execution: str
    primary_source: str
    datahub_endpoints: tuple[str, ...] = ()
    fallback_sources: tuple[str, ...] = ()
    markets: tuple[str, ...] = ()
    credentials: tuple[str, ...] = ()
    capability_status: str = "full"

    @property
    def credential_required(self) -> bool:
        return bool(self.credentials)


@dataclass(frozen=True)
class SkillManifest:
    slug: str
    description: str
    content: str
    policy: SkillDataPolicy


@dataclass(frozen=True)
class DataRequest:
    capability: str
    params: dict[str, Any]
    allow_fallback: bool = True
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataResult:
    rows: tuple[dict[str, Any], ...]
    source: str
    endpoint_code: str | None
    as_of: str | None
    degraded: bool = False
    degradation_reason: str | None = None
