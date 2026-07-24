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
        conn.execute("PRAGMA busy_timeout=10000")
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
        "mode": "full",
    }
    return packed, manifest


# Tables that are date-keyed (copied by trade_date slice). Must stay in sync
# with market_sync_worker._DATE_KEYED_TABLES. Whole/universe tables are tracked
# separately (security_master, trade_calendar) — only shipped when changed.
_DATE_KEYED_TABLES = (
    "bars_daily", "stock_daily_basic", "index_daily", "etf_daily", "fund_daily",
    "board_daily", "dragon_tiger", "stock_pool", "zt_pool", "zb_pool", "dt_pool",
    "yzt_pool", "ths_limit_up", "stock_capital_flow", "stock_capital_rank",
    "sector_capital_flow", "sector_snapshot", "sector_snapshot_industry",
    "sector_snapshot_concept", "market_breadth_snapshot", "market_stage_snapshot",
    "global_market_index_daily", "us_theme_snapshot", "premarket_news",
    "ths_hot_reason", "hot_list", "popularity_rank", "cls_telegraph", "stock_news",
    "fund_flow_daily", "margin_trading", "block_trade", "holder_num",
    "dividend_history", "lockup_expiry", "option_chain", "northbound_flow",
    "eps_forecast", "financial_snapshot", "financial_statement", "announcements",
    "fund_premium_snapshot", "us_a_share_transmission", "irm_qa",
)
# Universe tables: shipped whole, but only when their fingerprint changed since
# the last successful push (row count + max updated_at, recorded in sender-state).
_WHOLE_TABLES = ("security_master", "trade_calendar")


def _table_fingerprint(conn: sqlite3.Connection, table: str) -> tuple[int, str]:
    """Cheap change-detection fingerprint: (row_count, max(updated_at))."""
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except sqlite3.Error:
        return (0, "")
    upd = ""
    try:
        upd = str(conn.execute(f"SELECT MAX(updated_at) FROM {table}").fetchone()[0] or "")
    except sqlite3.Error:
        pass
    return (int(cnt or 0), upd)


def _load_whole_fingerprints(state_path: Path) -> dict[str, tuple[int, str]]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        wf = state.get("whole_fingerprints") or {}
        return {k: tuple(v) for k, v in wf.items()}  # type: ignore[return-value]
    except (OSError, ValueError, TypeError):
        return {}


def _save_whole_fingerprints(state_path: Path, fingerprints: dict[str, tuple[int, str]], sent_run_id: str) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sent_run_id": sent_run_id,
        "whole_fingerprints": {k: list(v) for k, v in fingerprints.items()},
        "updated_at": datetime.now(TZ_SH).isoformat(),
    }
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(state_path)


