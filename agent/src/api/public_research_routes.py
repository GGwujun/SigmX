"""Anonymous, deliberately limited research endpoints for the Web funnel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.product.public_research import InstrumentNotFound, PublicResearchService


class PublicSearchItemResponse(BaseModel):
    code: str
    name: str
    industry: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    as_of: str | None
    instrument_type: str


class PublicResourceResponse(BaseModel):
    title: str
    url: str
    description: str


class PublicSearchResponse(BaseModel):
    query: str
    interpretation: list[str]
    items: list[PublicSearchItemResponse]
    intent: str
    answer: str | None
    resources: list[PublicResourceResponse]
    source: str
    is_delayed: bool


class PublicStockResponse(BaseModel):
    code: str
    name: str
    industry: str | None
    market: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    as_of: str | None
    quote: dict[str, Any]
    finance: dict[str, Any]
    capital_flows: list[dict[str, Any]]
    events: list[dict[str, Any]]
    risks: list[str]
    research_summary: str
    quality: dict[str, Any]
    source: str
    is_delayed: bool


class PublicFundResponse(BaseModel):
    code: str
    name: str
    fund_type: str | None
    close: float | None
    change_percent: float | None
    as_of: str | None
    premium: dict[str, Any]
    scale: dict[str, Any]
    liquidity: dict[str, Any]
    risks: list[str]
    research_summary: str
    quality: dict[str, Any]
    source: str
    is_delayed: bool


router = APIRouter(tags=["public-research"])
_service: PublicResearchService | None = None


def _get_service() -> PublicResearchService:
    global _service
    if _service is None:
        _service = PublicResearchService()
    return _service


@router.get("/api/public/search", response_model=PublicSearchResponse)
async def public_search(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(10, ge=1, le=10)) -> PublicSearchResponse:
    try:
        result = _get_service().search(q, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PublicSearchResponse(**asdict(result))


@router.get("/api/public/stocks/{code}", response_model=PublicStockResponse)
async def public_stock(code: str) -> PublicStockResponse:
    try:
        return PublicStockResponse(**asdict(_get_service().stock(code)))
    except InstrumentNotFound as exc:
        raise HTTPException(status_code=404, detail="stock not found") from exc


@router.get("/api/public/funds/{code}", response_model=PublicFundResponse)
async def public_fund(code: str) -> PublicFundResponse:
    try:
        return PublicFundResponse(**asdict(_get_service().fund(code)))
    except InstrumentNotFound as exc:
        raise HTTPException(status_code=404, detail="fund not found") from exc


def register_public_research_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/public/search" for route in app.routes):
        app.include_router(router)
    return router
