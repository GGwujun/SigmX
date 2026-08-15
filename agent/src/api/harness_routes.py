"""Authenticated Desktop APIs for the Financial Harness product contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.harness.context import build_context_manifest
from src.harness.registry import HarnessToolRegistry
from src.harness.runs import HarnessRunAdapter


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
    status: str
    started_at: str | None
    finished_at: str | None
    context_manifest: dict[str, Any]
    tool_calls: list[str]
    evidence_refs: list[str]
    costs: dict[str, int | float]
    degradations: list[str]
    result_ref: str | None


class HarnessRunsResponse(BaseModel):
    items: list[HarnessRunItem]


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
_runs: HarnessRunAdapter | None = None


def _get_registry() -> HarnessToolRegistry:
    global _registry
    if _registry is None:
        from src.tools import build_registry
        _registry = HarnessToolRegistry.from_tool_registry(build_registry(include_shell_tools=False, interactive=False))
    return _registry


def _get_runs() -> HarnessRunAdapter:
    global _runs
    if _runs is None:
        from src.session.store import SessionStore
        from src.swarm.store import SwarmStore, swarm_runs_root
        agent_root = Path(__file__).resolve().parents[2]
        _runs = HarnessRunAdapter(SessionStore(agent_root / "sessions"), SwarmStore(swarm_runs_root()))
    return _runs


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
async def harness_runs(limit: int = Query(20, ge=1, le=100), user: dict = Depends(require_user)) -> HarnessRunsResponse:
    del user
    return HarnessRunsResponse(items=[HarnessRunItem(**item.to_dict()) for item in _get_runs().list(limit)])


@router.get("/runs/{run_id}", response_model=HarnessRunItem)
async def harness_run(run_id: str, user: dict = Depends(require_user)) -> HarnessRunItem:
    del user
    item = next((value for value in _get_runs().list(100) if value.run_id == run_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="harness run not found")
    return HarnessRunItem(**item.to_dict())


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
