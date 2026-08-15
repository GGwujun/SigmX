"""Privacy-preserving context manifests for reproducible research runs."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


_SECRET_KEYS = {"api_key", "authorization", "password", "secret", "token", "refresh_token", "access_token"}


@dataclass(frozen=True)
class LocalFileRef:
    ref: str
    name: str
    local_only: bool = True


@dataclass(frozen=True)
class ContextManifest:
    current_symbol: str | None
    cloud_watchlist_refs: tuple[str, ...]
    risk_profile_ref: str | None
    market_snapshot_ref: str | None
    local_files: tuple[LocalFileRef, ...]
    safe_attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_context_manifest(
    *,
    current_symbol: str | None,
    cloud_watchlist_refs: list[str],
    risk_profile_ref: str | None,
    market_snapshot_ref: str | None,
    local_files: list[Path],
    extra: dict[str, Any],
) -> ContextManifest:
    refs = []
    for path in local_files:
        resolved = str(Path(path).resolve())
        refs.append(LocalFileRef(ref=f"local-file:{hashlib.sha256(resolved.encode()).hexdigest()[:16]}", name=Path(path).name))
    safe = {key: value for key, value in extra.items() if key.lower() not in _SECRET_KEYS and _safe_value(value)}
    return ContextManifest(
        current_symbol=current_symbol.strip().upper() if current_symbol else None,
        cloud_watchlist_refs=tuple(dict.fromkeys(item.strip().upper() for item in cloud_watchlist_refs if item.strip())),
        risk_profile_ref=risk_profile_ref,
        market_snapshot_ref=market_snapshot_ref,
        local_files=tuple(refs),
        safe_attributes=safe,
    )


def _safe_value(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    if isinstance(value, list):
        return all(_safe_value(item) for item in value)
    if isinstance(value, dict):
        return all(key.lower() not in _SECRET_KEYS and _safe_value(item) for key, item in value.items())
    return False
