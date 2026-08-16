"""Resolve the renderer artifact for each independently built product."""

from pathlib import Path


def resolve_frontend_dist(
    repository_root: Path,
    *,
    desktop_mode: bool,
    override: Path | None,
) -> Path:
    if override is not None:
        return override
    product = "desktop" if desktop_mode else "web"
    return repository_root / "frontend" / "dist" / product