def build_incremental_snapshot(
    source_db: Path,
    output_dir: Path,
    run_id: str,
    state_path: Path,
) -> tuple[Path, dict[str, Any]]:
    """Build a small incremental package: only this run's tables + changed universe tables.

    Reads sync_dataset_runs for the run to know which datasets it wrote, maps
    them to tables, exports each date-keyed table's trade_date slice plus the
    run's sync_runs/sync_dataset_runs rows (validation-required) plus any
    changed whole tables. Ships a compact sqlite file instead of the full DB.
    """
    output_dir = Path(output_dir)
    raw = output_dir / "market.incremental.db"
    packed = output_dir / "market.incremental.db.gz"
    raw.unlink(missing_ok=True)

    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True, timeout=60)
    src.execute("PRAGMA busy_timeout=10000")
    src.row_factory = sqlite3.Row
    run_row = src.execute(
        "SELECT run_id, trade_date, status, finished_at FROM sync_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if not run_row or run_row["status"] != "published":
        raise RuntimeError(f"run {run_id} is not published")
    trade_date = run_row["trade_date"]
    published_at = str(run_row["finished_at"])

    # Create the compact incremental DB with the same schema, then copy rows.
    tgt = sqlite3.connect(str(raw))
    tgt.row_factory = sqlite3.Row

    tables_manifest: list[dict[str, Any]] = []

    def _copy_table(table: str, *, scope: str, td: str | None = None) -> None:
        try:
            if scope == "whole":
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
            else:
                rows = src.execute(
                    f"SELECT * FROM {table} WHERE trade_date = ?", (td or trade_date,)
                ).fetchall()
        except sqlite3.Error:
            return  # table absent in source — skip
        if not rows:
            return
        # Recreate table schema in target (CREATE TABLE LIKE via sqlite_schema).
        try:
            schema = src.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if schema and schema["sql"]:
                tgt.execute(schema["sql"])
                # Copy indexes too so the target is usable, though optional.
                for idx in src.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
                    (table,),
                ).fetchall():
                    try:
                        tgt.execute(idx["sql"])
                    except sqlite3.Error:
                        pass
                cols = [d[0] for d in src.execute(f"SELECT * FROM {table} LIMIT 0").description]
                collist = ",".join(cols)
                placeholders = ",".join("?" for _ in cols)
                tgt.executemany(
                    f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                    [tuple(r) for r in rows],
                )
                entry = {"name": table, "scope": scope}
                if scope == "date":
                    entry["trade_date"] = td or trade_date
                tables_manifest.append(entry)
        except sqlite3.Error:
            return

    # 1. Tables this run wrote (from sync_dataset_runs → table via dataset name).
    #    Also include a dataset→table fallback map for names not in _DATASET_TABLE.
    ds_rows = src.execute(
        "SELECT DISTINCT dataset FROM sync_dataset_runs WHERE run_id = ?", (run_id,)
    ).fetchall()
    _DATASET_TABLE = {
        "calendar": "trade_calendar", "master": "security_master",
        "index_master": "index_master", "board_master": "board_master",
        "board_members": "board_members", "daily": "bars_daily",
        "daily_basic": "stock_daily_basic", "index": "index_daily",
        "etf": "etf_daily", "etf_master": "etf_master", "fund_master": "fund_master",
        "fund_daily": "fund_daily", "etf_size": "etf_share_size",
        "dragon": "dragon_tiger", "pool": "stock_pool", "zt_pool": "zt_pool",
        "zb_pool": "zb_pool", "dt_pool": "dt_pool", "yzt_pool": "yzt_pool",
        "ths_hot": "ths_limit_up", "capital": "stock_capital_flow",
        "capital_rank": "stock_capital_rank", "sector_capital": "sector_capital_flow",
        "sector_snapshot": "sector_snapshot", "us_theme": "us_theme_snapshot",
        "us_transmission": "us_a_share_transmission", "premarket_news": "premarket_news",
        "stage_snapshot": "market_stage_snapshot", "premium": "fund_premium_snapshot",
        "board": "board_daily", "market_breadth": "market_breadth_snapshot",
        "global_indices": "global_market_index_daily", "hot_list": "hot_list",
        "eps_forecast": "eps_forecast", "financial_snapshot": "financial_snapshot",
        "financial_statement": "financial_statement", "announcements": "announcements",
        "fund_flow_daily": "fund_flow_daily", "option_chain": "option_chain",
        "margin_trading": "margin_trading", "block_trade": "block_trade",
        "holder_num": "holder_num", "dividend_history": "dividend_history",
        "northbound": "northbound_flow", "cls_telegraph": "cls_telegraph",
        "irm_qa": "irm_qa", "stock_news": "stock_news", "lockup_expiry": "lockup_expiry",
    }
    written_tables: set[str] = set()
    for dsr in ds_rows:
        table = _DATASET_TABLE.get(dsr["dataset"])
        if table and table in _DATE_KEYED_TABLES:
            _copy_table(table, scope="date")
            written_tables.add(table)

    # 2. Always carry the run's own sync_runs + sync_dataset_runs rows (receiver
    #    validates run identity + records dataset state from these).
    try:
        rr = src.execute("SELECT * FROM sync_runs WHERE run_id = ?", (run_id,)).fetchall()
        if rr:
            schema = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sync_runs'").fetchone()
            if schema and schema["sql"]:
                tgt.execute(schema["sql"])
                cols = [d[0] for d in src.execute("SELECT * FROM sync_runs LIMIT 0").description]
                placeholders = ",".join("?" for _ in cols)
                tgt.executemany(
                    f"INSERT OR REPLACE INTO sync_runs ({','.join(cols)}) VALUES ({placeholders})",
                    [tuple(r) for r in rr],
                )
    except sqlite3.Error:
        pass
    try:
        dr = src.execute("SELECT * FROM sync_dataset_runs WHERE run_id = ?", (run_id,)).fetchall()
        if dr:
            schema = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sync_dataset_runs'").fetchone()
            if schema and schema["sql"]:
                tgt.execute(schema["sql"])
                cols = [d[0] for d in src.execute("SELECT * FROM sync_dataset_runs LIMIT 0").description]
                placeholders = ",".join("?" for _ in cols)
                tgt.executemany(
                    f"INSERT OR REPLACE INTO sync_dataset_runs ({','.join(cols)}) VALUES ({placeholders})",
                    [tuple(r) for r in dr],
                )
    except sqlite3.Error:
        pass

    # 3. Whole tables — only if their fingerprint changed since last push.
    prev_fps = _load_whole_fingerprints(state_path)
    cur_fps: dict[str, tuple[int, str]] = {}
    for table in _WHOLE_TABLES:
        cur_fps[table] = _table_fingerprint(src, table)
        if cur_fps[table] != prev_fps.get(table):
            _copy_table(table, scope="whole")

    tgt.commit()
    tgt.close()
    src.close()

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
        "mode": "incremental",
        "tables": tables_manifest,
    }
    # Stash current whole-table fingerprints on the manifest-bearing object via
    # an attribute the caller can persist after a successful send.
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


