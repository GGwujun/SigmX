"""Authenticated snapshot receiver for the remote read-only query deployment.

This process is a data-plane sidecar, not a market-data fetcher.  It accepts a
quality-gated SQLite snapshot from the standalone sync host, stages it in
ordered idempotent chunks, verifies it, and imports it using SQLite's backup
API so existing query-process connections remain valid.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import os
import re
import sqlite3
import threading
from contextlib import closing
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 << 20):
            digest.update(block)
    return digest.hexdigest()


class SnapshotManifest(BaseModel):
    snapshot_id: str = Field(min_length=8, max_length=96)
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    run_id: str = Field(min_length=1, max_length=128)
    published_at: str = Field(min_length=10, max_length=64)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compression: Literal["gzip"] = "gzip"


class SnapshotReceiver:
    def __init__(self, staging_dir: Path, live_db: Path, *, max_size_bytes: int = 4 << 30) -> None:
        self.staging_dir = Path(staging_dir)
        self.live_db = Path(live_db)
        self.max_size_bytes = int(max_size_bytes)
        self._lock = threading.RLock()

    @staticmethod
    def _safe_id(snapshot_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,95}", snapshot_id):
            raise ValueError("invalid snapshot_id")
        return snapshot_id

    def _part_path(self, snapshot_id: str) -> Path:
        return self.staging_dir / f"{self._safe_id(snapshot_id)}.part"

    def _manifest_path(self, snapshot_id: str) -> Path:
        return self.staging_dir / f"{self._safe_id(snapshot_id)}.json"

    def _load_manifest(self, snapshot_id: str) -> SnapshotManifest:
        path = self._manifest_path(snapshot_id)
        if not path.exists():
            raise ValueError("snapshot has not been started")
        return SnapshotManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def _already_committed(self, manifest: SnapshotManifest) -> bool:
        if not self.live_db.exists():
            return False
        try:
            with closing(sqlite3.connect(str(self.live_db), timeout=30)) as conn:
                row = conn.execute(
                    "SELECT value FROM sync_meta WHERE key = ?",
                    (f"ingest:snapshot:{manifest.snapshot_id}",),
                ).fetchone()
            return bool(row and hmac.compare_digest(str(row[0]), manifest.sha256))
        except sqlite3.Error:
            return False

    def start(self, manifest: SnapshotManifest) -> dict[str, Any]:
        self._safe_id(manifest.snapshot_id)
        if manifest.size_bytes > self.max_size_bytes:
            raise ValueError("snapshot exceeds configured maximum size")
        with self._lock:
            self.staging_dir.mkdir(parents=True, exist_ok=True)
            self.live_db.parent.mkdir(parents=True, exist_ok=True)
            if self._already_committed(manifest):
                return {"ok": True, "committed": True, "offset": manifest.size_bytes}
            manifest_path = self._manifest_path(manifest.snapshot_id)
            part_path = self._part_path(manifest.snapshot_id)
            if manifest_path.exists():
                existing = self._load_manifest(manifest.snapshot_id)
                if existing != manifest:
                    raise ValueError("snapshot_id already exists with a different manifest")
            else:
                manifest_path.write_text(manifest.model_dump_json(), encoding="utf-8")
            part_path.touch(exist_ok=True)
            offset = part_path.stat().st_size
            if offset > manifest.size_bytes:
                raise ValueError("staged snapshot is larger than manifest")
            return {"ok": True, "committed": False, "offset": offset}

    def write_chunk(self, snapshot_id: str, offset: int, payload: bytes) -> int:
        if offset < 0 or not payload:
            raise ValueError("chunk offset and payload are required")
        with self._lock:
            manifest = self._load_manifest(snapshot_id)
            path = self._part_path(snapshot_id)
            current = path.stat().st_size
            if offset < current:
                if offset + len(payload) > current:
                    raise ValueError("chunk overlaps the current offset")
                with path.open("rb") as staged:
                    staged.seek(offset)
                    if staged.read(len(payload)) != payload:
                        raise ValueError("replayed chunk content mismatch")
                return current
            if offset != current:
                raise ValueError(f"chunk offset mismatch: expected {current}, got {offset}")
            if current + len(payload) > manifest.size_bytes:
                raise ValueError("chunk exceeds declared snapshot size")
            with path.open("ab") as staged:
                staged.write(payload)
                staged.flush()
                os.fsync(staged.fileno())
            return current + len(payload)

    def commit(self, snapshot_id: str) -> dict[str, Any]:
        with self._lock:
            manifest = self._load_manifest(snapshot_id)
            if self._already_committed(manifest):
                return {"ok": True, "committed": True, "idempotent": True}
            packed = self._part_path(snapshot_id)
            if packed.stat().st_size != manifest.size_bytes:
                raise ValueError("snapshot size mismatch")
            digest = _sha256_file(packed)
            if not hmac.compare_digest(digest, manifest.sha256):
                raise ValueError("snapshot checksum mismatch")

            unpacked = self.staging_dir / f"{self._safe_id(snapshot_id)}.db"
            source_db: sqlite3.Connection | None = None
            try:
                with gzip.open(packed, "rb") as source, unpacked.open("wb") as target:
                    while block := source.read(4 << 20):
                        target.write(block)
                source_db = sqlite3.connect(
                    f"file:{unpacked.as_posix()}?mode=ro", uri=True, timeout=30
                )
                check = source_db.execute("PRAGMA integrity_check").fetchone()
                if not check or check[0] != "ok":
                    raise ValueError("snapshot SQLite integrity check failed")
                run = source_db.execute(
                    "SELECT status, trade_date, finished_at FROM sync_runs WHERE run_id = ?",
                    (manifest.run_id,),
                ).fetchone()
                if (
                    not run
                    or run[0] != "published"
                    or run[1] != manifest.trade_date
                    or str(run[2]) != manifest.published_at
                ):
                    raise ValueError("snapshot run is not published for the declared trade date")
                with closing(sqlite3.connect(str(self.live_db), timeout=60)) as target:
                    target.execute("PRAGMA busy_timeout=60000")
                    try:
                        latest = target.execute(
                            "SELECT trade_date, finished_at FROM sync_runs "
                            "WHERE status = 'published' "
                            "ORDER BY trade_date DESC, finished_at DESC LIMIT 1"
                        ).fetchone()
                    except sqlite3.OperationalError:
                        latest = None
                    if latest and (manifest.trade_date, manifest.published_at) < (
                        str(latest[0]), str(latest[1])
                    ):
                        raise ValueError("snapshot is older than the live published run")
                    source_db.backup(target, pages=2000, sleep=0.02)
                    target.execute(
                        "INSERT OR REPLACE INTO sync_meta (key, value, updated_at) "
                        "VALUES (?, ?, datetime('now'))",
                        (f"ingest:snapshot:{manifest.snapshot_id}", manifest.sha256),
                    )
                    target.commit()
            except (OSError, EOFError, sqlite3.Error) as exc:
                raise ValueError(f"invalid snapshot payload: {exc}") from exc
            finally:
                if source_db is not None:
                    source_db.close()
                try:
                    unpacked.unlink(missing_ok=True)
                except PermissionError:
                    # Windows can briefly retain a SQLite mapping after close;
                    # the next start/commit safely overwrites this staging file.
                    pass
            return {"ok": True, "committed": True, "idempotent": False}


def _default_receiver() -> SnapshotReceiver:
    return SnapshotReceiver(
        Path(os.getenv("MARKET_INGEST_STAGING_DIR", "/data/ingest")),
        Path(os.getenv("VIBE_TRADING_MARKET_DB_PATH", "/data/market.db")),
        max_size_bytes=int(os.getenv("MARKET_INGEST_MAX_SIZE_BYTES", str(4 << 30))),
    )


receiver = _default_receiver()
app = FastAPI(title="SigmX verified market snapshot receiver")


def require_ingest_token(x_market_ingest_token: str = Header(default="")) -> None:
    expected = os.getenv("MARKET_INGEST_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="market ingest token is not configured")
    if not hmac.compare_digest(x_market_ingest_token, expected):
        raise HTTPException(status_code=401, detail="invalid market ingest token")


def _http_error(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


@app.post("/snapshots/start", dependencies=[Depends(require_ingest_token)])
def start_snapshot(manifest: SnapshotManifest) -> dict[str, Any]:
    try:
        return receiver.start(manifest)
    except ValueError as exc:
        raise _http_error(exc) from exc


@app.put("/snapshots/{snapshot_id}/chunks", dependencies=[Depends(require_ingest_token)])
async def upload_chunk(
    snapshot_id: str,
    request: Request,
    offset: int = Query(ge=0),
) -> dict[str, Any]:
    try:
        return {"ok": True, "offset": receiver.write_chunk(snapshot_id, offset, await request.body())}
    except ValueError as exc:
        raise _http_error(exc) from exc


@app.post("/snapshots/{snapshot_id}/commit", dependencies=[Depends(require_ingest_token)])
def commit_snapshot(snapshot_id: str) -> dict[str, Any]:
    try:
        return receiver.commit(snapshot_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "role": "verified-snapshot-receiver"}
