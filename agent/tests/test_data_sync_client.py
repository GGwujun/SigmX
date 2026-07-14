from __future__ import annotations

import gzip
import importlib.util
import sqlite3
from pathlib import Path

import pytest

from src.data.market_quality import QualityStatus
from src.data.market_store import MarketStore


def _load_module():
    path = Path(__file__).parents[2] / "data-sync" / "app.py"
    spec = importlib.util.spec_from_file_location("sigmx_data_sync", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_snapshot_uses_consistent_backup_and_published_run(tmp_path: Path) -> None:
    module = _load_module()
    db = tmp_path / "market.db"
    store = MarketStore(db)
    run_id = store.create_sync_run("2026-07-14", worker_id="test")
    store.finish_sync_run(run_id, QualityStatus.PUBLISHED)
    store.upsert_security_master([{"code": "600000.SH", "name": "A", "list_status": "L"}])

    packed, manifest = module.build_snapshot(db, tmp_path / "out")

    assert manifest["run_id"] == run_id
    assert manifest["trade_date"] == "2026-07-14"
    unpacked = tmp_path / "unpacked.db"
    with gzip.open(packed, "rb") as source, unpacked.open("wb") as target:
        target.write(source.read())
    with sqlite3.connect(unpacked) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM security_master").fetchone()[0] == 1


def test_build_snapshot_refuses_unpublished_database(tmp_path: Path) -> None:
    module = _load_module()
    db = tmp_path / "market.db"
    store = MarketStore(db)
    store.create_sync_run("2026-07-14", worker_id="test")
    store._conn.close()

    with pytest.raises(RuntimeError, match="published"):
        module.build_snapshot(db, tmp_path / "out")


def test_newer_partial_run_blocks_delivery_of_older_published_run(tmp_path: Path) -> None:
    module = _load_module()
    db = tmp_path / "market.db"
    store = MarketStore(db)
    good = store.create_sync_run("2026-07-13", worker_id="test")
    store.finish_sync_run(good, QualityStatus.PUBLISHED)
    bad = store.create_sync_run("2026-07-14", worker_id="test")
    store.finish_sync_run(bad, QualityStatus.PARTIAL, error_summary="hot_list empty")
    store._conn.close()

    with pytest.raises(RuntimeError, match="latest.*not published"):
        module.build_snapshot(db, tmp_path / "out")
