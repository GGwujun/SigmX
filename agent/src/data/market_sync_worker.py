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
    _data_integrity_check,
    _maybe_run_fund_premium_sync,
    _maybe_run_index_history_sync,
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


def _settled_trade_date(store=None) -> str:
    """The latest trading day whose close has actually settled, as of now.

    Strict time semantics: data must be written under its real trade date, never
    under "today" when today hasn't produced a bar yet. Before 15:05 CST this is
    the prior trading day; from 15:05 onward it's today (if a trading day).
    Prevents post_close (which spans overnight — 15:00→next 09:30) from writing
    an empty snapshot under a not-yet-traded date (e.g. 00:50 on day N+1 must
    still target day N, not N+1 which has no data yet).

    Tries the akshare (sina) calendar first, then the persisted trade_calendar
    table (db) as fallback, then today as last resort.
    """
    try:
        from src.data.trade_calendar import expected_settled_date

        d = expected_settled_date()
        if d:
            return d
    except Exception:  # noqa: BLE001
        pass
    if store is not None:
        try:
            from src.data.market_sync import _now_cst
            from datetime import timedelta

            now = _now_cst()
            cutoff = now.date().isoformat()
            if now.hour < 15 or (now.hour == 15 and now.minute < 5):
                cutoff = (now.date() - timedelta(days=1)).isoformat()
            row = store._conn.execute(  # noqa: SLF001
                "SELECT MAX(trade_date) AS d FROM trade_calendar "
                "WHERE market = 'CN' AND is_trading = 1 AND trade_date <= ?",
                (cutoff,),
            ).fetchone()
            if row and row["d"]:
                return str(row["d"])
        except Exception:  # noqa: BLE001
            pass
    return _today_cst_str()


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

# Tier-1 datasets: the day's core snapshot. Validated and published FIRST so the
# live DB has a usable universe even if a slow/stalled enhanced dataset (e.g.
# akshare fund-flow) hasn't finished. Mirrors _CRITICAL (calendar/master/
# daily_basic/index) plus `daily`, which has its own dedicated reference check.
# Everything else in _POST_CLOSE_DATASETS is Tier-2 (enhanced) and publishes
# after the core. See plan step ⑤.
_POST_CLOSE_CORE = {
    "calendar",
    "master",
    "daily_basic",
    "index",
    "daily",
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


def _prepare_shadow(live_db: Path, shadow_db: Path) -> None:
    """Ensure the shadow DB exists; reuse it across cycles.

    旧实现每轮删除 shadow 再从 live 全量拷贝——Windows bind mount 下
    unlink WAL/SHM 文件会因文件句柄残留而 PermissionError / 卡死。

    现在直接复用：所有写入按 (code, trade_date) 隔离，
    INSERT OR REPLACE / DELETE+INSERT 天然处理覆盖；shadow 自带的
    bars_daily 历史还能让逐股增量回退 (last_daily_date) 更高效。
    首次运行由后续 MarketStore(shadow_db) 的 _init_db 自动建表。
    """
    shadow_db.parent.mkdir(parents=True, exist_ok=True)


def _publish_shadow(shadow_db: Path, live_db: Path) -> None:
    """Copy the verified shadow DB into the live DB with a short write phase.

    DEPRECATED: full backup overwrite clears live-side intraday/backfill data.
    Kept only as a fallback if _merge_shadow_to_live is disabled. Use
    _merge_shadow_to_live instead.
    """
    live_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True, timeout=30) as source:
        with sqlite3.connect(str(live_db), timeout=30) as target:
            target.execute("PRAGMA busy_timeout=30000")
            source.backup(target, pages=1000, sleep=0.02)


