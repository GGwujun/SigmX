"""Metadata-only catalog for user-controlled local Financial Harness assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class LocalAsset:
    id: str
    kind: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    version: str | None
    local_only: bool = True


@dataclass(frozen=True)
class LocalAssetSummary:
    counts: dict[str, int]
    total_size_bytes: int
    latest_modified_at: str | None


class LocalAssetCatalog:
    def __init__(self, roots: dict[str, Path]) -> None:
        self.roots = {kind: Path(root).resolve() for kind, root in roots.items()}

    def list_assets(self, *, kind: str | None = None, query: str | None = None) -> list[LocalAsset]:
        items: list[LocalAsset] = []
        needle = (query or "").strip().casefold()
        for asset_kind, root in self.roots.items():
            if kind and kind != asset_kind or not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or (needle and needle not in path.name.casefold()):
                    continue
                stat = path.stat()
                relative = path.relative_to(root).as_posix()
                version_match = re.search(r"(?<!\d)(20\d{6})(?!\d)", path.name)
                items.append(LocalAsset(
                    id=f"{asset_kind}:{relative}", kind=asset_kind, name=path.name,
                    extension=path.suffix.lower().lstrip("."), size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    version=version_match.group(1) if version_match else None,
                ))
        return sorted(items, key=lambda item: (item.modified_at, item.name), reverse=True)

    def summary(self) -> LocalAssetSummary:
        assets = self.list_assets()
        counts = {kind: 0 for kind in self.roots}
        for item in assets:
            counts[item.kind] = counts.get(item.kind, 0) + 1
        return LocalAssetSummary(
            counts=counts, total_size_bytes=sum(item.size_bytes for item in assets),
            latest_modified_at=max((item.modified_at for item in assets), default=None),
        )

    def resolve_asset(self, asset_id: str) -> Path | None:
        if ":" in asset_id:
            kind, relative = asset_id.split(":", 1)
        elif len(self.roots) == 1:
            kind, relative = next(iter(self.roots)), asset_id
        else:
            return None
        root = self.roots.get(kind)
        if root is None:
            return None
        candidate = (root / relative).resolve()
        if candidate == root or root not in candidate.parents or not candidate.is_file():
            return None
        return candidate
