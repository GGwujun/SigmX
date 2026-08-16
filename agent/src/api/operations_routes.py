"""Admin and Desktop telemetry APIs for personal product operations."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_admin, require_user
from src.product.operations import ProductOperations


class ProductUpdate(BaseModel):
    enabled: bool
    price_cny_fen: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=500)


class EndpointUpdate(BaseModel):
    enabled: bool
    credit_cost: int = Field(ge=0)
    unit_cost_cny_fen: float = Field(ge=0)
    quality_score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=5, max_length=500)


class ContentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    href: str = Field(min_length=1, max_length=500)
    enabled: bool
    reason: str = Field(min_length=5, max_length=500)


class RefundRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class DesktopEventRequest(BaseModel):
    event: str = Field(pattern="^(installed|activated|connected_enabled|research_started|research_completed)$")
    session_id: str = Field(min_length=1, max_length=128)


class OperationsStateResponse(BaseModel):
    products: list[dict]
    endpoints: list[dict]
    content: list[dict]
    refunds: list[dict]
    metrics: dict
    audit: list[dict]


admin_router = APIRouter(prefix="/api/admin/operations", tags=["operations"], dependencies=[Depends(require_admin)])
telemetry_router = APIRouter(prefix="/api/desktop/telemetry", tags=["desktop-telemetry"], dependencies=[Depends(require_user)])
_operations: ProductOperations | None = None


def _get_operations() -> ProductOperations:
    global _operations
    if _operations is None:
        from src.api import product_routes
        _operations = ProductOperations(product_routes._get_store())
    return _operations


def _actor(admin: dict) -> str:
    return str(admin.get("email") or admin.get("id") or "admin")


@admin_router.get("", response_model=OperationsStateResponse)
async def operations_state(days: int = Query(30, ge=7, le=365), admin: dict = Depends(require_admin)) -> OperationsStateResponse:
    del admin
    ops = _get_operations()
    return OperationsStateResponse(
        products=[asdict(item) for item in ops.products()], endpoints=[asdict(item) for item in ops.endpoints()],
        content=[asdict(item) for item in ops.content()], refunds=[asdict(item) for item in ops.refunds()],
        metrics=asdict(ops.metrics(days=days)), audit=[asdict(item) for item in ops.audit_log()],
    )


@admin_router.put("/products/{code}")
async def put_product(code: str, body: ProductUpdate, admin: dict = Depends(require_admin)) -> dict:
    return asdict(_get_operations().upsert_product(code, enabled=body.enabled, price_cny_fen=body.price_cny_fen, actor_id=_actor(admin), reason=body.reason))


@admin_router.put("/endpoints/{code}")
async def put_endpoint(code: str, body: EndpointUpdate, admin: dict = Depends(require_admin)) -> dict:
    return asdict(_get_operations().upsert_endpoint(code, enabled=body.enabled, credit_cost=body.credit_cost, unit_cost_cny_fen=body.unit_cost_cny_fen, quality_score=body.quality_score, actor_id=_actor(admin), reason=body.reason))


@admin_router.put("/content/{slot}")
async def put_content(slot: str, body: ContentUpdate, admin: dict = Depends(require_admin)) -> dict:
    return asdict(_get_operations().upsert_content(slot, title=body.title, href=body.href, enabled=body.enabled, actor_id=_actor(admin), reason=body.reason))


@admin_router.post("/orders/{order_id}/refund")
async def refund_order(order_id: str, body: RefundRequest, admin: dict = Depends(require_admin)) -> dict:
    try:
        return asdict(_get_operations().refund_activation_order(order_id, actor_id=_actor(admin), reason=body.reason, idempotency_key=body.idempotency_key))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="activation order not found") from exc


@telemetry_router.post("/events", status_code=202)
async def desktop_event(body: DesktopEventRequest, user: dict = Depends(require_user)) -> dict:
    _get_operations().record_desktop_event(user["id"], body.event, session_id=body.session_id)
    return {"accepted": True}


def register_operations_routes(app: FastAPI) -> None:
    if not any(getattr(route, "path", "") == "/api/admin/operations" for route in app.routes):
        app.include_router(admin_router)
        app.include_router(telemetry_router)
