from pathlib import Path

from src.product.frontend_build import resolve_frontend_dist


def test_cloud_runtime_serves_only_web_product_build(tmp_path: Path) -> None:
    assert resolve_frontend_dist(tmp_path, desktop_mode=False, override=None) == tmp_path / "frontend" / "dist" / "web"


def test_desktop_runtime_serves_only_desktop_product_build(tmp_path: Path) -> None:
    assert resolve_frontend_dist(tmp_path, desktop_mode=True, override=None) == tmp_path / "frontend" / "dist" / "desktop"


def test_explicit_frontend_override_wins_for_both_products(tmp_path: Path) -> None:
    override = tmp_path / "release" / "renderer"
    assert resolve_frontend_dist(tmp_path, desktop_mode=True, override=override) == override
    assert resolve_frontend_dist(tmp_path, desktop_mode=False, override=override) == override
