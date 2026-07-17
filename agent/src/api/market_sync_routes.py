"""Read-only market-sync status API.

Canonical synchronization is owned exclusively by the standalone
``vibe-trading-sync`` process.  These routes expose operational state to the
business API but never fetch or mutate market data.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from src.api.auth_routes import require_admin

router = APIRouter(prefix="/market-sync", tags=["market-sync"])


class StatusResponse(BaseModel):
    daemon_enabled: bool = False
    backfill_running: bool = False
    sync_worker_required: bool = True
    last_synced: dict[str, str]
    tables: dict[str, int]
    date_ranges: dict[str, list[str | None]]
    coverage: dict[str, Any] = {}
    daily_readiness: dict[str, Any] = {}


class DailySyncRequest(BaseModel):
    trade_date: Optional[str] = None
    codes: Optional[list[str]] = None
    datasets: Optional[list[str]] = None
    lookback_days: int = 90


class SyncResultResponse(BaseModel):
    ok: bool
    trade_date: str
    detail: str
    rows: dict[str, int] = {}


class BackfillRequest(BaseModel):
    years: int = 2
    datasets: list[str] = ["daily"]
    universe: str = "default"
    etf_codes: Optional[list[str]] = None
    codes: Optional[list[str]] = None
    lookback_days: Optional[int] = None


class CodeSyncRequest(BaseModel):
    code: str
    datasets: list[str] = ["daily"]
    start: Optional[str] = None
    end: Optional[str] = None


class PushRequest(BaseModel):
    table: str
    trade_date: str
    rows: list[dict]


class HealthResponse(BaseModel):
    tpdog_configured: bool
    tpdog_ok: bool
    trading_today: bool
    detail: str


def _store():
    from src.data.market_store import get_market_store

    return get_market_store()


def _latest_synced() -> dict[str, str]:
    store = _store()
    if store is None:
        return {}
    rows = store._conn.execute(
        "SELECT key, value FROM sync_meta "
        "WHERE key LIKE 'daemon:____-__-__' ORDER BY key DESC LIMIT 30"
    ).fetchall()
    return {str(row["key"]).split(":", 1)[1]: str(row["value"]) for row in rows}


def _expected_settled_date(store) -> str | None:
    """Resolve the expected settled date from the akshare calendar.

    Same source as the sync scheduler and ``is_trading_day``; the DB table is a
    cross-check fallback only.
    """
    from src.data.market_sync import _now_cst
    from src.data.trade_calendar import expected_settled_date

    settled = expected_settled_date(_now_cst())
    if settled:
        return settled
    now = _now_cst()
    cutoff = now.date().isoformat()
    if now.hour < 15 or (now.hour == 15 and now.minute < 5):
        cutoff = (now.date() - timedelta(days=1)).isoformat()
    try:
        row = store._conn.execute(
            "SELECT MAX(trade_date) AS d FROM trade_calendar "
            "WHERE market = 'CN' AND is_trading = 1 AND trade_date <= ?",
            (cutoff,),
        ).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return str(row["d"]) if row and row["d"] else None


def _readiness_payload(store) -> dict[str, Any]:
    expected_date = _expected_settled_date(store)
    if not expected_date:
        return {
            "dataset": "bars_daily",
            "ready": False,
            "status": "failed",
            "blocking_reasons": ["canonical_trade_calendar_unavailable"],
        }
    readiness = store.get_data_readiness("bars_daily", expected_date)
    return {
        "dataset": readiness.dataset,
        "as_of": readiness.as_of,
        "ready": readiness.ready,
        "status": readiness.status.value,
        "expected_rows": readiness.expected_rows,
        "valid_rows": readiness.valid_rows,
        "published_rows": readiness.published_rows,
        "source": readiness.source,
        "run_id": readiness.run_id,
        "blocking_reasons": readiness.blocking_reasons,
    }


def _raise_worker_required() -> None:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "SYNC_WORKER_REQUIRED",
            "message": "The business API is read-only; run synchronization through vibe-trading-sync.",
        },
    )


def _dataset_status_payload(store, dataset: str, expected_date: str | None) -> dict[str, Any]:
    from src.data.dataset_registry import contract_for

    contract = contract_for(dataset)
    entry: dict[str, Any] = {
        "dataset": dataset,
        "expected_date": expected_date,
        "ready": False,
        "status": "unknown",
        "valid_rows": 0,
        "expected_rows": contract.minimum_rows,
        "blocking": contract.blocking,
        "recommendation_input": contract.recommendation_input,
        "blocking_reasons": [],
        "sync_errors": [],
    }
    if not expected_date:
        entry["blocking_reasons"] = ["canonical_trade_calendar_unavailable"]
        entry["sync_errors"] = store.list_sync_errors(dataset)
        return entry
    readiness = store.get_data_readiness(dataset, expected_date)
    entry.update(
        {
            "as_of": readiness.as_of,
            "ready": readiness.ready,
            "status": readiness.status.value,
            "valid_rows": readiness.valid_rows,
            "published_rows": readiness.published_rows,
            "source": readiness.source,
            "run_id": readiness.run_id,
            "blocking_reasons": readiness.blocking_reasons,
            "sync_errors": store.list_sync_errors(dataset),
        }
    )
    return entry


@router.get("/datasets", dependencies=[Depends(require_admin)])
async def dataset_status() -> dict[str, Any]:
    """Per-dataset readiness + active provider failures for diagnostics.

    Lists every dataset the publication gate and the recommendation pipeline
    care about (union of the registry's critical/advisory sets and the
    recommendation inputs), so a single call reveals why a run is not published
    or why recommendations collapsed.
    """
    store = _store()
    if store is None:
        raise HTTPException(status_code=503, detail="market store unavailable")
    from src.data import dataset_registry

    critical = getattr(dataset_registry, "_CRITICAL", {})
    advisory = getattr(dataset_registry, "_ADVISORY", {})
    inputs = getattr(dataset_registry, "_RECOMMENDATION_INPUTS", {})
    datasets = sorted(set(critical) | set(advisory) | set(inputs))
    expected_date = _expected_settled_date(store)
    return {
        "expected_date": expected_date,
        "datasets": [_dataset_status_payload(store, ds, expected_date) for ds in datasets],
    }


@router.get("/status", response_model=StatusResponse, dependencies=[Depends(require_admin)])
async def status() -> StatusResponse:
    store = _store()
    if store is None:
        raise HTTPException(status_code=503, detail="market store unavailable")
    counts = store.table_counts()
    return StatusResponse(
        last_synced=_latest_synced(),
        tables=counts,
        date_ranges={table: list(store.date_range(table)) for table in counts},
        coverage=store.market_coverage(),
        daily_readiness=_readiness_payload(store),
    )


@router.post("/daily", response_model=SyncResultResponse, dependencies=[Depends(require_admin)])
async def sync_daily(body: DailySyncRequest) -> SyncResultResponse:
    _raise_worker_required()


@router.post("/code", response_model=SyncResultResponse, dependencies=[Depends(require_admin)])
async def sync_code(body: CodeSyncRequest) -> SyncResultResponse:
    _raise_worker_required()


@router.post("/backfill", dependencies=[Depends(require_admin)])
async def backfill(body: BackfillRequest) -> dict[str, Any]:
    _raise_worker_required()


@router.post("/snapshot", response_model=SyncResultResponse, dependencies=[Depends(require_admin)])
async def snapshot(body: DailySyncRequest = DailySyncRequest()) -> SyncResultResponse:
    _raise_worker_required()


@router.post("/push")
def push_data(body: PushRequest) -> dict[str, Any]:
    _raise_worker_required()


@router.get("/health", response_model=HealthResponse, dependencies=[Depends(require_admin)])
async def health() -> HealthResponse:
    store = _store()
    if store is None:
        raise HTTPException(status_code=503, detail="market store unavailable")
    from src.data.market_sync import _today_cst_str

    return HealthResponse(
        tpdog_configured=bool(os.getenv("TPDOG_TOKEN", "").strip()),
        tpdog_ok=False,
        trading_today=store.is_trading_date(_today_cst_str()),
        detail="read-only API: provider health is checked by vibe-trading-sync",
    )


def register_market_sync_routes(app: FastAPI) -> None:
    app.include_router(router)
