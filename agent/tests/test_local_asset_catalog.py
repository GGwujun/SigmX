from pathlib import Path

from src.harness.assets import LocalAssetCatalog


def test_local_asset_catalog_groups_files_without_reading_private_contents(tmp_path: Path) -> None:
    datasets = tmp_path / "data"
    reports = tmp_path / "reports"
    cache = tmp_path / "cache"
    for root in (datasets, reports, cache):
        root.mkdir()
    (datasets / "market.db").write_bytes(b"not-a-real-db")
    (reports / "quality-report.md").write_text("api_key=do-not-return", encoding="utf-8")
    (cache / "bars-20260815.parquet").write_bytes(b"parquet")

    catalog = LocalAssetCatalog({"dataset": datasets, "report": reports, "cache": cache})
    assets = catalog.list_assets()

    assert {item.kind for item in assets} == {"dataset", "report", "cache"}
    assert next(item for item in assets if item.name == "bars-20260815.parquet").version == "20260815"
    assert all("do-not-return" not in repr(item) for item in assets)
    assert catalog.summary().counts == {"dataset": 1, "report": 1, "cache": 1}


def test_local_asset_catalog_rejects_paths_outside_managed_roots(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    catalog = LocalAssetCatalog({"report": managed})

    assert catalog.resolve_asset("../secret.txt") is None
