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
import socket
import time
from pathlib import Path
from typing import Iterable

from src.data.dataset_contracts import validate_dataset
from src.data.market_store import MarketStore
from src.data.dataset_registry import contract_for
from src.data.market_quality import (
    DatasetQualityReport,
    QualityStatus,
    ReferenceResult,
    validate_daily_dataset,
)
from src.data.market_sync import (
    _all_a_share_codes,
    _maybe_run_fund_premium_sync,
    _maybe_run_intraday_sync,
    _maybe_run_premarket_sync,
    _now_cst,
    _today_cst_str,
    fetch_daily_reference_closes,
    fetch_tdx_reference_closes,
    fetch_suspended_codes,
    run_daily_sync,
    select_daily_reference_sample,
)
from src.data.rate_limiter import mark_background, reset_background

# Provider calls from this worker must bypass system proxies.
for _key in list(os.environ):
    if "proxy" in _key.lower():
        os.environ.pop(_key, None)
os.environ.setdefault("NO_PROXY", "*")

logger = logging.getLogger(__name__)

_REALTIME_MIN_COVERAGE = float(os.getenv("MARKET_SYNC_REALTIME_MIN_COVERAGE", "0.90"))

_POST_CLOSE_DATASETS = {
    "calendar",
    "master",
    "index_master",
    "board_master",
    "board_members",
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
    # a-stock-data 扩展
    "ths_hot",
    "zt_pool",
    "hot_list",
    "eps_forecast",
    "financial_snapshot",
    "financial_statement",
    "announcements",
    "fund_flow_daily",
    "fund_flow_120d",
    "option_chain",
    "margin_trading",
    "block_trade",
    "holder_num",
    "dividend_history",
    "northbound",
    "cls_telegraph",
    "irm_qa",
    "stock_news",
    "lockup_expiry",
}

class MarketDataQualityError(RuntimeError):
    """Raised when a sync attempt cannot be proven safe to publish."""

    def __init__(self, report_or_message: DatasetQualityReport | str) -> None:
        self.report = report_or_message if isinstance(report_or_message, DatasetQualityReport) else None
        if self.report is not None:
            message = (
                f"{self.report.dataset} quality gate failed with {self.report.status.value}: "
                f"{', '.join(self.report.blocking_reasons)}"
            )
        else:
            message = str(report_or_message)
        super().__init__(message)


