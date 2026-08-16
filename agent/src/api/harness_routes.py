"""Authenticated Desktop APIs for the Financial Harness product contract."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.harness.context import build_context_manifest
from src.harness.assets import LocalAssetCatalog
from src.harness.registry import HarnessToolRegistry
from src.harness.store import HarnessRun, HarnessStore, InvalidRunTransition


class HarnessStatusResponse(BaseModel):
    runtime_available: bool
    cloud_connected: bool
    local_data_available: bool
    data_hub_available: bool
    research_credits: int
    data_credits: int
    governance_ceiling: str
    degradations: list[str]


class HarnessToolItem(BaseModel):
    id: str
    name: str
    category: str
    input_schema: dict[str, Any]
    output_kind: str
    data_locality: str
    governance_level: str
    requires_confirmation: bool
    cost_dimensions: list[str]


class HarnessToolsResponse(BaseModel):
    items: list[HarnessToolItem]


class HarnessRunItem(BaseModel):
    run_id: str
    run_type: str
    title: str
    goal: str
    status: str
    created_at: str
    started_at: str | None
    finished_at: str | None
    context_manifest: dict[str, Any]
    steps: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    costs: dict[str, float]
    degradations: list[dict[str, Any]]
    governance_events: list[dict[str, Any]]
    result_ref: str | None
    error: str | None


class HarnessRunsResponse(BaseModel):
    items: list[HarnessRunItem]


class LocalAssetItem(BaseModel):
    id: str
    kind: str
    name: str
    extension: str
    size_bytes: int
    modified_at: str
    version: str | None
    local_only: bool


class LocalAssetSummaryResponse(BaseModel):
    counts: dict[str, int]
    total_size_bytes: int
    latest_modified_at: str | None


class LocalAssetsResponse(BaseModel):
    items: list[LocalAssetItem]
    summary: LocalAssetSummaryResponse


class CreateHarnessRunRequest(BaseModel):
    run_type: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=160)
    goal: str = Field(..., min_length=1, max_length=2000)
    context_manifest: dict[str, Any] = Field(default_factory=dict)


class ContextPreviewRequest(BaseModel):
    current_symbol: str | None = Field(None, max_length=32)
    cloud_watchlist_refs: list[str] = Field(default_factory=list, max_length=100)
    risk_profile_ref: str | None = Field(None, max_length=128)
    market_snapshot_ref: str | None = Field(None, max_length=128)
    local_files: list[str] = Field(default_factory=list, max_length=100)
    extra: dict[str, Any] = Field(default_factory=dict)


class LocalFileRefResponse(BaseModel):
    ref: str
    name: str
    local_only: bool


class ContextPreviewResponse(BaseModel):
    current_symbol: str | None
    cloud_watchlist_refs: list[str]
    risk_profile_ref: str | None
    market_snapshot_ref: str | None
    local_files: list[LocalFileRefResponse]
    safe_attributes: dict[str, Any]


router = APIRouter(prefix="/api/harness", tags=["harness"])
_registry: HarnessToolRegistry | None = None
_store: HarnessStore | None = None
_assets: LocalAssetCatalog | None = None


def _get_registry() -> HarnessToolRegistry:
    global _registry
    if _registry is None:
        from src.tools import build_registry
        _registry = HarnessToolRegistry.from_tool_registry(build_registry(include_shell_tools=False, interactive=False))
    return _registry


def _get_store() -> HarnessStore:
    global _store
    if _store is None:
        _store = HarnessStore(Path.home() / ".vibe-trading" / "harness.db")
    return _store


def _get_assets() -> LocalAssetCatalog:
    global _assets
    if _assets is None:
        root = Path.home() / ".vibe-trading"
        _assets = LocalAssetCatalog({
            "dataset": root / "data", "research": root / "research",
            "report": root / "reports", "cache": root / "cache",
        })
    return _assets


def _run_item(run: HarnessRun) -> HarnessRunItem:
    return HarnessRunItem(
        run_id=run.id, run_type=run.run_type, title=run.title, goal=run.goal,
        status=run.status, created_at=run.created_at, started_at=run.started_at,
        finished_at=run.finished_at, context_manifest=run.context_manifest,
        steps=[asdict(value) for value in run.steps],
        tool_calls=[asdict(value) for value in run.tool_calls],
        evidence=[asdict(value) for value in run.evidence],
        artifacts=[asdict(value) for value in run.artifacts], costs=run.costs or {},
        degradations=[asdict(value) for value in run.degradations],
        governance_events=[asdict(value) for value in run.governance_events],
        result_ref=run.result_ref, error=run.error,
    )


def _status(user_id: str) -> dict[str, Any]:
    from src.api import product_routes
    store = product_routes._get_store()
    entitlements = product_routes._get_commerce().current_entitlements(user_id).entitlements
    research = product_routes._get_ledger().balance(user_id).available
    data = product_routes._get_data_ledger().balance(user_id).available
    device_count = store._get_conn().execute(
        "SELECT COUNT(*) FROM devices WHERE user_id=? AND revoked_at IS NULL", (user_id,)
    ).fetchone()[0]
    local_db = Path.home() / ".vibe-trading" / "market.db"
    degradations = []
    if not local_db.exists():
        degradations.append("local market database is not initialized")
    if not device_count:
        degradations.append("cloud device is not connected")
    return {
        "runtime_available": True,
        "cloud_connected": bool(device_count),
        "local_data_available": local_db.exists(),
        "data_hub_available": bool(entitlements.get("datahub.enabled", False)),
        "research_credits": int(research),
        "data_credits": int(data),
        "governance_ceiling": "simulate",
        "degradations": degradations,
    }


@router.get("/status", response_model=HarnessStatusResponse)
async def harness_status(user: dict = Depends(require_user)) -> HarnessStatusResponse:
    return HarnessStatusResponse(**_status(user["id"]))


@router.get("/tools", response_model=HarnessToolsResponse)
async def harness_tools(user: dict = Depends(require_user)) -> HarnessToolsResponse:
    del user
    return HarnessToolsResponse(items=[HarnessToolItem(
        id=item.id, name=item.name, category=item.category.value,
        input_schema=item.input_schema, output_kind=item.output_kind,
        data_locality=item.data_locality.value, governance_level=item.governance_level.value,
        requires_confirmation=item.requires_confirmation,
        cost_dimensions=[value.value for value in item.cost_dimensions],
    ) for item in _get_registry().list()])


@router.get("/runs", response_model=HarnessRunsResponse)
async def harness_runs(
    limit: int = Query(20, ge=1, le=100), run_type: str | None = Query(None),
    status: str | None = Query(None), user: dict = Depends(require_user),
) -> HarnessRunsResponse:
    return HarnessRunsResponse(items=[_run_item(item) for item in _get_store().list_runs(
        user_id=user["id"], run_type=run_type, status=status, limit=limit,
    )])


@router.post("/runs", response_model=HarnessRunItem, status_code=201)
async def create_harness_run(body: CreateHarnessRunRequest, user: dict = Depends(require_user)) -> HarnessRunItem:
    return _run_item(_get_store().create_run(
        user_id=user["id"], run_type=body.run_type, title=body.title,
        goal=body.goal, context_manifest=body.context_manifest,
    ))


@router.get("/runs/{run_id}", response_model=HarnessRunItem)
async def harness_run(run_id: str, user: dict = Depends(require_user)) -> HarnessRunItem:
    try:
        item = _get_store().get_run(run_id, user_id=user["id"])
    except KeyError:
        item = None
    if item is None:
        raise HTTPException(status_code=404, detail="harness run not found")
    return _run_item(item)


@router.post("/runs/{run_id}/cancel", response_model=HarnessRunItem)
async def cancel_harness_run(run_id: str, user: dict = Depends(require_user)) -> HarnessRunItem:
    try:
        item = _get_store().get_run(run_id, user_id=user["id"])
        if item is None:
            raise KeyError(run_id)
        return _run_item(_get_store().cancel_run(run_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="harness run not found") from None
    except InvalidRunTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/assets", response_model=LocalAssetsResponse)
async def harness_assets(
    kind: str | None = Query(None), query: str | None = Query(None, max_length=120),
    user: dict = Depends(require_user),
) -> LocalAssetsResponse:
    del user
    catalog = _get_assets()
    return LocalAssetsResponse(
        items=[LocalAssetItem(**asdict(item)) for item in catalog.list_assets(kind=kind, query=query)],
        summary=LocalAssetSummaryResponse(**asdict(catalog.summary())),
    )


@router.post("/context/preview", response_model=ContextPreviewResponse)
async def harness_context_preview(body: ContextPreviewRequest, user: dict = Depends(require_user)) -> ContextPreviewResponse:
    del user
    manifest = build_context_manifest(
        current_symbol=body.current_symbol,
        cloud_watchlist_refs=body.cloud_watchlist_refs,
        risk_profile_ref=body.risk_profile_ref,
        market_snapshot_ref=body.market_snapshot_ref,
        local_files=[Path(value) for value in body.local_files],
        extra=body.extra,
    )
    return ContextPreviewResponse(**manifest.to_dict())


def register_harness_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/harness/status" for route in app.routes):
        app.include_router(router)
    return router
