"""Read-only compatibility routes for canonical TPDog-sourced data."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, FastAPI, Query
from pydantic import BaseModel

from src.api.auth_routes import require_admin
from src.data.tpdog_client import is_configured

router = APIRouter(prefix="/tpdog", tags=["tpdog"])


class TpdogStatus(BaseModel):
    configured: bool
    ok: bool
    detail: str


class TpdogEnvelope(BaseModel):
    ok: bool
    detail: str
    content: List[Dict[str, Any]] = []


def _error_envelope(exc: Exception) -> TpdogEnvelope:
    return TpdogEnvelope(ok=False, detail=str(exc)[:300], content=[])


def _store():
    from src.data.market_store import db_read_enabled, get_market_store

    return get_market_store() if db_read_enabled() else None


@router.get("/status", response_model=TpdogStatus, dependencies=[Depends(require_admin)])
async def tpdog_status() -> TpdogStatus:
    configured = is_configured()
    return TpdogStatus(
        configured=configured,
        ok=False,
        detail="read-only API: provider health is owned by vibe-trading-sync",
    )


@router.get("/trading-days", response_model=TpdogEnvelope, dependencies=[Depends(require_admin)])
async def trading_days(year: str = Query(..., description="yyyy, for example 2026")) -> TpdogEnvelope:
    try:
        store = _store()
        if store is None:
            return TpdogEnvelope(ok=False, detail="DATA_NOT_READY: market store unavailable")
        rows = store._conn.execute(
            "SELECT trade_date AS date, is_trading FROM trade_calendar "
            "WHERE trade_date LIKE ? ORDER BY trade_date",
            (f"{year}-%",),
        ).fetchall()
        content = [{"date": row["date"], "is_trading": bool(row["is_trading"])} for row in rows]
        return TpdogEnvelope(ok=bool(content), detail=f"{len(content)} rows (DB)", content=content)
    except Exception as exc:  # noqa: BLE001
        return _error_envelope(exc)


def _project_code_from_tpdog(tpdog_code: str) -> str | None:
    if "." not in tpdog_code:
        return None
    prefix, digits = tpdog_code.split(".", 1)
    if len(digits) != 6 or not digits.isdigit():
        return None
    return f"{digits}.{prefix.upper()}"


@router.get("/daily", response_model=TpdogEnvelope, dependencies=[Depends(require_admin)])
async def daily_history(
    code: str = Query(..., description="sh.600206 / sz.000001"),
    start: str = Query(..., description="yyyy-MM-dd"),
    end: str = Query(..., description="yyyy-MM-dd"),
) -> TpdogEnvelope:
    try:
        store = _store()
        project_code = _project_code_from_tpdog(code)
        if store is not None and project_code is not None:
            frame = store.get_daily_bars(project_code, start=start, end=end)
            if frame is not None and not frame.empty:
                content = [
                    {
                        "date": str(timestamp)[:10],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                    }
                    for timestamp, row in frame.iterrows()
                ]
                return TpdogEnvelope(ok=True, detail=f"{len(content)} rows (DB)", content=content)
        return TpdogEnvelope(
            ok=False,
            detail="DATA_NOT_READY: canonical daily bars unavailable; run vibe-trading-sync",
        )
    except Exception as exc:  # noqa: BLE001
        return _error_envelope(exc)


@router.get("/call-auction", response_model=TpdogEnvelope, dependencies=[Depends(require_admin)])
async def call_auction(
    code: str = Query(...),
    sort: int = Query(2),
    test: bool = Query(False),
) -> TpdogEnvelope:
    return TpdogEnvelope(
        ok=False,
        detail="SYNC_WORKER_REQUIRED: query API does not call external market providers",
    )


@router.get("/dragon-tiger", response_model=TpdogEnvelope, dependencies=[Depends(require_admin)])
async def dragon_tiger(date: str = Query(..., description="yyyy-MM-dd")) -> TpdogEnvelope:
    try:
        store = _store()
        if store is not None and store.has_dragon_tiger(date):
            rows = store.get_dragon_tiger(date)
            return TpdogEnvelope(ok=True, detail=f"{len(rows)} rows (DB)", content=rows)
        return TpdogEnvelope(
            ok=False,
            detail="DATA_NOT_READY: canonical dragon-tiger data unavailable; run vibe-trading-sync",
        )
    except Exception as exc:  # noqa: BLE001
        return _error_envelope(exc)


def register_tpdog_routes(app: FastAPI) -> None:
    app.include_router(router)
