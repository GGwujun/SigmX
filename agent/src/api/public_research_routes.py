"""Anonymous, deliberately limited research endpoints for the Web funnel."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from datetime import datetime, timezone
from pathlib import Path
import os

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


class DiscoveryMetricResponse(BaseModel):
    key: str
    label: str
    value: float | None
    change: float | None
    unit: str | None
    quality: str
    secondary_value: float | None = None


class ResearchTemplateResponse(BaseModel):
    id: str
    label: str
    description: str
    prompt: str
    data_domains: list[str]


class PublicDiscoveryResponse(BaseModel):
    as_of: str | None
    source: str
    is_delayed: bool
    market_status: str
    metrics: list[DiscoveryMetricResponse]
    templates: list[ResearchTemplateResponse]


class PublicIntelligenceArticleResponse(BaseModel):
    title: str
    url: str = ""
    source: str = ""
    published: str = ""
    snippet: str = ""


class PublicIntelligenceResponse(BaseModel):
    articles: list[PublicIntelligenceArticleResponse]
    query: str
    sources: list[str]
    updated_at: str
    cache_status: str
    cached_until: str | None = None
    degraded: bool = False
    warnings: list[str] = []
    source_health: dict[str, dict[str, Any]] = {}


class PublicGlobalEventResponse(BaseModel):
    id: str
    title: str
    summary: str
    event_type: str
    status: str
    importance: float
    confidence: float
    region: str
    first_seen_at: str
    updated_at: str
    evidence_count: int


class PublicGlobalEventListResponse(BaseModel):
    items: list[PublicGlobalEventResponse]
    total: int
    limit: int
    offset: int


class PublicGlobalEventDetailResponse(PublicGlobalEventResponse):
    evidence: list[dict[str, Any]]


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
_intelligence_service = None
_event_service = None


def _get_service() -> PublicResearchService:
    global _service
    if _service is None:
        _service = PublicResearchService()
    return _service


def _get_intelligence_services():
    global _intelligence_service, _event_service
    if _intelligence_service is None:
        from src.intelligence.event_service import GlobalEventService
        from src.intelligence.service import IntelligenceService
        from src.intelligence.sources.gdelt import GdeltSourceAdapter
        from src.intelligence.sources.legacy import default_legacy_sources
        from src.intelligence.store import IntelligenceStore

        db_path = Path(os.getenv("SIGMX_INTELLIGENCE_DB_PATH", str(Path.home() / ".vibe-trading" / "intelligence.db")))
        store = IntelligenceStore(db_path)
        _intelligence_service = IntelligenceService(store, [*default_legacy_sources(), GdeltSourceAdapter()])
        _event_service = GlobalEventService(store)
    return _intelligence_service, _event_service


@router.get("/api/public/search", response_model=PublicSearchResponse)
async def public_search(q: str = Query(..., min_length=1, max_length=200), limit: int = Query(10, ge=1, le=10)) -> PublicSearchResponse:
    try:
        result = _get_service().search(q, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PublicSearchResponse(**asdict(result))


@router.get("/api/public/discovery", response_model=PublicDiscoveryResponse)
async def public_discovery() -> PublicDiscoveryResponse:
    return PublicDiscoveryResponse(**asdict(_get_service().discovery()))


@router.get("/api/public/intelligence", response_model=PublicIntelligenceResponse)
async def public_intelligence(q: str = Query("", max_length=100), limit: int = Query(30, ge=1, le=60)) -> PublicIntelligenceResponse:
    import asyncio
    from src.api.news_routes import get_cached_news_list
    from src.intelligence.service import IntelligenceQuery

    service, events = _get_intelligence_services()
    loop = asyncio.get_running_loop()
    legacy, result = await asyncio.gather(
        loop.run_in_executor(None, get_cached_news_list, q.strip()),
        loop.run_in_executor(None, service.search, IntelligenceQuery(query=q.strip(), limit=limit)),
    )
    await asyncio.get_running_loop().run_in_executor(None, events.refresh, result.articles)
    articles = list(legacy.get("articles", []))
    seen = {(item.get("url"), item.get("title")) for item in articles}
    for item in result.articles:
        if (item.url, item.title) not in seen:
            articles.append({"title": item.title, "url": item.url, "source": item.source_name,
                             "published": item.published_at.isoformat(), "snippet": item.summary})
    articles = articles[:limit]
    health = {key: {"health": batch.health.value, "errors": [error.message for error in batch.errors]}
              for key, batch in result.source_health.items()}
    return PublicIntelligenceResponse(
        articles=articles, query=q.strip() or "市场情报",
        sources=list(legacy.get("sources") or dict.fromkeys(item.source_name for item in result.articles)),
        updated_at=datetime.now(timezone.utc).isoformat(), cache_status=str(legacy.get("cache_status") or "live"),
        cached_until=legacy.get("cached_until"), degraded=result.degraded,
        warnings=result.warnings, source_health=health,
    )


def _event_response(view) -> PublicGlobalEventResponse:
    event = view.event
    return PublicGlobalEventResponse(
        id=event.id, title=event.title, summary=event.summary, event_type=event.event_type,
        status=event.status, importance=event.importance, confidence=event.confidence, region=event.region,
        first_seen_at=event.first_seen_at.isoformat(), updated_at=event.updated_at.isoformat(),
        evidence_count=len(view.evidence),
    )


@router.get("/api/public/global-events", response_model=PublicGlobalEventListResponse)
async def public_global_events(
    event_type: str = Query("", max_length=40), limit: int = Query(30, ge=1, le=60), offset: int = Query(0, ge=0),
) -> PublicGlobalEventListResponse:
    _, service = _get_intelligence_services()
    result = service.list(event_type=event_type, limit=limit, offset=offset)
    return PublicGlobalEventListResponse(items=[_event_response(item) for item in result.items], total=result.total, limit=limit, offset=offset)


@router.get("/api/public/global-events/{event_id}", response_model=PublicGlobalEventDetailResponse)
async def public_global_event(event_id: str) -> PublicGlobalEventDetailResponse:
    _, service = _get_intelligence_services()
    try:
        view = service.get(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="event not found") from exc
    base = _event_response(view).model_dump()
    evidence = [{"id": item.article.id, "title": item.article.title, "url": item.article.url,
                 "source": item.article.source_name, "published_at": item.article.published_at.isoformat(),
                 "is_key": item.is_key} for item in view.evidence]
    return PublicGlobalEventDetailResponse(**base, evidence=evidence)


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
