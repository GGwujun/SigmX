from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .client import SkillRuntimeError
from .models import DataRequest, DataResult, SkillDataPolicy


class DataSource(Protocol):
    def fetch(self, request: DataRequest) -> DataResult: ...


class SkillDataRouter:
    def __init__(self, data_hub: DataSource, fallbacks: dict[str, DataSource]):
        self.data_hub = data_hub
        self.fallbacks = fallbacks

    def fetch(self, policy: SkillDataPolicy, request: DataRequest) -> DataResult:
        if policy.primary_source != "data_hub":
            return self._fallback(policy, request, "capability_not_supported")
        try:
            return self.data_hub.fetch(request)
        except SkillRuntimeError as exc:
            if exc.code not in {"credential_missing", "source_unavailable", "capability_not_supported"}:
                raise
            return self._fallback(policy, request, exc.code)

    def _fallback(self, policy: SkillDataPolicy, request: DataRequest, reason: str) -> DataResult:
        if not request.allow_fallback:
            raise SkillRuntimeError("fallback_not_allowed", "request requires the declared primary source")
        last_error: SkillRuntimeError | None = None
        for name in policy.fallback_sources:
            source = self.fallbacks.get(name)
            if source is None:
                continue
            try:
                result = source.fetch(request)
            except SkillRuntimeError as exc:
                last_error = exc
                continue
            if any(field not in row for row in result.rows for field in request.required_fields):
                raise SkillRuntimeError("fallback_schema_mismatch", f"{name} omitted required fields")
            return replace(result, degraded=True, degradation_reason=reason)
        if last_error:
            raise last_error
        raise SkillRuntimeError("source_unavailable", "no declared fallback source is available")
