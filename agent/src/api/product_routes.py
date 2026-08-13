"""Product lifecycle HTTP routes — Task 5 of the product-closure plan.

Exposes the product domain (catalog / entitlements / credits / orders / devices /
admin) over the API prefixes defined in design §8. Follows the same registration
pattern as ``credits_routes.py``: a single ``register_product_routes(app)``
call, lazy singletons for the domain services, and ``Depends(require_user)`` /
``Depends(require_admin)`` from ``auth_routes`` for auth.

Registration bootstrap (plan Task 5 Step 4 — grant free plan + 50 welcome credits
at registration) is intentionally NOT wired here: it touches the user's
``UserStore.create_user`` / auth registration flow, which the plan's Global
Constraints say to reconcile rather than overwrite. ``current_entitlements``
already defaults ungranted users to ``free``, so the entitlement read is correct
today; the welcome-credit grant is deferred until that reconciliation happens.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth_routes import require_admin, require_user
from src.product.commerce import ActivationError, CommerceService
from src.product.credits import CreditLedger
from src.product.devices import DeviceLimitReached, DeviceService
from src.product.store import ProductStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons (mirror credits_routes.py / admin_redeem_routes.py)
# ---------------------------------------------------------------------------

_store: ProductStore | None = None
_ledger: CreditLedger | None = None
_commerce: CommerceService | None = None
_devices: DeviceService | None = None


def _get_store() -> ProductStore:
    global _store
    if _store is None:
        _store = ProductStore()
    return _store


def _get_ledger() -> CreditLedger:
    global _ledger
    if _ledger is None:
        _ledger = CreditLedger(_get_store())
    return _ledger


def _get_commerce() -> CommerceService:
    global _commerce
    if _commerce is None:
        _commerce = CommerceService(_get_store(), _get_ledger())
    return _commerce


def _get_devices() -> DeviceService:
    global _devices
    if _devices is None:
        _devices = DeviceService(_get_store())
    return _devices


# ---------------------------------------------------------------------------
# Pydantic response/request models
# ---------------------------------------------------------------------------


class PlanView(BaseModel):
    code: str
    name_zh: str
    price_cny_fen: int
    billing_period: str
    monthly_credits: int
    welcome_credits: int
    description: str
    entitlements: dict[str, Any]
    sort_order: int


class CatalogResponse(BaseModel):
    plans: list[PlanView]


class StableRelease(BaseModel):
    version: str
    notes: str
    download_url: str


class EntitlementsResponse(BaseModel):
    plan_code: str
    valid_from: str | None
    valid_until: str | None
    entitlements: dict[str, Any]


class CreditsBalanceResponse(BaseModel):
    available: int
    expiring_soon: int


class ActivateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=1, max_length=128)


class ActivateResponse(BaseModel):
    order_id: str
    plan_code: str
    months: int
    credits_granted: int
    replayed: bool


class OrderItem(BaseModel):
    id: str
    plan_code: str
    status: str
    channel: str
    months: int
    created_at: str
    paid_at: str | None


class OrdersResponse(BaseModel):
    items: list[OrderItem]


class CreateActivationCodeRequest(BaseModel):
    plan_code: str
    months: int = Field(..., ge=1, le=36)
    count: int = Field(1, ge=1, le=100)


class CreatedCodeItem(BaseModel):
    plaintext: str
    code_hash: str
    plan_code: str
    months: int


class CreateActivationCodeResponse(BaseModel):
    codes: list[CreatedCodeItem]


class DeviceItem(BaseModel):
    id: str
    name: str
    created_at: str
    revoked_at: str | None


class DevicesResponse(BaseModel):
    items: list[DeviceItem]


class RevokeDeviceRequest(BaseModel):
    device_id: str


class CreditLotItem(BaseModel):
    id: str
    idempotency_key: str | None
    amount_total: int
    amount_remaining: int
    source: str
    expires_at: str | None
    created_at: str


class CreditLotsResponse(BaseModel):
    lots: list[CreditLotItem]


class LedgerEntryItem(BaseModel):
    id: str
    operation: str
    delta: int
    lot_id: str | None
    idempotency_key: str | None
    created_at: str


class LedgerResponse(BaseModel):
    entries: list[LedgerEntryItem]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

# Environment-driven stable release info; the frontend must not hard-code it.
_STABLE_VERSION_DEFAULT = "0.1.7"


# Module-level router + handlers so the handlers are unit-testable without a
# TestClient (the env's httpx/starlette versions break TestClient). Registration
# just attaches this router to the app.
_router = APIRouter(tags=["product"])


# --- Public catalog ---------------------------------------------------


@_router.get("/api/catalog/plans", response_model=CatalogResponse)
async def list_plans() -> CatalogResponse:
    """Public plan catalog (design §4.1, §7.1 /pricing). No auth."""
    plans = [PlanView(**p) for p in _get_store().list_plans()]
    return CatalogResponse(plans=plans)


@_router.get("/api/catalog/releases/stable", response_model=StableRelease)
async def stable_release() -> StableRelease:
    import os

    return StableRelease(
        version=os.getenv("SIGMX_STABLE_VERSION", _STABLE_VERSION_DEFAULT),
        notes=os.getenv("SIGMX_STABLE_NOTES", ""),
        download_url=os.getenv("SIGMX_STABLE_DOWNLOAD_URL", ""),
    )


# --- Account (require_user) ------------------------------------------


@_router.get("/api/entitlements/me", response_model=EntitlementsResponse)
async def my_entitlements(user: dict = Depends(require_user)) -> EntitlementsResponse:
    # Lazy welcome grant (Task 5 Step 4): seed free plan + 50 credits on first contact.
    _get_commerce().ensure_welcome_grant(user["id"])
    snap = _get_commerce().current_entitlements(user["id"])
    return EntitlementsResponse(
        plan_code=snap.plan_code,
        valid_from=snap.valid_from,
        valid_until=snap.valid_until,
        entitlements=snap.entitlements,
    )


@_router.get("/api/credits/me", response_model=CreditsBalanceResponse)
async def my_credits(user: dict = Depends(require_user)) -> CreditsBalanceResponse:
    # Lazy welcome grant so the balance reflects the one-time 50 credits on first read.
    _get_commerce().ensure_welcome_grant(user["id"])
    bal = _get_ledger().balance(user["id"])
    return CreditsBalanceResponse(available=bal.available, expiring_soon=bal.expiring_soon)


@_router.get("/api/credits/lots", response_model=CreditLotsResponse)
async def my_credits_lots(user: dict = Depends(require_user)) -> CreditLotsResponse:
    """List the user's credit lots with remaining amounts and expiry (design §4.2)."""
    rows = _get_ledger().list_lots(user["id"])
    return CreditLotsResponse(
        lots=[
            CreditLotItem(
                id=r["id"],
                idempotency_key=r.get("idempotency_key"),
                amount_total=r["amount_total"],
                amount_remaining=r["amount_remaining"],
                source=r["source"],
                expires_at=r.get("expires_at"),
                created_at=r["created_at"],
            )
            for r in rows
        ]
    )