# Tables merged by (code, trade_date) — only rows for the run's trade_date are
# copied from shadow to live. INSERT OR REPLACE keeps other dates intact.
_DATE_KEYED_TABLES = (
    "bars_daily",
    "stock_daily_basic",
    "index_daily",
    "etf_daily",
    "fund_daily",
    "board_daily",
    "dragon_tiger",
    "stock_pool",
    "zt_pool",
    "zb_pool",
    "dt_pool",
    "yzt_pool",
    "ths_limit_up",
    "stock_capital_flow",
    "stock_capital_rank",
    "sector_capital_flow",
    "sector_snapshot",
    "sector_snapshot_industry",
    "sector_snapshot_concept",
    "market_breadth_snapshot",
    "market_stage_snapshot",
    "global_market_index_daily",
    "us_theme_snapshot",
    "premarket_news",
    "ths_hot_reason",
    "hot_list",
    "popularity_rank",
    "cls_telegraph",
    "stock_news",
    "fund_flow_daily",
    "margin_trading",
    "block_trade",
    "holder_num",
    "dividend_history",
    "lockup_expiry",
    "option_chain",
    "northbound_flow",
    "eps_forecast",
    "financial_snapshot",
    "financial_statement",
    "announcements",
)
# Tables merged wholesale (no per-date isolation; PK covers whole row).
_WHOLE_TABLES = ("security_master", "trade_calendar")


def _merge_shadow_to_live(shadow_db: Path, live_db: Path, trade_date: str) -> None:
    """Incrementally merge shadow rows into live by INSERT OR REPLACE.

    Replaces the old ``source.backup(target)`` full-overwrite publish (which
    wiped live-side intraday/backfill data every post_close). Now only the
    run's trade_date slice (or the whole table for universe tables) is merged,
    preserving live data for other dates and for tables the shadow never wrote
    (realtime intraday, integrity backfill).
    """
    live_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{shadow_db}?mode=ro", uri=True, timeout=30)
    src.row_factory = sqlite3.Row
    tgt = sqlite3.connect(str(live_db), timeout=30)
    tgt.execute("PRAGMA busy_timeout=30000")
    tgt.execute("BEGIN IMMEDIATE")
    try:
        # Date-keyed tables: copy only this run's trade_date rows.
        for table in _DATE_KEYED_TABLES:
            try:
                rows = src.execute(
                    f"SELECT * FROM {table} WHERE trade_date = ?", (trade_date,)
                ).fetchall()
            except sqlite3.Error:
                # Table may not exist in this shadow build — skip.
                continue
            if not rows:
                continue
            cols = [d[0] for d in src.execute(f"SELECT * FROM {table} LIMIT 0").description]
            placeholders = ",".join("?" for _ in cols)
            collist = ",".join(cols)
            tgt.executemany(
                f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                [tuple(r) for r in rows],
            )
        # Whole tables: merge entire shadow table (universe/calendar).
        for table in _WHOLE_TABLES:
            try:
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.Error:
                continue
            if not rows:
                continue
            cols = [d[0] for d in src.execute(f"SELECT * FROM {table} LIMIT 0").description]
            placeholders = ",".join("?" for _ in cols)
            collist = ",".join(cols)
            tgt.executemany(
                f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                [tuple(r) for r in rows],
            )
        tgt.commit()
    except Exception:
        tgt.rollback()
        raise
    finally:
        tgt.close()
        src.close()


def _integrity_ok(db_path: Path) -> bool:
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == "ok")


# Map dataset name → DB table for the row-count fallback (datasets without a
# semantic validator). Used so the quality gate trusts actual DB rows over a
# possibly-fabricated provider return value (e.g. index when tushare is
# rate-limited but degraded sources wrote rows).
_DATASET_TABLE = {
    "calendar": "trade_calendar",
    "master": "security_master",
    "index_master": "index_master",
    "board_master": "board_master",
    "daily_basic": "stock_daily_basic",
    "index": "index_daily",
    "etf": "etf_daily",
    "fund_daily": "fund_daily",
    "etf_size": "etf_share_size",
    "dragon": "dragon_tiger",
    "pool": "stock_pool",
    "zt_pool": "zt_pool",
    "capital": "stock_capital_flow",
    "capital_rank": "stock_capital_rank",
    "sector_capital": "sector_capital_flow",
    "sector_snapshot": "sector_snapshot",
    "market_breadth": "market_breadth_snapshot",
    "global_indices": "global_market_index_daily",
    "us_theme": "us_theme_snapshot",
    "premarket_news": "premarket_news",
    "stage_snapshot": "market_stage_snapshot",
    "premium": "fund_premium_snapshot",
    "board": "board_daily",
}


