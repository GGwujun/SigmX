# -*- coding: utf-8 -*-
"""AI 短线复盘 API：POST 触发生成（后台线程），GET latest / GET by id。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.product.shortline_review import ShortlineReviewService

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
    return ReviewResponse(**row) if row else None


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_shortline_review(
    review_id: str,
    user: dict = Depends(require_user),  # noqa: ARG001
) -> ReviewResponse:
    try:
        return ReviewResponse(**_get_service().get(review_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="复盘不存在") from exc


def register_shortline_review_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/v1/shortline/review" for route in app.routes):
        app.include_router(router)
    return router