@_router.get("/api/credits/ledger", response_model=LedgerResponse)
async def my_credits_ledger(user: dict = Depends(require_user)) -> LedgerResponse:
    """The immutable credit ledger — every grant/reserve/settle/refund (design §4.2)."""
    rows = _get_ledger().list_entries(user["id"])
    return LedgerResponse(
        entries=[
            LedgerEntryItem(
                id=r["id"],
                operation=r["operation"],
                delta=r["delta"],
                lot_id=r.get("lot_id"),
                idempotency_key=r.get("idempotency_key"),
                created_at=r["created_at"],
            )
            for r in rows
        ]
    )


@_router.post("/api/orders/activate", response_model=ActivateResponse)
async def activate_order(
    body: ActivateRequest, user: dict = Depends(require_user)
) -> ActivateResponse:
    try:
        result = _get_commerce().activate_code(user["id"], body.code, body.idempotency_key)
    except ActivationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ActivateResponse(
        order_id=result.order_id,
        plan_code=result.plan_code,
        months=result.months,
        credits_granted=result.credits_granted,
        replayed=result.replayed,
    )


@_router.get("/api/orders", response_model=OrdersResponse)
async def list_orders(user: dict = Depends(require_user)) -> OrdersResponse:
    rows = _get_store()._get_conn().execute(
        "SELECT id, plan_code, status, channel, months, created_at, paid_at "
        "FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return OrdersResponse(items=[OrderItem(**dict(r)) for r in rows])


# --- Devices (require_user) ------------------------------------------


@_router.get("/api/devices", response_model=DevicesResponse)
async def list_devices(user: dict = Depends(require_user)) -> DevicesResponse:
    rows = _get_store()._get_conn().execute(
        "SELECT id, name, created_at, revoked_at FROM devices "
        "WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return DevicesResponse(items=[DeviceItem(**dict(r)) for r in rows])


@_router.post("/api/devices/revoke")
async def revoke_device(
    body: RevokeDeviceRequest, user: dict = Depends(require_user)
) -> dict:
    _get_devices().revoke(user_id=user["id"], device_id=body.device_id)
    return {"ok": True}


# --- Admin operations (require_admin) --------------------------------


@_router.post(
    "/api/admin/activation-codes",
    response_model=CreateActivationCodeResponse,
)
async def create_activation_codes(
    body: CreateActivationCodeRequest, _: dict = Depends(require_admin)
) -> CreateActivationCodeResponse:
    try:
        # Plan codes are created one at a time by the service; honor count.
        codes = [
            _get_commerce().admin_create_activation_code(
                plan=body.plan_code, months=body.months
            )
            for _ in range(body.count)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except DeviceLimitReached as exc:  # pragma: no cover - not raised here
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return CreateActivationCodeResponse(
        codes=[
            CreatedCodeItem(
                plaintext=c.plaintext, code_hash=c.code_hash,
                plan_code=c.plan_code, months=c.months,
            )
            for c in codes
        ]
    )


def register_product_routes(app: FastAPI) -> APIRouter:
    """Attach the product router to ``app``. Idempotent across reloads."""
    already = any(getattr(r, "path", "") == "/api/catalog/plans" for r in app.routes)
    if not already:
        app.include_router(_router)
    logger.info("Product lifecycle routes registered")
    return _router