def _dataset_db_row_count(store: MarketStore, dataset: str, trade_date: str) -> int:
    """Count actual rows for *dataset* on *trade_date* directly in the DB.

    Returns 0 if the table doesn't exist or the query fails — never raises.
    """
    table = _DATASET_TABLE.get(dataset)
    if not table:
        return 0
    try:
        if table in ("security_master", "trade_calendar", "index_master", "board_master"):
            row = store._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        else:
            row = store._conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE trade_date = ?", (trade_date,)
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:  # noqa: BLE001
        return 0


def _validate_tier_quality(
    shadow_store: MarketStore,
    trade_date: str,
    run_id: str,
    tier_datasets: set[str],
    rows: dict[str, int],
    *,
    active_code_count: int | None = None,
) -> list[str]:
    """Per-dataset contract loop for one tier. Persists each dataset's quality
    report and returns the list of violating-contract strings (empty = pass).

    Verbatim extraction of the original per-dataset loop; the caller owns the
    run lifecycle (it decides whether to finish_sync_run + raise on non-empty).
    """
    failed_contracts: list[str] = []
    reported_datasets = (tier_datasets | set(rows)) - {"daily"}
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
            elif received == 0:
                # No semantic validator AND provider reported 0 rows. Trust the
                # DB over the (possibly-fabricated) return value: a degraded
                # fetch may have written rows even when the tushare-only count
                # is 0. Read actual rows for this trade_date.
                db_count = _dataset_db_row_count(shadow_store, dataset, trade_date)
                if db_count > 0:
                    valid_rows = db_count
                    received = db_count
        except Exception as exc:  # noqa: BLE001
            valid_rows = 0
            reasons.append(f"semantic_validation_error:{exc}")
        expected_rows = minimum
        if dataset == "realtime":
            # security_master is authoritative on the LIVE db (core tier writes
            # it there). The shadow db may not contain it (e.g. enhanced-only
            # run, or a fresh shadow), so querying shadow here silently returns
            # 0 active codes and skips the coverage gate — letting an
            # under-covered realtime publish as PUBLISHED. Prefer the count the
            # caller read from live; fall back to shadow only if not provided.
            if active_code_count is not None:
                active_codes = active_code_count
            else:
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
    return failed_contracts


def _validate_daily_reference(
    shadow_store: MarketStore,
    trade_date: str,
    run_id: str,
    expected_codes: list[str],
) -> None:
    """Daily reference cross-check (suspended codes + reference closes + tdx +
    validate_daily_dataset). Verbatim extraction; raises MarketDataQualityError
    on non-VERIFIED (after finishing the run). Only meaningful for a tier that
    includes ``daily``.
    """
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
    if report.status is QualityStatus.VERIFIED:
        return
    # QUARANTINED = genuine data corruption (bad OHLC / close mismatch / wrong
    # date). Always blocks — never ship known-bad rows.
    if report.status is QualityStatus.QUARANTINED:
        shadow_store.finish_sync_run(
            run_id,
            report.status,
            error_summary="; ".join(report.blocking_reasons),
        )
        raise MarketDataQualityError(report)
    # PARTIAL can mean either (a) a reference SOURCE was unavailable
    # (weekend / third-party down) — environmental, not a data fault — or
    # (b) the data itself is short while sources WERE available. Only (a) is
    # safe to downgrade. When a source is unavailable, `unexplained_missing_codes`
    # is a *symptom* (we can't tell which codes are suspended vs. truly missing),
    # so its presence alongside source-unavailability still counts as (a).
    # If sources WERE available and codes are still missing, that's real (b).
    # Set MARKET_SYNC_DAILY_REFERENCE_STRICT=1 to hard-block on any non-VERIFIED.
    _SOURCE_UNAVAILABLE_REASONS = {
        "suspension_reference_unavailable",
        "cross_source_reference_unavailable",
        "fallback_reference_coverage_too_low",
    }
    reasons = set(report.blocking_reasons)
    source_down = bool(reasons & _SOURCE_UNAVAILABLE_REASONS)
    strict = os.getenv("MARKET_SYNC_DAILY_REFERENCE_STRICT", "0") == "1"
    if (not source_down) or strict:
        shadow_store.finish_sync_run(
            run_id,
            report.status,
            error_summary="; ".join(report.blocking_reasons),
        )
        raise MarketDataQualityError(report)
    logger.warning(
        "daily reference check PARTIAL (reference sources unavailable), "
        "publishing in lenient mode: %s",
        "; ".join(report.blocking_reasons) or "(no reasons)",
    )
    # Lenient publish: the run will ship, so the per-dataset report must
    # reflect "published & usable" — otherwise downstream readiness gates
    # (get_data_readiness) see PARTIAL and reject consumers (recommendations)
    # even though the data is live. Promote the report status to PUBLISHED
    # while keeping the blocking_reasons for traceability.
    if report.status is not QualityStatus.PUBLISHED:
        promoted = DatasetQualityReport(
            dataset=report.dataset,
            trade_date=report.trade_date,
            status=QualityStatus.PUBLISHED,
            expected_rows=report.expected_rows,
            received_rows=report.received_rows,
            valid_rows=report.valid_rows,
            published_rows=report.valid_rows,
            blocking_reasons=report.blocking_reasons,
            source=report.source + "+lenient_promoted",
        )
        shadow_store.record_dataset_result(run_id, promoted)