def sync_once(expected_run_id: str | None = None, *, state_path: Path | None = None) -> dict[str, Any]:
    if not DB_PATH.exists():
        raise RuntimeError(f"market database does not exist: {DB_PATH}")
    full_mode = os.getenv("MARKET_SYNC_FULL_SNAPSHOT", "0") == "1"
    packed: Path
    manifest: dict[str, Any]
    new_whole_fps: dict[str, tuple[int, str]] | None = None
    if full_mode:
        packed, manifest = build_snapshot(DB_PATH, WORK_DIR)
    else:
        if not expected_run_id:
            # No run id available (shouldn't happen in the watcher loop) — fall
            # back to full snapshot.
            packed, manifest = build_snapshot(DB_PATH, WORK_DIR)
        else:
            sp = state_path or (WORK_DIR / "sender-state.json")
            packed, manifest = build_incremental_snapshot(DB_PATH, WORK_DIR, expected_run_id, sp)
            # Capture current whole-table fingerprints to persist on success.
            try:
                src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
                new_whole_fps = {t: _table_fingerprint(src, t) for t in _WHOLE_TABLES}
                src.close()
            except sqlite3.Error:
                new_whole_fps = None
    try:
        if expected_run_id and manifest["run_id"] != expected_run_id:
            raise RuntimeError(
                "published run changed while snapshot was being built; "
                f"expected={expected_run_id} actual={manifest['run_id']}"
            )
        log(
            f"upload snapshot={manifest['snapshot_id']} trade_date={manifest['trade_date']} "
            f"mode={manifest.get('mode', 'full')} tables={len(manifest.get('tables', []))} "
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
    state_path = watcher.state_path
    while True:
        try:
            run_id = watcher.next_run_id()
            if run_id:
                try:
                    sync_once(run_id, state_path=state_path)
                    watcher.mark_sent(run_id)
                    # After a successful incremental push, persist the current
                    # whole-table fingerprints so unchanged universe tables are
                    # skipped on subsequent pushes.
                    if not os.getenv("MARKET_SYNC_FULL_SNAPSHOT", "0") == "1":
                        try:
                            src = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
                            fps = {t: _table_fingerprint(src, t) for t in _WHOLE_TABLES}
                            src.close()
                            _save_whole_fingerprints(state_path, fps, run_id)
                        except sqlite3.Error:
                            pass
                except Exception as exc:  # noqa: BLE001
                    log(f"snapshot delivery failed and will retry run={run_id}: {exc}")
        except sqlite3.OperationalError as exc:
            # market-sync 正在写 market.db (DELETE journal 持锁), 读 sync_runs 拿不到锁。
            # 不能让进程崩溃 → docker 反复 restart。记日志, 下个 tick 重试。
            log(f"market.db busy ({exc}); will retry next tick")
        time.sleep(SYNC_INTERVAL)


if __name__ == "__main__":
    main()
