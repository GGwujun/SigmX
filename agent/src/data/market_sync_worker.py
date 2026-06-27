"""Standalone market-data sync worker.

Run this outside the API server process so long market-data backfills cannot
block web requests. Intraday ticks write only small snapshot tables to the live
DB. Post-close syncs use a shadow DB first, then publish the verified result
back to the live DB with SQLite's backup API.
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from src.data.market_store import MarketStore
from src.data.market_sync import (
    _maybe_run_fund_premium_sync,
    _maybe_run_intraday_sync,
    _maybe_run_premarket_sync,
    _now_cst,
    _today_cst_str,
    run_daily_sync,
)
from src.data.rate_limiter import mark_background, reset_background

logger = logging.getLogger(__name__)

_POST_CLOSE_DATASETS = {
    "calendar",
    "master",
    "index_master",
    "board_master",
    "daily",
    "daily_basic",
    "dragon",
    "pool",
    "etf",
    "fund_daily",
    "etf_master",
    "fund_master",
    "etf_size",
    "index",
    "board",
    "capital",
    "capital_rank",
    "sector_capital",
    "sector_snapshot",
    "market_breadth",
    "global_indices",
    "us_theme",
    "us_transmission",
    "premarket_news",
    "stage_snapshot",
    "premium",
}


def _default_live_db() -> Path:
    env = os.getenv("VIBE_TRADING_MARKET_DB_PATH", "").strip()
    return Path(env) if env else Path.home() / ".vibe-trading" / "market.db"


def _shadow_db_path(live_db: Path) -> Path:
    env = os.getenv("VIBE_TRADING_MARKET_SHADOW_DB_PATH", "").strip()
    if env:
        return Path(env)
    return live_db.with_name(f"{live_db.stem}.shadow{live_db.suffix}")


def _parse_datasets(value: str | None, default: set[str]) -> set[str]:
    if not value:
        return set(default)
    return {part.strip() for part in value.split(",") if part.strip()}


def _sqlite_backup(src: Path, dst: Path, *, pages: int = 1000, sleep: float = 0.02) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30) as source:
        with sqlite3.connect(str(dst), timeout=30) as target:
            source.backup(target, pages=pages, sleep=sleep)


def _prepare_shadow(live_db: Path, shadow_db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(shadow_db) + suffix)
        if path.exists():
            path.unlink()
    if live_db.exists():
        _sqlite_backup(live_db, shadow_db)
    else:
        MarketStore(shadow_db)


def _publish_shadow(shadow_db: Path, live_db: Path) -> None:
    """Copy the verified shadow DB into the live DB with a short write phase."""
    live_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True, timeout=30) as source:
        with sqlite3.connect(str(live_db), timeout=30) as target:
            target.execute("PRAGMA busy_timeout=30000")
            source.backup(target, pages=1000, sleep=0.02)


def _integrity_ok(db_path: Path) -> bool:
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")


def _run_post_close_shadow_sync(
    trade_date: str,
    *,
    live_db: Path,
    shadow_db: Path,
    datasets: set[str],
    deadline_seconds: int,
    lookback_days: int,
) -> dict[str, int]:
    live_store = MarketStore(live_db)
    meta_key = f"daemon:{trade_date}"
    if live_store.get_meta(meta_key):
        return {}

    logger.info("post-close shadow sync preparing %s -> %s", live_db, shadow_db)
    _prepare_shadow(live_db, shadow_db)
    shadow_store = MarketStore(shadow_db)
    rows = run_daily_sync(
        trade_date,
        store=shadow_store,
        datasets=datasets,
        universe=os.getenv("MARKET_SYNC_POSTCLOSE_UNIVERSE", "all"),
        deadline_seconds=deadline_seconds,
        lookback_days=lookback_days,
    )
    shadow_store.set_meta(meta_key, _now_cst().isoformat())
    if not _integrity_ok(shadow_db):
        raise RuntimeError(f"shadow DB integrity check failed: {shadow_db}")
    logger.info("post-close shadow sync publishing %s rows=%s", trade_date, rows)
    _publish_shadow(shadow_db, live_db)
    return rows


def run_once(
    *,
    trade_date: str | None = None,
    datasets: Iterable[str] | None = None,
    shadow: bool = True,
    deadline_seconds: int = 3600,
    lookback_days: int = 365,
) -> dict[str, int]:
    """Run one operator-triggered sync outside the API process."""
    live_db = _default_live_db()
    ds = set(datasets) if datasets is not None else set(_POST_CLOSE_DATASETS)
    day = trade_date or _today_cst_str()
    if shadow:
        return _run_post_close_shadow_sync(
            day,
            live_db=live_db,
            shadow_db=_shadow_db_path(live_db),
            datasets=ds,
            deadline_seconds=deadline_seconds,
            lookback_days=lookback_days,
        )
    return run_daily_sync(
        day,
        store=MarketStore(live_db),
        datasets=ds,
        universe=os.getenv("MARKET_SYNC_POSTCLOSE_UNIVERSE", "all"),
        deadline_seconds=deadline_seconds,
        lookback_days=lookback_days,
    )


def run_worker(interval_seconds: int = 60) -> None:
    """Long-running worker loop for Docker/systemd."""
    token = mark_background(True)
    live_db = _default_live_db()
    live_store = MarketStore(live_db)
    try:
        while True:
            try:
                _maybe_run_premarket_sync(live_store)
                _maybe_run_intraday_sync(live_store)
                _maybe_run_fund_premium_sync(live_store)

                from src.data.trade_calendar import cn_market_phase

                if cn_market_phase() == "post_close":
                    datasets = _parse_datasets(
                        os.getenv("MARKET_SYNC_POSTCLOSE_DATASETS"),
                        _POST_CLOSE_DATASETS,
                    )
                    _run_post_close_shadow_sync(
                        _today_cst_str(),
                        live_db=live_db,
                        shadow_db=_shadow_db_path(live_db),
                        datasets=datasets,
                        deadline_seconds=int(os.getenv("MARKET_SYNC_POSTCLOSE_DEADLINE", "3600")),
                        lookback_days=int(os.getenv("MARKET_SYNC_POSTCLOSE_LOOKBACK_DAYS", "365")),
                    )
            except Exception:
                logger.exception("market sync worker tick failed")
            time.sleep(interval_seconds)
    finally:
        reset_background(token)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vibe-Trading market sync worker")
    sub = parser.add_subparsers(dest="command")

    worker = sub.add_parser("worker", help="Run the long-lived sync worker")
    worker.add_argument("--interval", type=int, default=int(os.getenv("MARKET_SYNC_WORKER_INTERVAL", "60")))

    once = sub.add_parser("once", help="Run one sync and exit")
    once.add_argument("--date", default="")
    once.add_argument("--datasets", default="")
    once.add_argument("--no-shadow", action="store_true")
    once.add_argument("--deadline", type=int, default=3600)
    once.add_argument("--lookback-days", type=int, default=365)

    args = parser.parse_args(argv)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

    if args.command == "worker":
        run_worker(interval_seconds=args.interval)
        return 0
    if args.command == "once":
        rows = run_once(
            trade_date=args.date or None,
            datasets=_parse_datasets(args.datasets, _POST_CLOSE_DATASETS) if args.datasets else None,
            shadow=not args.no_shadow,
            deadline_seconds=args.deadline,
            lookback_days=args.lookback_days,
        )
        print(rows)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