def _split_deadline(
    total: int, core_done: bool, enhanced_datasets: set[str]
) -> tuple[int, int]:
    """Split the post-close deadline budget across core/enhanced tiers.

    Core gets the majority (it carries the daily reference check and is
    readiness-critical). Both have floors so a fast path isn't starved.
    See plan step ⑤ / blueprint §6.
    """
    if core_done:
        return (0, total)  # all remaining budget to enhanced retry
    if not enhanced_datasets:
        return (total, 0)  # core-only mode (e.g. CLI --datasets daily)
    core = max(int(total * 0.6), 300)
    enhanced = max(total - core, 120)
    return (core, enhanced)


def _run_one_tier(
    *,
    tier_name: str,
    trade_date: str,
    live_db: Path,
    shadow_db: Path,
    tier_datasets: set[str],
    deadline_seconds: int,
    lookback_days: int,
    universe: str,
    expected_codes: list[str],
    enable_daily_reference: bool,
    tier_meta_key: str,
) -> dict[str, int]:
    """Run one tier end-to-end: prepare → sync → validate → publish.

    On success, sets ``tier_meta_key``. Does NOT touch the aggregate
    ``daemon:{date}`` key (the orchestrator owns that). Raises on failure.
    See plan step ⑤ / blueprint §2.
    """
    logger.info("post-close %s tier preparing %s -> %s", tier_name, live_db, shadow_db)
    _prepare_shadow(live_db, shadow_db)
    shadow_store = MarketStore(shadow_db)
    run_id = shadow_store.create_sync_run(trade_date, worker_id=_worker_id())
    try:
        rows = run_daily_sync(
            trade_date,
            store=shadow_store,
            codes=expected_codes if "daily" in tier_datasets else None,
            datasets=tier_datasets,
            universe=universe,
            deadline_seconds=deadline_seconds,
            lookback_days=lookback_days,
            sync_run_id=run_id,
        )
        # A dataset with no result row either failed or returned nothing. For
        # CORE (critical) datasets that's normally fatal. But in lenient mode
        # (default), a missing critical dataset due to a provider being
        # temporarily unavailable (rate-limit / weekend / third-party down)
        # degrades to a warning + PARTIAL publish rather than freezing the
        # whole day's data. Hard strict only when MARKET_SYNC_CORE_STRICT=1.
        strict = os.getenv("MARKET_SYNC_CORE_STRICT", "0") == "1"
        missing_results = sorted(tier_datasets - rows.keys())
        missing_critical = [d for d in missing_results if contract_for(d).blocking]
        if missing_critical:
            if strict:
                raise MarketDataQualityError(
                    f"missing critical dataset results after sync: {', '.join(missing_critical)}"
                )
            logger.warning(
                "post-close %s: missing critical datasets %s (lenient mode, "
                "provider likely unavailable) — continuing to publish",
                tier_name, missing_critical,
            )

        # realtime coverage gate needs the authoritative active-code count from
        # the LIVE security_master (shadow may be empty of it). Only query when
        # this tier actually includes realtime.
        active_code_count: int | None = None
        if "realtime" in tier_datasets:
            probe = MarketStore(live_db)
            try:
                row = probe._conn.execute(
                    "SELECT COUNT(*) FROM security_master WHERE list_status = 'L'"
                ).fetchone()
                active_code_count = int(row[0] or 0) if row else 0
            except Exception:
                active_code_count = None
            finally:
                probe._conn.close()

        failed_contracts = _validate_tier_quality(
            shadow_store, trade_date, run_id, tier_datasets, rows,
            active_code_count=active_code_count,
        )
        if failed_contracts:
            shadow_store.finish_sync_run(
                run_id,
                QualityStatus.PARTIAL,
                error_summary="; ".join(failed_contracts),
            )
            if strict:
                raise MarketDataQualityError(
                    f"blocking dataset quality contracts failed: {'; '.join(failed_contracts)}"
                )
            # Lenient mode: log and continue to publish. The failing datasets
            # are recorded PARTIAL (downstream readiness reflects it), but a
            # single degraded dataset must not freeze the entire tier's data.
            logger.warning(
                "post-close %s: contracts failed but lenient mode publishing: %s",
                tier_name, "; ".join(failed_contracts),
            )

        if enable_daily_reference and "daily" in tier_datasets:
            _validate_daily_reference(shadow_store, trade_date, run_id, expected_codes)
        shadow_store.finish_sync_run(run_id, QualityStatus.VERIFIED)
        logger.info("post-close shadow sync done rows=%s", rows)
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
    logger.info("post-close %s tier publishing %s rows=%s", tier_name, trade_date, rows)
    # Incremental merge (not full overwrite) — preserves live intraday/backfill.
    _merge_shadow_to_live(shadow_db, live_db, trade_date)
    published_store = MarketStore(live_db)
    # Post-publish readiness recheck. Only enforced in strict mode: in lenient
    # mode the daily dataset may legitimately be PARTIAL (reference sources
    # unavailable), which makes `.ready` False even though the rows published
    # fine — re-checking would spuriously reject a successful publish.
    strict = os.getenv("MARKET_SYNC_DAILY_REFERENCE_STRICT", "0") == "1"
    if (
        strict
        and enable_daily_reference
        and "daily" in tier_datasets
        and not published_store.get_data_readiness("bars_daily", trade_date).ready
    ):
        published_store._conn.close()
        raise RuntimeError("post-publication readiness verification failed")
    published_store.finish_sync_run(run_id, QualityStatus.PUBLISHED)
    published_store.set_meta(tier_meta_key, _now_cst().isoformat())
    published_store._conn.close()
    return rows


