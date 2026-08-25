from __future__ import annotations

import re
from pathlib import Path

from src.product.datahub_catalog import ENDPOINT_CATALOG_V2

from .models import (
    EXECUTION_MODES,
    FALLBACK_SOURCES,
    OWNERSHIPS,
    PRIMARY_SOURCES,
    SkillDataPolicy,
    SkillManifest,
)


class ManifestValidationError(ValueError):
    pass


def _scalar(value: str):
    value = value.strip().strip('"\'')
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip('"\'') for item in value[1:-1].split(",") if item.strip()]
    if value.isdigit():
        return int(value)
    return value


def _front_matter(content: str) -> dict[str, object]:
    match = re.match(r"^---\s*\r?\n(.*?)\r?\n---", content, re.DOTALL)
    if not match:
        raise ManifestValidationError("front matter is required")
    result: dict[str, object] = {}
    nested: dict[str, object] | None = None
    list_key: str | None = None
    for raw in match.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" "):
            key, _, value = raw.partition(":")
            if not _:
                continue
            if value.strip():
                result[key.strip()] = _scalar(value)
                nested = None
            else:
                nested = {}
                result[key.strip()] = nested
            list_key = None
            continue
        if nested is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("-") and list_key:
            values = nested.setdefault(list_key, [])
            assert isinstance(values, list)
            values.append(_scalar(stripped[1:]))
            continue
        key, _, value = stripped.partition(":")
        if not _:
            continue
        list_key = key.strip()
        nested[list_key] = _scalar(value) if value.strip() else []
    return result


def _tuple(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise ManifestValidationError("policy list field must be a list")
    return tuple(str(item) for item in value)


def validate_policy(policy: SkillDataPolicy) -> None:
    if policy.schema_version != 1:
        raise ManifestValidationError("unsupported schema_version")
    if policy.ownership not in OWNERSHIPS:
        raise ManifestValidationError("invalid ownership")
    if policy.execution not in EXECUTION_MODES:
        raise ManifestValidationError("invalid execution")
    if policy.primary_source not in PRIMARY_SOURCES:
        raise ManifestValidationError("invalid primary_source")
    if policy.primary_source == "data_hub" and not policy.datahub_endpoints:
        raise ManifestValidationError("datahub_endpoints required for Data Hub source")
    known_endpoints = {item.endpoint_code for item in ENDPOINT_CATALOG_V2}
    unknown_endpoints = set(policy.datahub_endpoints) - known_endpoints
    if unknown_endpoints:
        raise ManifestValidationError(f"unknown Data Hub endpoints: {sorted(unknown_endpoints)}")
    unknown_fallbacks = set(policy.fallback_sources) - FALLBACK_SOURCES
    if unknown_fallbacks:
        raise ManifestValidationError(f"unknown fallback sources: {sorted(unknown_fallbacks)}")
    if any(value not in {"SIGMX_DATA_HUB_BASE_URL", "SIGMX_DATA_HUB_KEY", "TUSHARE_TOKEN"} for value in policy.credentials):
        raise ManifestValidationError("unsupported credential")


def load_skill_manifest(path: Path) -> SkillManifest:
    content = path.read_text(encoding="utf-8")
    front = _front_matter(content)
    sigmx = front.get("sigmx")
    if not isinstance(sigmx, dict):
        raise ManifestValidationError("sigmx policy is required")
    policy = SkillDataPolicy(
        schema_version=int(sigmx.get("schema_version", 0)),
        ownership=str(sigmx.get("ownership", "")),
        execution=str(sigmx.get("execution", "")),
        primary_source=str(sigmx.get("primary_source", "")),
        datahub_endpoints=_tuple(sigmx.get("datahub_endpoints")),
        fallback_sources=_tuple(sigmx.get("fallback_sources")),
        markets=_tuple(sigmx.get("markets")),
        credentials=_tuple(sigmx.get("credentials")),
        capability_status=str(sigmx.get("capability_status", "full")),
    )
    validate_policy(policy)
    return SkillManifest(
        slug=str(front.get("name") or path.parent.name),
        description=str(front.get("description") or ""),
        content=content,
        policy=policy,
    )


def validate_skill_tree(root: Path) -> list[SkillManifest]:
    return [load_skill_manifest(path) for path in sorted(root.glob("*/SKILL.md"))]
