from __future__ import annotations

import gzip
import hashlib
import sqlite3
from pathlib import Path

import pytest

from src.data.data_ingest_server import SnapshotManifest, SnapshotReceiver
from src.data.market_quality import QualityStatus
from src.data.market_store import MarketStore


def _snapshot(tmp_path: Path, *, status: QualityStatus = QualityStatus.PUBLISHED) -> tuple[Path, str]:
    raw = tmp_path / "source.db"
    store = MarketStore(raw)
    run_id = store.create_sync_run("2026-07-14", worker_id="test")
    store.finish_sync_run(run_id, status)
    store.upsert_security_master(
        [{"code": "600000.SH", "name": "PF Bank", "list_status": "L"}]
    )
    store._conn.close()
    packed = tmp_path / "source.db.gz"
    with raw.open("rb") as source, gzip.open(packed, "wb") as target:
        target.write(source.read())
    return packed, run_id


def _manifest(path: Path, run_id: str) -> SnapshotManifest:
    payload = path.read_bytes()
    with sqlite3.connect(path.with_name("source.db")) as conn:
        published_at = conn.execute(
            "SELECT finished_at FROM sync_runs WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
    return SnapshotManifest(
        snapshot_id="20260714-deadbeef",
        trade_date="2026-07-14",
        run_id=run_id,
        published_at=published_at,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        compression="gzip",
    )


def test_chunk_upload_is_ordered_and_idempotent(tmp_path: Path) -> None:
    packed, run_id = _snapshot(tmp_path)
    manifest = _manifest(packed, run_id)
    receiver = SnapshotReceiver(tmp_path / "stage", tmp_path / "live.db")
    receiver.start(manifest)
    payload = packed.read_bytes()

    assert receiver.write_chunk(manifest.snapshot_id, 0, payload[:100]) == 100
    assert receiver.write_chunk(manifest.snapshot_id, 0, payload[:100]) == 100
    with pytest.raises(ValueError, match="offset"):
        receiver.write_chunk(manifest.snapshot_id, 101, payload[100:])


def test_commit_verifies_and_atomically_imports_snapshot(tmp_path: Path) -> None:
    packed, run_id = _snapshot(tmp_path)
    manifest = _manifest(packed, run_id)
    live = tmp_path / "live.db"
    receiver = SnapshotReceiver(tmp_path / "stage", live)
    receiver.start(manifest)
    receiver.write_chunk(manifest.snapshot_id, 0, packed.read_bytes())

    result = receiver.commit(manifest.snapshot_id)

    assert result["ok"] is True
    store = MarketStore(live)
    assert store._conn.execute(
        "SELECT name FROM security_master WHERE code='600000.SH'"
    ).fetchone()["name"] == "PF Bank"
    assert store.get_meta(f"ingest:snapshot:{manifest.snapshot_id}") == manifest.sha256
    assert not receiver._part_path(manifest.snapshot_id).exists()
    assert not receiver._manifest_path(manifest.snapshot_id).exists()


def test_commit_rejects_unpublished_or_corrupt_snapshot(tmp_path: Path) -> None:
    packed, run_id = _snapshot(tmp_path, status=QualityStatus.VERIFIED)
    manifest = _manifest(packed, run_id)
    receiver = SnapshotReceiver(tmp_path / "stage", tmp_path / "live.db")
    receiver.start(manifest)
    receiver.write_chunk(manifest.snapshot_id, 0, packed.read_bytes())
    with pytest.raises(ValueError, match="published"):
        receiver.commit(manifest.snapshot_id)

    corrupt = SnapshotManifest(**{**manifest.model_dump(), "snapshot_id": "20260714-bad", "sha256": "0" * 64})
    receiver.start(corrupt)
    receiver.write_chunk(corrupt.snapshot_id, 0, packed.read_bytes())
    with pytest.raises(ValueError, match="checksum"):
        receiver.commit(corrupt.snapshot_id)