def _run_post_close_shadow_sync(
    trade_date: str,
    *,
    live_db: Path,
    shadow_db: Path,
    datasets: set[str],
    deadline_seconds: int,
    lookback_days: int,
) -> dict[str, int]:
    """Tiered post-close sync: publish the CORE snapshot first, then ENHANCED.

    Core (calendar/master/daily_basic/index/daily) validates and publishes
    independently so a slow/stalled enhanced dataset (akshare fund-flow, etc.)
    can no longer block the day's core snapshot. Enhanced datasets publish
    afterward; if enhanced fails, the core stays published and the next worker
    tick retries only enhanced. See plan step ⑤.
    """
    # 3-state idempotency gate (blueprint §7)
    probe = MarketStore(live_db)
    aggregate_done = bool(probe.get_meta(f"daemon:{trade_date}"))
    core_done = bool(probe.get_meta(f"daemon:post_close:core:{trade_date}"))
    probe._conn.close()
    if aggregate_done:
        return {}

    # Derive tier partition. Honor an explicit caller subset: a request for
    # only enhanced datasets (e.g. tests, or CLI --datasets zt_pool) must NOT
    # be force-expanded to the full core set. The worker path passes the full
    # _POST_CLOSE_DATASETS, so both tiers run there.
    core_datasets = datasets & _POST_CLOSE_CORE
    enhanced_datasets = datasets - _POST_CLOSE_CORE
    universe = os.getenv("MARKET_SYNC_POSTCLOSE_UNIVERSE", "all")

    core_budget, enhanced_budget = _split_deadline(
        deadline_seconds, core_done, enhanced_datasets
    )

    # Tier-1 (core): re-raise on failure — live DB keeps yesterday's snapshot,
    # next tick retries both tiers. Skipped when the caller asked for no core
    # datasets (explicit enhanced-only subset) or core already published.
    core_rows: dict[str, int] = {}
    if core_datasets and not core_done:
        expected_codes_core: list[str] = []
        if "daily" in core_datasets:
            # Read the security_master universe from the live DB (shadow not
            # prepared yet). Hold the connection only for this read.
            codes_store = MarketStore(live_db)
            try:
                expected_codes_core = _all_a_share_codes(
                    codes_store, default_only=(universe == "default")
                )
            finally:
                codes_store._conn.close()
        core_rows = _run_one_tier(
            tier_name="core",
            trade_date=trade_date,
            live_db=live_db,
            shadow_db=shadow_db,
            tier_datasets=core_datasets,
            deadline_seconds=core_budget,
            lookback_days=lookback_days,
            universe=universe,
            expected_codes=expected_codes_core,
            enable_daily_reference=True,
            tier_meta_key=f"daemon:post_close:core:{trade_date}",
        )

    # Tier-2 (enhanced): a failure here re-raises, but because the core tier
    # already published and set daemon:post_close:core:{date}, the next worker
    # tick skips core and retries ONLY enhanced. Corrupt-data failures
    # (hard_fail_on_zero_valid) MUST still surface — they are never silently
    # swallowed. See plan step ⑤ / blueprint §8.
    enhanced_rows: dict[str, int] = {}
    if enhanced_datasets:
        enhanced_rows = _run_one_tier(
            tier_name="enhanced",
            trade_date=trade_date,
            live_db=live_db,
            shadow_db=shadow_db,
            tier_datasets=enhanced_datasets,
            deadline_seconds=enhanced_budget,
            lookback_days=lookback_days,
            universe=universe,
            expected_codes=[],  # enhanced has no daily
            enable_daily_reference=False,
            tier_meta_key=f"daemon:post_close:enhanced:{trade_date}",
        )

    # Aggregate back-compat marker — set only when BOTH tiers succeed.
    agg = MarketStore(live_db)
    agg.set_meta(f"daemon:{trade_date}", _now_cst().isoformat())
    agg._conn.close()
    return {**core_rows, **enhanced_rows}


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
    day = trade_date or _settled_trade_date()
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
    # Periodic integrity sweep: cleans stale pending sync_runs, backfills shallow
    # history, and re-syncs low daily coverage. The in-process daemon (_loop) that
    # used to host this is disabled in production (start_market_sync_daemon returns
    # immediately), so it MUST run here too or auto-remediation never happens.
    # Wall-clock throttled; set MARKET_SYNC_INTEGRITY_INTERVAL=0 to disable.
    integrity_interval = int(os.getenv("MARKET_SYNC_INTEGRITY_INTERVAL", "600"))
    last_integrity = 0.0
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
                        _settled_trade_date(live_store),
                        live_db=live_db,
                        shadow_db=_shadow_db_path(live_db),
                        datasets=datasets,
                        deadline_seconds=int(os.getenv("MARKET_SYNC_POSTCLOSE_DEADLINE", "3600")),
                        lookback_days=int(os.getenv("MARKET_SYNC_POSTCLOSE_LOOKBACK_DAYS", "365")),
                    )
                    # Long-term index history backfill (akshare) — runs AFTER the core
                    # snapshot publish, on its own idempotent meta_key. Slow/idempotent;
                    # must never block the day's core publish. See plan step ③.
                    _maybe_run_index_history_sync(live_store)

                if integrity_interval > 0 and time.monotonic() - last_integrity >= integrity_interval:
                    last_integrity = time.monotonic()
                    try:
                        _data_integrity_check(live_store, _today_cst_str())
                    except Exception:
                        logger.exception("data integrity check failed")
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
