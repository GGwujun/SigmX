"""Risk management API routes — market regime + risk check endpoints.

Mounted by ``agent/api_server.py`` via ``register_risk_routes(app, ...)``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.api.auth_routes import require_user as _require_auth_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


# ─────────────────────────────────────────────────────────────────
# Response models
# ─────────────────────────────────────────────────────────────────

class RegimeResponse(BaseModel):
    trade_date: str
    regime: str
    confidence: float
    bull_score: float
    bear_score: float
    strong_trend: bool
    technical_indicators: dict = {}
    parameters: dict = {}


class RiskCheckResponse(BaseModel):
    trade_date: str
    regime: str
    checks: list[dict] = []
    portfolio_health_score: float | None = None
    has_positions: bool = True
    summary: str = ""


class RegimeHistoryResponse(BaseModel):
    items: list[dict] = []


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@router.get("/regime", response_model=RegimeResponse)
async def get_current_regime():
    """返回当前市场环境分类结果。"""
    from src.data.market_store import get_market_store
    store = get_market_store()
    if store is None:
        raise HTTPException(status_code=503, detail="MarketStore not available")

    result = store.get_latest_regime()
    if result is None:
        # 如果没有历史数据，尝试实时分类
        try:
            from src.risk.regime_classifier import classify_regime
            regime_result = classify_regime(store)
            store.save_regime_result(regime_result.to_dict())
            return RegimeResponse(**regime_result.to_dict())
        except Exception as exc:
            logger.warning("实时 regime 分类失败: %s", exc)
            # 返回默认 range
            from src.risk.regime_classifier import REGIME_PARAMS
            return RegimeResponse(
                trade_date="",
                regime="range",
                confidence=0.0,
                bull_score=0.0,
                bear_score=0.0,
                strong_trend=False,
                parameters=REGIME_PARAMS["range"],
            )

    return RegimeResponse(
        trade_date=result.get("trade_date", ""),
        regime=result.get("regime", "range"),
        confidence=result.get("confidence", 0.0),
        bull_score=result.get("bull_score", 0.0),
        bear_score=result.get("bear_score", 0.0),
        strong_trend=result.get("strong_trend", False),
        technical_indicators=result.get("indicators", {}),
        parameters=result.get("params", {}),
    )


@router.get("/regime/history", response_model=RegimeHistoryResponse)
async def get_regime_history(days: int = Query(default=30, ge=1, le=365)):
    """返回近 N 天的市场环境分类历史。"""
    from src.data.market_store import get_market_store
    store = get_market_store()
    if store is None:
        raise HTTPException(status_code=503, detail="MarketStore not available")

    items = store.get_regime_history(days)
    return RegimeHistoryResponse(items=items)


@router.get("/regime/run")
async def run_regime_classification(trade_date: str | None = None):
    """手动触发市场环境分类。"""
    from src.data.market_store import get_market_store
    from src.risk.regime_classifier import classify_regime

    store = get_market_store()
    if store is None:
        raise HTTPException(status_code=503, detail="MarketStore not available")

    try:
        result = classify_regime(store, trade_date=trade_date)
        store.save_regime_result(result.to_dict())
        return result.to_dict()
    except Exception as exc:
        logger.exception("regime 分类失败")
        raise HTTPException(status_code=500, detail=f"regime classification failed: {exc}")


@router.get("/params")
async def get_regime_params():
    """返回当前 regime 对应的风控参数，以及所有 regime 的参数库。"""
    from src.risk.regime_classifier import REGIME_PARAMS
    from src.data.market_store import get_market_store

    store = get_market_store()
    current_regime = "range"
    if store is not None:
        latest = store.get_latest_regime()
        if latest:
            current_regime = latest.get("regime", "range")

    return {
        "current_regime": current_regime,
        "current_params": REGIME_PARAMS.get(current_regime, REGIME_PARAMS["range"]),
        "all_params": REGIME_PARAMS,
    }


@router.get("/check", response_model=RiskCheckResponse)
async def run_risk_check():
    """运行 8 层风控检查。"""
    import asyncio
    from src.data.market_store import get_market_store
    from src.risk.risk_engine import run_all_checks
    from src.risk.risk_store import save_risk_report, save_health_score

    store = get_market_store()
    if store is None:
        raise HTTPException(status_code=503, detail="MarketStore not available")

    try:
        loop = asyncio.get_event_loop()
        report = await loop.run_in_executor(None, run_all_checks, store)
        report_dict = report.to_dict()
        # 持久化风控事件和健康评分（无持仓时 score 为 None，跳过持久化）
        save_risk_report(report_dict)
        if report.portfolio_health_score is not None:
            save_health_score(report.portfolio_health_score)
        return RiskCheckResponse(**report_dict)
    except Exception as exc:
        logger.exception("风控检查失败")
        raise HTTPException(status_code=500, detail=f"risk check failed: {exc}")


@router.get("/health")
async def get_health_score():
    """返回当前持仓健康评分（无持仓/未检查时为 null）。"""
    from src.risk.risk_store import get_latest_health_score
    score = get_latest_health_score()
    return {"health_score": score}


@router.get("/check/history")
async def get_risk_check_history(
    days: int = Query(default=30, ge=1, le=365),
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    """返回历史风控事件。"""
    from src.risk.risk_store import get_risk_events
    events = get_risk_events(days=days, severity=severity, limit=limit)
    return {"events": events, "count": len(events)}


# ─────────────────────────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────────────────────────

def register_risk_routes(
    app: FastAPI,
    require_auth: Any = None,
    require_event_stream_auth: Any = None,
) -> None:
    """Register risk routes on the FastAPI app."""
    auth_dep = require_auth or _require_auth_dep
    app.include_router(router, dependencies=[Depends(auth_dep)])
