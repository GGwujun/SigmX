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


def test_nested_product_roots_deduplicate_react_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    config = (root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert 'dedupe: ["react", "react-dom"]' in config


def test_product_api_namespace_is_proxied_to_backend() -> None:
    root = Path(__file__).resolve().parents[2]
    config = (root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert '"/api"' in config
