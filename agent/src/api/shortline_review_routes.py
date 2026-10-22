# -*- coding: utf-8 -*-
"""AI 短线复盘 API：POST 触发生成（后台线程），GET latest / GET by id。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.product.shortline_review import ShortlineReviewService
from src.product.shortline_verify import (conditions_with_status,
                                          track_record, verify_trade_date)

router = APIRouter(prefix="/api/v1/shortline/review", tags=["shortline-review"],
                   dependencies=[Depends(require_user)])


class StartReviewRequest(BaseModel):
    trade_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ReviewResponse(BaseModel):
    id: str
    trade_date: str
    model: str | None
    status: str
    sections: dict[str, Any]
    gaps: list[str]
    conditions: list[dict[str, Any]]
    error: str | None
    created_at: str
    finished_at: str | None


_service: ShortlineReviewService | None = None


def _get_service() -> ShortlineReviewService:
    global _service
    if _service is None:
        from src.api.product_routes import _get_store
        from src.product.ai_runtime_config import AIRuntimeConfigService, build_configured_chat

        config = AIRuntimeConfigService(_get_store()).get_effective()

        def _llm():
            return build_configured_chat(config.execution,
                                         temperature=config.temperature,
                                         timeout_seconds=config.timeout_seconds,
                                         max_retries=config.max_retries,
                                         reasoning_effort=config.reasoning_effort)

        _service = ShortlineReviewService(_get_store(), _llm)
    return _service


def _market_store():
    from src.data.market_store import get_market_store

    return get_market_store()


def _product_store():
    from src.api.product_routes import _get_store

    return _get_store()


@router.post("", response_model=ReviewResponse, status_code=201)
async def start_shortline_review(
    body: StartReviewRequest,
    user: dict = Depends(require_user),  # noqa: ARG001 —— 生成需要登录态，复盘本身市场级
) -> ReviewResponse:
    try:
        row = _get_service().start(trade_date=body.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"复盘服务暂不可用: {exc}") from exc
    return ReviewResponse(**row)


@router.get("/latest", response_model=ReviewResponse | None)
async def latest_shortline_review(
    trade_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(require_user),  # noqa: ARG001
) -> ReviewResponse | None:
    row = _get_service().latest(trade_date)
    if not row:
        return None
    row["conditions"] = conditions_with_status(_product_store(), row["id"],
                                               row["conditions"])
    return ReviewResponse(**row)


@router.post("/verify")
async def verify_shortline_conditions(
    trade_date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    user: dict = Depends(require_user),  # noqa: ARG001 —— 市场级对账
) -> dict:
    """手动对账：trade_date=验证日 t1（缺省用当前已结算日），T 自动取前一交易日。"""
    t1 = trade_date
    if t1 is None:
        from src.data.market_sync_worker import _settled_trade_date

        t1 = _settled_trade_date(_market_store())
    if not t1:
        raise HTTPException(status_code=409, detail="无法确定已结算交易日，请显式传 trade_date")
    return verify_trade_date(_product_store(), _market_store(), t1)


@router.get("/track")
async def shortline_track_record(
    metric: str | None = Query(default=None),
    window: int = Query(default=60, ge=1, le=250),
    user: dict = Depends(require_user),  # noqa: ARG001
) -> dict:
    """复盘条件战绩：近 window 个已决交易日的命中率 + 基准发生率校正。"""
    return track_record(_product_store(), _market_store(),
                        metric=metric, window=window)


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_shortline_review(
    review_id: str,
    user: dict = Depends(require_user),  # noqa: ARG001
) -> ReviewResponse:
    try:
        row = _get_service().get(review_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="复盘不存在") from exc
    row["conditions"] = conditions_with_status(_product_store(), row["id"],
                                               row["conditions"])
    return ReviewResponse(**row)


def register_shortline_review_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/v1/shortline/review" for route in app.routes):
        app.include_router(router)
    return router