def _semantic_rows(
    store: MarketStore,
    dataset: str,
    trade_date: str,
) -> list[dict] | None:
    """Read critical rows back from the shadow DB for semantic validation."""
    if dataset == "realtime":
        return store.get_realtime_quotes(trade_date, limit=10000)
    if dataset == "capital_rank":
        rows = []
        for rank_type in ("inflow", "outflow"):
            for row in store.get_stock_capital_rank(trade_date, rank_type, limit=500):
                rows.append({**row, "code": row.get("symbol"), "rank_type": rank_type})
        return rows
    if dataset == "sector_capital":
        return store.get_sector_capital(trade_date, limit=500)
    if dataset == "market_breadth":
        row = store.get_market_breadth_snapshot(trade_date)
        return [row] if row else []
    if dataset == "master":
        # security_master is a trade-date-independent universe table; validate a
        # sample so corruption (null/placeholder rows) is caught even though the
        # row count alone would pass.
        return store.list_security_master()[:5000]
    if dataset == "board_members":
        rows = store._conn.execute(
            "SELECT board_code, board_type, stock_code, stock_name, stock_exchange "
            "FROM board_members ORDER BY board_code LIMIT 5000"
        ).fetchall()
        return [dict(r) for r in rows]
    return None


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


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
        live_store._conn.close()
        return {}
    live_store._conn.close()

    logger.info("post-close shadow sync preparing %s -> %s", live_db, shadow_db)
    _prepare_shadow(live_db, shadow_db)
    shadow_store = MarketStore(shadow_db)
    run_id = shadow_store.create_sync_run(trade_date, worker_id=_worker_id())
    universe = os.getenv("MARKET_SYNC_POSTCLOSE_UNIVERSE", "all")
    expected_codes = (
        _all_a_share_codes(shadow_store, default_only=(universe == "default"))
        if "daily" in datasets
        else []
    )
    try:
        rows = run_daily_sync(
            trade_date,
            store=shadow_store,
            codes=expected_codes if "daily" in datasets else None,
            datasets=datasets,
            universe=universe,
            deadline_seconds=deadline_seconds,
            lookback_days=lookback_days,
            sync_run_id=run_id,
        )
        missing_results = sorted(datasets - rows.keys())
        if missing_results:
            raise MarketDataQualityError(
                f"missing dataset results after sync: {', '.join(missing_results)}"
            )

        failed_contracts: list[str] = []
        reported_datasets = (datasets | set(rows)) - {"daily"}
        for dataset in sorted(reported_datasets):
            received = max(int(rows.get(dataset, 0)), 0)
            contract = contract_for(dataset)
            minimum = contract.minimum_rows
            valid_rows = received
            reasons: list[str] = []
            try:
                semantic_rows = _semantic_rows(shadow_store, dataset, trade_date)
                if semantic_rows is not None:
                    validation = validate_dataset(
                        dataset,
                        semantic_rows,
                        trade_date=trade_date,
                    )
                    valid_rows = len(validation.rows)
                    reasons.extend(validation.reasons)
            except Exception as exc:  # noqa: BLE001
                valid_rows = 0
                reasons.append(f"semantic_validation_error:{exc}")
            expected_rows = minimum
            if dataset == "realtime":
                active_rows = shadow_store._conn.execute(
                    "SELECT COUNT(*) FROM security_master WHERE list_status = 'L'"
                ).fetchone()
                active_codes = int(active_rows[0] or 0) if active_rows else 0
                coverage_minimum = int(active_codes * _REALTIME_MIN_COVERAGE + 0.999999)
                expected_rows = max(minimum, coverage_minimum)
                if active_codes and valid_rows < coverage_minimum:
                    reasons.append("realtime_universe_coverage_below_threshold")
            if valid_rows < minimum:
                reasons.append("row_count_below_minimum")
            reasons = list(dict.fromkeys(reasons))
            status = QualityStatus.PARTIAL if reasons else QualityStatus.VERIFIED
            shadow_store.record_dataset_result(
                run_id,
                DatasetQualityReport(
                    dataset=dataset,
                    trade_date=trade_date,
                    status=status,
                    expected_rows=expected_rows,
                    received_rows=received,
                    valid_rows=valid_rows,
                    blocking_reasons=reasons,
                    source="configured-provider-chain",
                ),
            )
            # A blocking contract fails the run on any degradation.  An
            # advisory contract only fails the run when the provider returned
            # rows but every one was rejected as corrupt — coverage shortfall or
            # an empty result degrades (PARTIAL + readiness) but still publishes.
            corrupt = received > 0 and valid_rows == 0
            if reasons and (contract.blocking or (contract.hard_fail_on_zero_valid and corrupt)):
                failed_contracts.append(
                    f"{dataset} received={received} valid={valid_rows} minimum={minimum}"
                )

        if failed_contracts:
            shadow_store.finish_sync_run(
                run_id,
                QualityStatus.PARTIAL,
                error_summary="; ".join(failed_contracts),
            )
            raise MarketDataQualityError(
                "blocking dataset quality contracts failed: " + "; ".join(failed_contracts)
            )

        if "daily" in datasets:
            received_codes = set(shadow_store.daily_codes_for_run(trade_date, run_id))
            suspension_result = fetch_suspended_codes(
                trade_date,
                sorted(set(expected_codes) - received_codes),
            )
            active_expected = set(expected_codes)
            if suspension_result.available:
                active_expected -= set(suspension_result.codes)
            daily_rows = shadow_store.daily_rows_for_run(trade_date, run_id)
            tushare_codes = [
                str(row["code"])
                for row in daily_rows
                if row.get("source") == "tushare.daily"
            ]
            fallback_codes = [
                str(row["code"])
                for row in daily_rows
                if str(row.get("source") or "").startswith("tpdog.")
            ]
            reference_sample = select_daily_reference_sample(tushare_codes, seed=trade_date)
            if active_expected and not reference_sample and not fallback_codes:
                reference_result = ReferenceResult.unavailable(
                    "no independent reference sample for active daily universe"
                )
            else:
                reference_result = fetch_daily_reference_closes(trade_date, reference_sample)
            fallback_reference_result = fetch_tdx_reference_closes(
                trade_date,
                sorted(set(fallback_codes)),
            )
            report = validate_daily_dataset(
                shadow_store,
                trade_date,
                expected_codes,
                run_id,
                suspension_result=suspension_result,
                reference_result=reference_result,
                fallback_reference_result=fallback_reference_result,
            )
            shadow_store.record_dataset_result(run_id, report)
            if report.status is not QualityStatus.VERIFIED:
                shadow_store.finish_sync_run(
                    run_id,
                    report.status,
                    error_summary="; ".join(report.blocking_reasons),
                )
                raise MarketDataQualityError(report)
        shadow_store.finish_sync_run(run_id, QualityStatus.VERIFIED)
    except Exception as exc:
        run_row = shadow_store._conn.execute(
            "SELECT status FROM sync_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run_row and run_row["status"] in {
            QualityStatus.PENDING.value,
            QualityStatus.FETCHING.value,
            QualityStatus.VALIDATING.value,
        }:
            shadow_store.finish_sync_run(run_id, QualityStatus.FAILED, error_summary=str(exc))
        shadow_store._conn.close()
        raise

    if not _integrity_ok(shadow_db):
        shadow_store.finish_sync_run(
            run_id,
            QualityStatus.FAILED,
            error_summary="shadow DB integrity check failed",
        )
        shadow_store._conn.close()
        raise RuntimeError(f"shadow DB integrity check failed: {shadow_db}")
    shadow_store._conn.close()
    logger.info("post-close shadow sync publishing %s rows=%s", trade_date, rows)
    _publish_shadow(shadow_db, live_db)
    published_store = MarketStore(live_db)
    if "daily" in datasets and not published_store.get_data_readiness("bars_daily", trade_date).ready:
        published_store._conn.close()
        raise RuntimeError("post-publication readiness verification failed")
    published_store.finish_sync_run(run_id, QualityStatus.PUBLISHED)
    published_store.set_meta(meta_key, _now_cst().isoformat())
    published_store._conn.close()
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
    if not shadow:
        raise ValueError("shadow publication is mandatory for canonical market data")
    return _run_post_close_shadow_sync(
        day,
        live_db=live_db,
        shadow_db=_shadow_db_path(live_db),
        datasets=ds,
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
            shadow=True,
            deadline_seconds=args.deadline,
            lookback_days=args.lookback_days,
        )
        print(rows)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
