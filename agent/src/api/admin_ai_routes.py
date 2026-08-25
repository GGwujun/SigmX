"""Administrator APIs for the platform-owned AI research runtime."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.api.auth_routes import require_admin
from src.product.ai_runtime_config import AIConfigurationError, AIRuntimeConfigService


class ProviderInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    models: list[str] = Field(default_factory=list, max_length=50)
    enabled: bool = True


class ProviderResponse(BaseModel):
    code: str
    name: str
    base_url: str
    models: list[str]
    enabled: bool
    api_key_masked: str | None
    configured: bool
    updated_at: str


class StrategyInput(BaseModel):
    planning_provider: str
    planning_model: str
    execution_provider: str
    execution_model: str
    summary_provider: str
    summary_model: str
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=8000, ge=256, le=200000)
    timeout_seconds: int = Field(default=90, ge=5, le=900)
    max_retries: int = Field(default=2, ge=0, le=5)


class SourceInput(BaseModel):
    enabled: bool
    priority: int = Field(ge=0, le=10000)
    markets: list[str] = Field(default_factory=list)


router = APIRouter(
    prefix="/api/admin/ai",
    tags=["admin-ai"],
    dependencies=[Depends(require_admin)],
)
_service: AIRuntimeConfigService | None = None


def _get_service() -> AIRuntimeConfigService:
    global _service
    if _service is None:
        from src.api.product_routes import _get_store

        _service = AIRuntimeConfigService(_get_store())
    return _service


def _actor(admin: dict) -> str:
    return str(admin.get("email") or admin.get("id") or "admin")


@router.get("/providers", response_model=list[ProviderResponse])
def list_providers(admin: dict = Depends(require_admin)) -> list[ProviderResponse]:
    del admin
    return [ProviderResponse(**asdict(item)) for item in _get_service().list_providers()]


@router.put("/providers/{code}", response_model=ProviderResponse)
def save_provider(code: str, body: ProviderInput, admin: dict = Depends(require_admin)) -> ProviderResponse:
    try:
        item = _get_service().save_provider(code=code, actor=_actor(admin), **body.model_dump())
        return ProviderResponse(**asdict(item))
    except (ValueError, AIConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/strategy")
def save_strategy(body: StrategyInput, admin: dict = Depends(require_admin)) -> dict:
    try:
        _get_service().save_strategy(actor=_actor(admin), **body.model_dump())
        return {"ok": True}
    except (ValueError, AIConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/sources/{code}")
def save_source(code: str, body: SourceInput, admin: dict = Depends(require_admin)) -> dict:
    try:
        return asdict(_get_service().save_source(code, actor=_actor(admin), **body.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/health")
def ai_health(admin: dict = Depends(require_admin)) -> dict:
    del admin
    try:
        config = _get_service().get_effective()
        return {"configured": True, "planning_model": config.planning.model, "sources": [item.code for item in config.sources]}
    except AIConfigurationError as exc:
        return {"configured": False, "detail": str(exc)}


def register_admin_ai_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/admin/ai/providers" for route in app.routes):
        app.include_router(router)
    return router
