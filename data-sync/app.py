"""Ship quality-gated SQLite snapshots from the sync host to production.

The producer never exports table-shaped JSON or maintains per-table date
watermarks.  A consistent SQLite backup captures every current and future
schema, is compressed, chunked, checksummed, resumable, and committed by the
remote receiver only when its sync run is already marked ``published``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

for _key in list(os.environ):
    if "proxy" in _key.lower():
        os.environ.pop(_key, None)
os.environ.setdefault("NO_PROXY", "*")

DB_PATH = Path(os.getenv("DB_PATH", "/data/market.db"))
SERVER_URL = os.getenv("SERVER_URL", "").rstrip("/")
INGEST_TOKEN = os.getenv("MARKET_INGEST_TOKEN", "").strip()
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL", "30"))
CHUNK_BYTES = int(os.getenv("SNAPSHOT_CHUNK_BYTES", str(4 << 20)))
WORK_DIR = Path(os.getenv("SNAPSHOT_WORK_DIR", "/tmp/sigmx-data-sync"))
SYNC_LOG_PATH = Path(os.getenv("SYNC_LOG_PATH", "/data/sync.log"))
PUSH_SLOTS = tuple(
    slot.strip() for slot in os.getenv("SNAPSHOT_PUSH_SLOTS", "09:26,14:29,15:20").split(",")
    if slot.strip()
)
TZ_SH = timezone(timedelta(hours=8))


def log(message: str) -> None:
    line = f"[{datetime.now(TZ_SH):%Y-%m-%d %H:%M:%S}] {message}"
    print(line, flush=True)
    # Persist to disk so failures are observable without attaching to the
    # container's stdout.  A write failure must never kill the sync loop.
    try:
        SYNC_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SYNC_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 << 20):
            digest.update(block)
    return digest.hexdigest()


def _consistent_backup(source_path: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    with closing(sqlite3.connect(
        f"file:{source_path.as_posix()}?mode=ro", uri=True, timeout=60
    )) as source:
        with closing(sqlite3.connect(str(destination), timeout=60)) as target:
            source.backup(target, pages=2000, sleep=0.02)


def _latest_published_run(snapshot_db: Path) -> tuple[str, str, str]:
    with closing(sqlite3.connect(str(snapshot_db), timeout=30)) as conn:
        row = conn.execute(
            "SELECT run_id, trade_date, status, finished_at FROM sync_runs "
            "ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        check = conn.execute("PRAGMA integrity_check").fetchone()
    if not check or check[0] != "ok":
        raise RuntimeError("local snapshot failed SQLite integrity check")
    if not row or row[2] != "published":
        raise RuntimeError("latest local sync run is not published; refusing snapshot delivery")
    return str(row[0]), str(row[1]), str(row[3])


def _published_run_id(source_db: Path) -> str | None:
    if not Path(source_db).exists():
        return None
    with closing(sqlite3.connect(
        f"file:{Path(source_db).as_posix()}?mode=ro", uri=True, timeout=10
    )) as conn:
        row = conn.execute(
            "SELECT run_id, status FROM sync_runs ORDER BY started_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return str(row[0]) if row and row[1] == "published" else None


class PublishedRunWatcher:
    """Emit each newly published run once, independent of wall-clock slots."""

    def __init__(self, source_db: Path, state_path: Path | None = None) -> None:
        self.source_db = Path(source_db)
        self.state_path = Path(state_path or (WORK_DIR / "sender-state.json"))
        self._sent_run_id: str | None = None
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._sent_run_id = str(state.get("sent_run_id") or "") or None
        except (OSError, ValueError, TypeError):
            self._sent_run_id = None

    def next_run_id(self) -> str | None:
        run_id = _published_run_id(self.source_db)
        return run_id if run_id and run_id != self._sent_run_id else None

    def mark_sent(self, run_id: str) -> None:
        self._sent_run_id = run_id
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"sent_run_id": run_id, "updated_at": datetime.now(TZ_SH).isoformat()}),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)


def build_snapshot(source_db: Path, output_dir: Path) -> tuple[Path, dict[str, Any]]:
    output_dir = Path(output_dir)
    raw = output_dir / "market.snapshot.db"
    packed = output_dir / "market.snapshot.db.gz"
    _consistent_backup(Path(source_db), raw)
    run_id, trade_date, published_at = _latest_published_run(raw)

    with raw.open("rb") as source, packed.open("wb") as raw_target:
        with gzip.GzipFile(fileobj=raw_target, mode="wb", filename="", mtime=0) as target:
            while block := source.read(4 << 20):
                target.write(block)
    raw.unlink(missing_ok=True)
    digest = _sha256_file(packed)
    manifest = {
        "snapshot_id": f"{trade_date.replace('-', '')}-{digest[:24]}",
        "trade_date": trade_date,
        "run_id": run_id,
        "published_at": published_at,
        "size_bytes": packed.stat().st_size,
        "sha256": digest,
        "compression": "gzip",
    }
    return packed, manifest


class SnapshotClient:
    def __init__(self, server_url: str, token: str, *, timeout: int = 120) -> None:
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: bytes, content_type: str) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.server_url}{path}",
            data=payload,
            method=method,
            headers={
                "Content-Type": content_type,
                "X-Market-Ingest-Token": self.token,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"receiver HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"receiver unavailable: {exc}") from exc

    def send(self, packed: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        start = self._request(
            "POST",
            "/snapshots/start",
            json.dumps(manifest, separators=(",", ":")).encode("utf-8"),
            "application/json",
        )
        if start.get("committed"):
            return start
        offset = int(start.get("offset", 0))
        snapshot_id = urllib.parse.quote(str(manifest["snapshot_id"]), safe="")
        with packed.open("rb") as source:
            source.seek(offset)
            while chunk := source.read(CHUNK_BYTES):
                result = self._request(
                    "PUT",
                    f"/snapshots/{snapshot_id}/chunks?offset={offset}",
                    chunk,
                    "application/octet-stream",
                )
                next_offset = int(result.get("offset", -1))
                if next_offset != offset + len(chunk):
                    raise RuntimeError(
                        f"receiver returned invalid offset {next_offset}; expected {offset + len(chunk)}"
                    )
                offset = next_offset
        return self._request(
            "POST",
            f"/snapshots/{snapshot_id}/commit",
            b"{}",
            "application/json",
        )


def sync_once(expected_run_id: str | None = None) -> dict[str, Any]:
    if not DB_PATH.exists():
        raise RuntimeError(f"market database does not exist: {DB_PATH}")
    packed, manifest = build_snapshot(DB_PATH, WORK_DIR)
    try:
        if expected_run_id and manifest["run_id"] != expected_run_id:
            raise RuntimeError(
                "published run changed while snapshot was being built; "
                f"expected={expected_run_id} actual={manifest['run_id']}"
            )
        log(
            f"upload snapshot={manifest['snapshot_id']} trade_date={manifest['trade_date']} "
            f"compressed={manifest['size_bytes']}"
        )
        result = SnapshotClient(SERVER_URL, INGEST_TOKEN).send(packed, manifest)
        log(f"snapshot committed: {result}")
        return result
    finally:
        packed.unlink(missing_ok=True)


def main() -> None:
    log("SigmX verified snapshot sender started")
    log(f"DB={DB_PATH} receiver={SERVER_URL} delivery_deadlines={','.join(PUSH_SLOTS)}")
    if not SERVER_URL or not INGEST_TOKEN:
        raise SystemExit("SERVER_URL and MARKET_INGEST_TOKEN are required")
    watcher = PublishedRunWatcher(DB_PATH)
    # Heartbeat: write a line to sync.log at least this often so a Docker
    # healthcheck can tell a live-but-idle loop from a frozen one. Backs off
    # exponentially on repeated failures (capped) so a long server outage does
    # not re-pack+re-upload the whole DB every SYNC_INTERVAL seconds.
    heartbeat_every = max(SYNC_INTERVAL * 2, 60)
    last_heartbeat = 0.0
    backoff = SYNC_INTERVAL
    max_backoff = 900  # 15 minutes
    while True:
        now = time.time()
        run_id = watcher.next_run_id()
        if run_id:
            try:
                sync_once(run_id)
                watcher.mark_sent(run_id)
                backoff = SYNC_INTERVAL  # reset on success
            except Exception as exc:  # noqa: BLE001
                log(f"snapshot delivery failed and will retry run={run_id}: {exc}")
                # Exponential backoff with a cap; avoids hammering the receiver
                # (and re-running the full sqlite backup + gzip) when it is down.
                sleep_for = min(backoff, max_backoff)
                log(f"backing off {sleep_for}s before next attempt")
                time.sleep(sleep_for)
                backoff = min(backoff * 2, max_backoff)
                continue
        elif now - last_heartbeat >= heartbeat_every:
            log(f"heartbeat: no new published run; next check in {SYNC_INTERVAL}s")
            last_heartbeat = now
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
