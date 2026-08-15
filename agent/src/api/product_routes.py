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
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.auth_routes import require_admin, require_user
from src.product.commerce import ActivationError, CommerceService
from src.product.cloud_research import (
    CloudResearchService,
    ReportNotFound,
    ReportRevoked,
)
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.datahub_catalog import DataHubEndpointCatalog
from src.product.datahub_budgets import DataHubBudgetService
from src.product.notifications import PersonalNotificationService
from src.product.funnel import PersonalFunnelService
from src.product.support_operations import PersonalSupportOperations, SupportTargetNotFound
from src.product.subscriptions import SavedQuerySubscriptionService
from src.product.datahub_credentials import (
    CredentialLimitReached,
    CredentialNotFound,
    CredentialRevoked,
    DataHubCredentialService,
)
from src.product.devices import DeviceLimitReached, DeviceService
from src.product.research_handoffs import (
    HandoffExpired,
    HandoffNotFound,
    HandoffUsed,
    ResearchHandoffService,
)
from src.product.store import ProductStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons (mirror credits_routes.py / admin_redeem_routes.py)
# ---------------------------------------------------------------------------

_store: ProductStore | None = None
_ledger: CreditLedger | None = None
_commerce: CommerceService | None = None
_devices: DeviceService | None = None
_data_ledger: DataCreditLedger | None = None
_endpoint_catalog: DataHubEndpointCatalog | None = None
_credential_service: DataHubCredentialService | None = None
_cloud_research: CloudResearchService | None = None
_research_handoffs: ResearchHandoffService | None = None
_budget_service: DataHubBudgetService | None = None
_notification_service: PersonalNotificationService | None = None
_subscription_service: SavedQuerySubscriptionService | None = None
_funnel_service: PersonalFunnelService | None = None
_support_operations: PersonalSupportOperations | None = None


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


def _get_data_ledger() -> DataCreditLedger:
    global _data_ledger
    if _data_ledger is None:
        _data_ledger = DataCreditLedger(_get_store())
    return _data_ledger


def _get_endpoint_catalog() -> DataHubEndpointCatalog:
    global _endpoint_catalog
    if _endpoint_catalog is None:
        _endpoint_catalog = DataHubEndpointCatalog(_get_store())
    return _endpoint_catalog


def _get_credential_service() -> DataHubCredentialService:
    global _credential_service
    if _credential_service is None:
        _credential_service = DataHubCredentialService(_get_store())
    return _credential_service


def _get_cloud_research() -> CloudResearchService:
    global _cloud_research
    if _cloud_research is None:
        _cloud_research = CloudResearchService(_get_store())
    return _cloud_research


def _get_research_handoffs() -> ResearchHandoffService:
    global _research_handoffs
    if _research_handoffs is None:
        _research_handoffs = ResearchHandoffService(_get_store())
    return _research_handoffs


def _get_budget_service() -> DataHubBudgetService:
    global _budget_service
    if _budget_service is None:
        _budget_service = DataHubBudgetService(_get_store())
    return _budget_service


def _get_notifications() -> PersonalNotificationService:
    global _notification_service
    if _notification_service is None:
        _notification_service = PersonalNotificationService(_get_store())
    return _notification_service


def _get_subscriptions() -> SavedQuerySubscriptionService:
    global _subscription_service
    if _subscription_service is None:
        _subscription_service = SavedQuerySubscriptionService(_get_store())
    return _subscription_service


def _get_funnel() -> PersonalFunnelService:
    global _funnel_service
    if _funnel_service is None:
        _funnel_service = PersonalFunnelService(_get_store())
    return _funnel_service


def _get_support_operations() -> PersonalSupportOperations:
    global _support_operations
    if _support_operations is None:
        _support_operations = PersonalSupportOperations(_get_store())
    return _support_operations


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


class DataCreditPackView(BaseModel):
    code: str
    name_zh: str
    credits: int
    price_cny_fen: int
    valid_days: int
    enabled: bool
    sort_order: int


class DataCreditPackCatalogResponse(BaseModel):
    items: list[DataCreditPackView]


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
    price_cny_fen: int
    months: int
    created_at: str
    paid_at: str | None


class OrdersResponse(BaseModel):
    items: list[OrderItem]


class BillingDailyItem(BaseModel):
    date: str
    research_credits_consumed: int
    data_credits_consumed: int
    paid_cny_fen: int


class BillingSummaryResponse(BaseModel):
    period_days: int
    paid_orders: int
    paid_cny_fen: int
    research_credits_consumed: int
    data_credits_consumed: int
    daily: list[BillingDailyItem]


class NotificationItem(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    read_at: str | None
    created_at: str


class NotificationsResponse(BaseModel):
    items: list[NotificationItem]


class NotificationPreferencesResponse(BaseModel):
    budget_alerts: bool
    product_updates: bool
    cloud_tasks: bool


class PutNotificationPreferencesRequest(NotificationPreferencesResponse):
    pass


class AdminProductMetricsResponse(BaseModel):
    period_days: int
    active_entitled_users: int
    plan_distribution: dict[str, int]
    paid_orders: int
    revenue_cny_fen: int
    active_datahub_credentials: int
    datahub_requests: int
    datahub_success_rate: float
    data_credits_charged: int
    weekly_effective_research_users: int
    personal_funnel: dict[str, int]


class PersonalFunnelEventRequest(BaseModel):
    anonymous_session_id: str = Field(..., min_length=16, max_length=64)
    event_name: str = Field(..., min_length=1, max_length=40)


class AdminCompensateCreditsRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    ledger: str
    amount: int = Field(..., ge=1, le=1_000_000)
    reason: str = Field(..., min_length=5, max_length=500)


class AdminSecurityRevokeRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    target_id: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(..., min_length=5, max_length=500)


class SavedQuerySubscriptionItem(BaseModel):
    id: str
    saved_query_id: str
    query: str
    frequency: str
    next_run_at: str
    last_run_at: str | None
    created_at: str


class SavedQuerySubscriptionsResponse(BaseModel):
    items: list[SavedQuerySubscriptionItem]


class PutSavedQuerySubscriptionRequest(BaseModel):
    saved_query_id: str
    frequency: str


class CreateActivationCodeRequest(BaseModel):
    plan_code: str
    months: int = Field(..., ge=1, le=36)
    count: int = Field(1, ge=1, le=100)


class CreateDataCreditCodeRequest(BaseModel):
    pack_code: str
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


# ---- Device authorization flow (Task 9) ----


class DeviceAuthorizeStartRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=128)
    fingerprint_hash: str = Field(..., min_length=1, max_length=128)


class DeviceAuthorizeStartResponse(BaseModel):
    device_code: str
    user_code: str
    verification_url: str
    interval_seconds: int
    expires_in_seconds: int


class DeviceAuthorizeApproveRequest(BaseModel):
    user_code: str = Field(..., min_length=1, max_length=32)


class DeviceAuthorizePollRequest(BaseModel):
    device_code: str = Field(..., min_length=1)


class DeviceAuthorizePollResponse(BaseModel):
    status: str  # pending | approved | expired
    access_token: str | None = None
    refresh_token: str | None = None
    device_id: str | None = None
    interval_seconds: int = 5


class DeviceTokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class DeviceTokenRefreshResponse(BaseModel):
    status: str  # ok | revoked
    access_token: str | None = None
    refresh_token: str | None = None


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


class DataCreditsBalanceResponse(BaseModel):
    available: int
    expiring_soon: int


class DataCreditLotItem(BaseModel):
    id: str
    idempotency_key: str
    amount_total: int
    amount_remaining: int
    source: str
    expires_at: str | None
    created_at: str


class DataCreditLotsResponse(BaseModel):
    lots: list[DataCreditLotItem]


class DataCreditLedgerItem(BaseModel):
    id: str
    operation: str
    delta: int
    lot_id: str | None
    reservation_id: str | None
    created_at: str


class DataCreditLedgerResponse(BaseModel):
    entries: list[DataCreditLedgerItem]


class DataHubEndpointItem(BaseModel):
    endpoint_code: str
    catalog_version: int
    http_method: str
    path_pattern: str
    dataset_group: str
    pricing_mode: str
    base_cost: int
    unit_name: str | None
    unit_size: int | None
    unit_cost: int | None
    max_cost: int | None
    enabled: bool


class DataHubCatalogResponse(BaseModel):
    items: list[DataHubEndpointItem]


class CreateDataHubCredentialRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(..., min_length=1)
    ip_allowlist: list[str] = Field(default_factory=list)
    expires_at: str | None = None


class CreateDesktopDataHubSessionRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=128)


class DataHubCredentialItem(BaseModel):
    id: str
    key_prefix: str
    name: str
    scopes: list[str]
    ip_allowlist: list[str]
    expires_at: str | None
    last_used_at: str | None
    created_at: str
    revoked_at: str | None


class CreatedDataHubCredentialResponse(DataHubCredentialItem):
    plaintext: str


class DataHubCredentialsResponse(BaseModel):
    items: list[DataHubCredentialItem]


class DataHubUsageByEndpointItem(BaseModel):
    endpoint_code: str
    requests: int
    successful_requests: int
    credits_charged: int


class DataHubUsageResponse(BaseModel):
    total_requests: int
    successful_requests: int
    credits_charged: int
    by_endpoint: list[DataHubUsageByEndpointItem]


class DataHubRequestLogItem(BaseModel):
    request_id: str
    credential_id: str
    credential_name: str
    key_prefix: str
    endpoint_code: str
    status_code: int
    requested_units: int
    actual_units: int
    credits_authorized: int
    credits_charged: int
    duration_ms: int
    error_code: str | None
    created_at: str


class DataHubRequestLogsResponse(BaseModel):
    items: list[DataHubRequestLogItem]
    next_cursor: str | None


class PutDataHubBudgetRequest(BaseModel):
    daily_limit: int | None = Field(default=None, ge=1)


class DataHubBudgetResponse(BaseModel):
    credential_id: str
    daily_limit: int
    spent_today: int
    remaining_today: int
    utc_date: str


class DataHubBudgetsResponse(BaseModel):
    items: list[DataHubBudgetResponse]


class DataHubBudgetAlertItem(BaseModel):
    credential_id: str
    credential_name: str
    utc_date: str
    threshold_percent: int
    spent: int
    daily_limit: int
    created_at: str


class DataHubBudgetAlertsResponse(BaseModel):
    items: list[DataHubBudgetAlertItem]


class SaveCloudQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    result_summary: dict[str, Any] = Field(default_factory=dict)


class CloudQueryItem(BaseModel):
    id: str
    query: str
    result_summary: dict[str, Any]
    created_at: str


class CloudQueriesResponse(BaseModel):
    items: list[CloudQueryItem]


class AddCloudWatchlistRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    name: str = Field("", max_length=128)


class CloudWatchlistItemResponse(BaseModel):
    symbol: str
    name: str
    created_at: str


class CloudWatchlistResponse(BaseModel):
    items: list[CloudWatchlistItemResponse]


class PublishCloudReportRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=20_000)


class CloudReportResponse(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    created_at: str
    revoked_at: str | None


class CloudReportsResponse(BaseModel):
    items: list[CloudReportResponse]


class CreateResearchHandoffRequest(BaseModel):
    kind: str = Field(..., min_length=1, max_length=32)
    payload: dict[str, Any]


class CreatedResearchHandoffResponse(BaseModel):
    id: str
    token: str
    deep_link: str
    expires_at: str


class ConsumedResearchHandoffResponse(BaseModel):
    id: str
    kind: str
    payload: dict[str, str]
    created_at: str


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


@_router.post("/api/public/funnel-events", status_code=status.HTTP_202_ACCEPTED)
async def record_personal_funnel_event(body: PersonalFunnelEventRequest) -> dict:
    try:
        accepted = _get_funnel().record(body.anonymous_session_id, body.event_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"accepted": accepted}


@_router.get("/api/catalog/plans", response_model=CatalogResponse)
async def list_plans() -> CatalogResponse:
    """Public plan catalog (design §4.1, §7.1 /pricing). No auth."""
    plans = [PlanView(**p) for p in _get_store().list_plans()]
    return CatalogResponse(plans=plans)


@_router.get("/api/catalog/data-credit-packs", response_model=DataCreditPackCatalogResponse)
async def list_data_credit_packs() -> DataCreditPackCatalogResponse:
    return DataCreditPackCatalogResponse(
        items=[DataCreditPackView(**item) for item in _get_store().list_data_credit_packs()]
    )


@_router.get("/api/datahub/catalog", response_model=DataHubCatalogResponse)
async def datahub_catalog() -> DataHubCatalogResponse:
    """Public, enabled latest-version Data Hub endpoint price list."""
    return DataHubCatalogResponse(
        items=[DataHubEndpointItem(**vars(entry)) for entry in _get_endpoint_catalog().list()]
    )


def _query_item(item) -> CloudQueryItem:
    return CloudQueryItem(id=item.id, query=item.query, result_summary=item.result_summary, created_at=item.created_at)


def _watchlist_item(item) -> CloudWatchlistItemResponse:
    return CloudWatchlistItemResponse(symbol=item.symbol, name=item.name, created_at=item.created_at)


def _report_item(item) -> CloudReportResponse:
    return CloudReportResponse(id=item.id, slug=item.slug, title=item.title, summary=item.summary, created_at=item.created_at, revoked_at=item.revoked_at)


@_router.post("/api/cloud/queries", response_model=CloudQueryItem)
async def save_cloud_query(body: SaveCloudQueryRequest, user: dict = Depends(require_user)) -> CloudQueryItem:
    try:
        return _query_item(_get_cloud_research().save_query(user["id"], body.query, body.result_summary))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@_router.get("/api/cloud/queries", response_model=CloudQueriesResponse)
async def list_cloud_queries(user: dict = Depends(require_user)) -> CloudQueriesResponse:
    return CloudQueriesResponse(items=[_query_item(item) for item in _get_cloud_research().list_saved_queries(user["id"])])


@_router.post("/api/cloud/watchlist", response_model=CloudWatchlistItemResponse)
async def add_cloud_watchlist(body: AddCloudWatchlistRequest, user: dict = Depends(require_user)) -> CloudWatchlistItemResponse:
    try:
        return _watchlist_item(_get_cloud_research().add_watchlist(user["id"], body.symbol, body.name))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@_router.get("/api/cloud/watchlist", response_model=CloudWatchlistResponse)
async def list_cloud_watchlist(user: dict = Depends(require_user)) -> CloudWatchlistResponse:
    return CloudWatchlistResponse(items=[_watchlist_item(item) for item in _get_cloud_research().list_watchlist(user["id"])])


@_router.delete("/api/cloud/watchlist/{symbol}")
async def remove_cloud_watchlist(symbol: str, user: dict = Depends(require_user)) -> dict:
    if not _get_cloud_research().remove_watchlist(user["id"], symbol):
        raise HTTPException(status_code=404, detail="watchlist item not found")
    return {"ok": True}


@_router.post("/api/cloud/reports", response_model=CloudReportResponse)
async def publish_cloud_report(body: PublishCloudReportRequest, user: dict = Depends(require_user)) -> CloudReportResponse:
    try:
        return _report_item(_get_cloud_research().publish_report(user["id"], body.title, body.summary))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@_router.get("/api/cloud/reports", response_model=CloudReportsResponse)
async def list_cloud_reports(user: dict = Depends(require_user)) -> CloudReportsResponse:
    return CloudReportsResponse(items=[_report_item(item) for item in _get_cloud_research().list_reports(user["id"])])


@_router.delete("/api/cloud/reports/{report_id}")
async def revoke_cloud_report(report_id: str, user: dict = Depends(require_user)) -> dict:
    if not _get_cloud_research().revoke_report(user["id"], report_id):
        raise HTTPException(status_code=404, detail="report not found")
    return {"ok": True}


@_router.get("/api/public/reports/{slug}", response_model=CloudReportResponse)
async def public_cloud_report(slug: str) -> CloudReportResponse:
    try:
        return _report_item(_get_cloud_research().get_public_report(slug))
    except ReportRevoked as exc:
        raise HTTPException(status_code=410, detail="report has been revoked") from exc
    except ReportNotFound as exc:
        raise HTTPException(status_code=404, detail="report not found") from exc


@_router.post("/api/cloud/handoffs", response_model=CreatedResearchHandoffResponse)
async def create_research_handoff(
    body: CreateResearchHandoffRequest, user: dict = Depends(require_user)
) -> CreatedResearchHandoffResponse:
    try:
        created = _get_research_handoffs().create(user["id"], body.kind, body.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreatedResearchHandoffResponse(**vars(created))


@_router.post(
    "/api/cloud/handoffs/{token}/consume",
    response_model=ConsumedResearchHandoffResponse,
)
async def consume_research_handoff(
    token: str, user: dict = Depends(require_user)
) -> ConsumedResearchHandoffResponse:
    try:
        consumed = _get_research_handoffs().consume(user["id"], token)
    except HandoffNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (HandoffExpired, HandoffUsed) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ConsumedResearchHandoffResponse(**vars(consumed))


def _credential_item(value) -> DataHubCredentialItem:
    return DataHubCredentialItem(
        id=value.id,
        key_prefix=value.key_prefix,
        name=value.name,
        scopes=list(value.scopes),
        ip_allowlist=list(value.ip_allowlist),
        expires_at=value.expires_at,
        last_used_at=getattr(value, "last_used_at", None),
        created_at=value.created_at,
        revoked_at=getattr(value, "revoked_at", None),
    )


def _created_credential(value) -> CreatedDataHubCredentialResponse:
    return CreatedDataHubCredentialResponse(
        **_credential_item(value).model_dump(), plaintext=value.plaintext
    )


@_router.post("/api/datahub/credentials", response_model=CreatedDataHubCredentialResponse)
async def create_datahub_credential(
    body: CreateDataHubCredentialRequest, user: dict = Depends(require_user)
) -> CreatedDataHubCredentialResponse:
    try:
        created = _get_credential_service().create(
            user["id"], body.name, body.scopes, body.ip_allowlist, body.expires_at
        )
    except CredentialLimitReached as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _created_credential(created)


@_router.post(
    "/api/datahub/desktop-session",
    response_model=CreatedDataHubCredentialResponse,
)
async def create_desktop_datahub_session(
    body: CreateDesktopDataHubSessionRequest,
    user: dict = Depends(require_user),
) -> CreatedDataHubCredentialResponse:
    device = _get_store()._get_conn().execute(
        "SELECT id FROM devices WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
        (body.device_id, user["id"]),
    ).fetchone()
    if device is None:
        raise HTTPException(status_code=404, detail="active device not found")
    snapshot = _get_commerce().current_entitlements(user["id"])
    if not snapshot.entitlements.get("desktop.connected_mode", False):
        raise HTTPException(status_code=403, detail="connected mode is not enabled")
    groups = snapshot.entitlements.get("datahub.dataset_groups", [])
    scopes = [f"group:{group}" for group in groups]
    if not scopes:
        raise HTTPException(status_code=403, detail="no Data Hub datasets are enabled")
    return _created_credential(
        _get_credential_service().create_desktop_session(
            user["id"], body.device_id, scopes
        )
    )


@_router.get("/api/datahub/credentials", response_model=DataHubCredentialsResponse)
async def list_datahub_credentials(
    user: dict = Depends(require_user),
) -> DataHubCredentialsResponse:
    return DataHubCredentialsResponse(
        items=[_credential_item(item) for item in _get_credential_service().list(user["id"])]
    )


@_router.post(
    "/api/datahub/credentials/{credential_id}/rotate",
    response_model=CreatedDataHubCredentialResponse,
)
async def rotate_datahub_credential(
    credential_id: str, user: dict = Depends(require_user)
) -> CreatedDataHubCredentialResponse:
    try:
        return _created_credential(
            _get_credential_service().rotate(user["id"], credential_id)
        )
    except CredentialNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CredentialRevoked as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@_router.delete("/api/datahub/credentials/{credential_id}")
async def revoke_datahub_credential(
    credential_id: str, user: dict = Depends(require_user)
) -> dict:
    try:
        _get_credential_service().revoke(user["id"], credential_id)
    except CredentialNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@_router.get("/api/datahub/usage", response_model=DataHubUsageResponse)
async def datahub_usage(user: dict = Depends(require_user)) -> DataHubUsageResponse:
    conn = _get_store()._get_conn()
    totals = conn.execute(
        "SELECT COUNT(*) AS requests, "
        "SUM(CASE WHEN status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END) AS successes, "
        "COALESCE(SUM(credits_charged), 0) AS credits "
        "FROM datahub_request_usage WHERE user_id = ?",
        (user["id"],),
    ).fetchone()
    groups = conn.execute(
        "SELECT endpoint_code, COUNT(*) AS requests, "
        "SUM(CASE WHEN status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END) AS successes, "
        "COALESCE(SUM(credits_charged), 0) AS credits "
        "FROM datahub_request_usage WHERE user_id = ? GROUP BY endpoint_code "
        "ORDER BY endpoint_code",
        (user["id"],),
    ).fetchall()
    return DataHubUsageResponse(
        total_requests=int(totals["requests"] or 0),
        successful_requests=int(totals["successes"] or 0),
        credits_charged=int(totals["credits"] or 0),
        by_endpoint=[
            DataHubUsageByEndpointItem(
                endpoint_code=row["endpoint_code"],
                requests=int(row["requests"]),
                successful_requests=int(row["successes"] or 0),
                credits_charged=int(row["credits"] or 0),
            )
            for row in groups
        ],
    )


@_router.get("/api/datahub/logs", response_model=DataHubRequestLogsResponse)
async def datahub_logs(
    limit: int = Query(50, ge=1, le=200),
    before: str | None = Query(None),
    errors_only: bool = Query(False),
    user: dict = Depends(require_user),
) -> DataHubRequestLogsResponse:
    clauses = ["u.user_id=?"]
    params: list[Any] = [user["id"]]
    if errors_only:
        clauses.append("(u.error_code IS NOT NULL OR u.status_code < 200 OR u.status_code >= 300)")
    if before:
        try:
            created_at, request_id = before.rsplit("~", 1)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid log cursor") from exc
        clauses.append("(u.created_at < ? OR (u.created_at = ? AND u.request_id < ?))")
        params.extend([created_at, created_at, request_id])
    params.append(limit)
    rows = _get_store()._get_conn().execute(
        "SELECT u.*, c.name credential_name, c.key_prefix FROM datahub_request_usage u "
        "JOIN datahub_credentials c ON c.id=u.credential_id WHERE " + " AND ".join(clauses) +
        " ORDER BY u.created_at DESC, u.request_id DESC LIMIT ?",
        tuple(params),
    ).fetchall()
    items = [DataHubRequestLogItem(**dict(row)) for row in rows]
    cursor = f"{rows[-1]['created_at']}~{rows[-1]['request_id']}" if len(rows) == limit else None
    return DataHubRequestLogsResponse(items=items, next_cursor=cursor)


@_router.get(
    "/api/datahub/credentials/{credential_id}/budget",
    response_model=DataHubBudgetResponse,
)
async def get_datahub_budget(
    credential_id: str, user: dict = Depends(require_user)
) -> DataHubBudgetResponse:
    budget = _get_budget_service().get(user["id"], credential_id)
    if budget is None:
        raise HTTPException(status_code=404, detail="credential budget not found")
    return DataHubBudgetResponse(**vars(budget))


@_router.get("/api/datahub/budgets", response_model=DataHubBudgetsResponse)
async def list_datahub_budgets(
    user: dict = Depends(require_user),
) -> DataHubBudgetsResponse:
    return DataHubBudgetsResponse(items=[
        DataHubBudgetResponse(**vars(item)) for item in _get_budget_service().list(user["id"])
    ])


@_router.put(
    "/api/datahub/credentials/{credential_id}/budget",
    response_model=DataHubBudgetResponse | None,
)
async def put_datahub_budget(
    credential_id: str,
    body: PutDataHubBudgetRequest,
    user: dict = Depends(require_user),
) -> DataHubBudgetResponse | None:
    try:
        budget = _get_budget_service().set(user["id"], credential_id, body.daily_limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DataHubBudgetResponse(**vars(budget)) if budget else None


@_router.get("/api/datahub/budget-alerts", response_model=DataHubBudgetAlertsResponse)
async def datahub_budget_alerts(
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(require_user),
) -> DataHubBudgetAlertsResponse:
    return DataHubBudgetAlertsResponse(items=[
        DataHubBudgetAlertItem(**vars(item))
        for item in _get_budget_service().list_events(user["id"], limit)
    ])


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


@_router.get("/api/data-credits/me", response_model=DataCreditsBalanceResponse)
async def my_data_credits(user: dict = Depends(require_user)) -> DataCreditsBalanceResponse:
    from datetime import datetime, timezone

    plan = _get_commerce().current_entitlements(user["id"]).plan_code
    _get_commerce().ensure_monthly_data_grant(
        user["id"], plan, datetime.now(timezone.utc).date()
    )
    balance = _get_data_ledger().balance(user["id"])
    return DataCreditsBalanceResponse(
        available=balance.available, expiring_soon=balance.expiring_soon
    )


@_router.get("/api/data-credits/lots", response_model=DataCreditLotsResponse)
async def my_data_credit_lots(user: dict = Depends(require_user)) -> DataCreditLotsResponse:
    return DataCreditLotsResponse(
        lots=[DataCreditLotItem(**row) for row in _get_data_ledger().list_lots(user["id"])]
    )


@_router.get("/api/data-credits/ledger", response_model=DataCreditLedgerResponse)
async def my_data_credit_ledger(user: dict = Depends(require_user)) -> DataCreditLedgerResponse:
    rows = _get_data_ledger().list_entries(user["id"])
    return DataCreditLedgerResponse(
        entries=[
            DataCreditLedgerItem(
                id=row["id"],
                operation=row["operation"],
                delta=row["delta"],
                lot_id=row.get("lot_id"),
                reservation_id=row.get("reservation_id"),
                created_at=row["created_at"],
            )
            for row in rows
        ]
    )


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


@_router.post("/api/data-credits/redeem", response_model=ActivateResponse)
async def redeem_data_credit_pack(
    body: ActivateRequest, user: dict = Depends(require_user)
) -> ActivateResponse:
    try:
        result = _get_commerce().redeem_data_credit_code(
            user["id"], body.code, body.idempotency_key
        )
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ActivateResponse(
        order_id=result.order_id,
        plan_code=result.plan_code,
        months=0,
        credits_granted=result.credits_granted,
        replayed=result.replayed,
    )


@_router.get("/api/orders", response_model=OrdersResponse)
async def list_orders(user: dict = Depends(require_user)) -> OrdersResponse:
    rows = _get_store()._get_conn().execute(
        "SELECT id, plan_code, status, channel, price_cny_fen, months, created_at, paid_at "
        "FROM orders WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return OrdersResponse(items=[OrderItem(**dict(r)) for r in rows])


@_router.get("/api/billing/summary", response_model=BillingSummaryResponse)
async def billing_summary(
    days: int = Query(30, ge=7, le=365),
    user: dict = Depends(require_user),
) -> BillingSummaryResponse:
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
    conn = _get_store()._get_conn()
    orders = conn.execute(
        "SELECT paid_at, price_cny_fen FROM orders WHERE user_id=? AND status='paid' "
        "AND paid_at IS NOT NULL AND paid_at>=?",
        (user["id"], start),
    ).fetchall()
    research = conn.execute(
        "SELECT created_at, amount FROM credit_reservations WHERE user_id=? "
        "AND status='settled' AND created_at>=?",
        (user["id"], start),
    ).fetchall()
    data = conn.execute(
        "SELECT settled_at, amount_settled FROM data_credit_reservations "
        "WHERE owner_id=? AND status='settled' AND settled_at IS NOT NULL AND settled_at>=?",
        (user["id"], start),
    ).fetchall()
    daily: dict[str, dict[str, int]] = {}

    def bucket(value: str) -> dict[str, int]:
        return daily.setdefault(
            value[:10], {"research_credits_consumed": 0, "data_credits_consumed": 0, "paid_cny_fen": 0}
        )

    for row in orders:
        bucket(row["paid_at"])["paid_cny_fen"] += int(row["price_cny_fen"])
    for row in research:
        bucket(row["created_at"])["research_credits_consumed"] += int(row["amount"])
    for row in data:
        bucket(row["settled_at"])["data_credits_consumed"] += int(row["amount_settled"] or 0)
    return BillingSummaryResponse(
        period_days=days,
        paid_orders=len(orders),
        paid_cny_fen=sum(int(row["price_cny_fen"]) for row in orders),
        research_credits_consumed=sum(int(row["amount"]) for row in research),
        data_credits_consumed=sum(int(row["amount_settled"] or 0) for row in data),
        daily=[BillingDailyItem(date=date, **values) for date, values in sorted(daily.items())],
    )


@_router.get("/api/notifications", response_model=NotificationsResponse)
async def list_notifications(
    limit: int = Query(100, ge=1, le=500), user: dict = Depends(require_user)
) -> NotificationsResponse:
    _get_subscriptions().process_due(user["id"])
    return NotificationsResponse(items=[
        NotificationItem(**vars(item)) for item in _get_notifications().list(user["id"], limit)
    ])


@_router.get(
    "/api/cloud/query-subscriptions", response_model=SavedQuerySubscriptionsResponse
)
async def list_saved_query_subscriptions(
    user: dict = Depends(require_user),
) -> SavedQuerySubscriptionsResponse:
    return SavedQuerySubscriptionsResponse(items=[
        SavedQuerySubscriptionItem(**vars(item)) for item in _get_subscriptions().list(user["id"])
    ])


@_router.put(
    "/api/cloud/query-subscriptions", response_model=SavedQuerySubscriptionItem
)
async def put_saved_query_subscription(
    body: PutSavedQuerySubscriptionRequest, user: dict = Depends(require_user)
) -> SavedQuerySubscriptionItem:
    try:
        item = _get_subscriptions().create(user["id"], body.saved_query_id, body.frequency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SavedQuerySubscriptionItem(**vars(item))


@_router.delete("/api/cloud/query-subscriptions/{subscription_id}")
async def delete_saved_query_subscription(
    subscription_id: str, user: dict = Depends(require_user)
) -> dict:
    if not _get_subscriptions().delete(user["id"], subscription_id):
        raise HTTPException(status_code=404, detail="subscription not found")
    return {"ok": True}


@_router.post("/api/notifications/{notification_id}/read")
async def read_notification(
    notification_id: str, user: dict = Depends(require_user)
) -> dict:
    if not _get_notifications().mark_read(user["id"], notification_id):
        raise HTTPException(status_code=404, detail="notification not found")
    return {"ok": True}


@_router.get(
    "/api/notification-preferences", response_model=NotificationPreferencesResponse
)
async def get_notification_preferences(
    user: dict = Depends(require_user),
) -> NotificationPreferencesResponse:
    return NotificationPreferencesResponse(**vars(_get_notifications().preferences(user["id"])))


@_router.put(
    "/api/notification-preferences", response_model=NotificationPreferencesResponse
)
async def put_notification_preferences(
    body: PutNotificationPreferencesRequest, user: dict = Depends(require_user)
) -> NotificationPreferencesResponse:
    preferences = _get_notifications().set_preferences(user["id"], **body.model_dump())
    return NotificationPreferencesResponse(**vars(preferences))


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


# --- Device authorization flow (Task 9) ---


def _verification_url(user_code: str) -> str:
    """Where the user approves the device in a browser."""
    import os

    base = os.getenv("SIGMX_VERIFY_URL", "/account/devices/authorize").rstrip("/")
    return f"{base}?user_code={user_code}"


@_router.post("/api/devices/authorize/start", response_model=DeviceAuthorizeStartResponse)
async def device_authorize_start(
    body: DeviceAuthorizeStartRequest,
) -> DeviceAuthorizeStartResponse:
    """Desktop client starts the flow. No auth — it only learns codes here."""
    started = _get_devices().start(
        device_name=body.device_name, fingerprint_hash=body.fingerprint_hash
    )
    from datetime import datetime, timezone

    expires_at = datetime.fromisoformat(started.expires_at)
    expires_in = max(1, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    return DeviceAuthorizeStartResponse(
        device_code=started.device_code,
        user_code=started.user_code,
        verification_url=_verification_url(started.user_code),
        interval_seconds=started.interval_seconds,
        expires_in_seconds=expires_in,
    )


@_router.post("/api/devices/authorize/approve")
async def device_authorize_approve(
    body: DeviceAuthorizeApproveRequest, user: dict = Depends(require_user)
) -> dict:
    """User confirms the device in-browser. Enforces the plan device limit."""
    _get_devices().approve(user_id=user["id"], user_code=body.user_code)
    return {"ok": True}


@_router.post("/api/devices/authorize/poll", response_model=DeviceAuthorizePollResponse)
async def device_authorize_poll(
    body: DeviceAuthorizePollRequest,
) -> DeviceAuthorizePollResponse:
    """Desktop client polls for the outcome. No user JWT — keyed by device_code."""
    result = _get_devices().poll(device_code=body.device_code)
    return DeviceAuthorizePollResponse(
        status=result.status.value,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        device_id=result.device_id,
    )


@_router.post("/api/devices/token/refresh", response_model=DeviceTokenRefreshResponse)
async def device_token_refresh(
    body: DeviceTokenRefreshRequest,
) -> DeviceTokenRefreshResponse:
    """Rotate the desktop's refresh token, mint a new access token."""
    result = _get_devices().refresh(refresh_token=body.refresh_token)
    return DeviceTokenRefreshResponse(
        status=result.status,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
    )


# --- Admin operations (require_admin) --------------------------------


@_router.get("/api/admin/product-metrics", response_model=AdminProductMetricsResponse)
async def admin_product_metrics(
    days: int = Query(30, ge=7, le=365), _: dict = Depends(require_admin)
) -> AdminProductMetricsResponse:
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).date().isoformat()
    weekly = (now - timedelta(days=6)).date().isoformat()
    conn = _get_store()._get_conn()
    grants = conn.execute(
        "SELECT user_id,plan_code,valid_until FROM entitlement_grants "
        "WHERE valid_until IS NULL OR valid_until>=? "
        "ORDER BY user_id, CASE WHEN valid_until IS NULL THEN 0 ELSE 1 END DESC, valid_until DESC",
        (now.isoformat(),),
    ).fetchall()
    current_by_user: dict[str, str] = {}
    for row in grants:
        current_by_user.setdefault(row["user_id"], row["plan_code"])
    distribution: dict[str, int] = {}
    for plan_code in current_by_user.values():
        distribution[plan_code] = distribution.get(plan_code, 0) + 1
    orders = conn.execute(
        "SELECT price_cny_fen FROM orders WHERE status='paid' AND paid_at IS NOT NULL AND paid_at>=?",
        (start,),
    ).fetchall()
    credential_count = conn.execute(
        "SELECT COUNT(*) count FROM datahub_credentials WHERE credential_kind='personal' "
        "AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at>?)",
        (now.isoformat(),),
    ).fetchone()["count"]
    usage = conn.execute(
        "SELECT COUNT(*) requests, SUM(CASE WHEN status_code BETWEEN 200 AND 299 THEN 1 ELSE 0 END) successes, "
        "COALESCE(SUM(credits_charged),0) credits FROM datahub_request_usage WHERE created_at>=?",
        (start,),
    ).fetchone()
    effective_users: set[str] = set()
    for table, condition in (
        ("saved_queries", "created_at>=?"),
        ("cloud_watchlist", "created_at>=?"),
        ("report_snapshots", "created_at>=?"),
        ("credit_ledger", "operation='settle' AND created_at>=?"),
        ("datahub_request_usage", "status_code BETWEEN 200 AND 299 AND created_at>=?"),
    ):
        effective_users.update(
            row["user_id"] for row in conn.execute(
                f"SELECT DISTINCT user_id FROM {table} WHERE {condition}",
                (weekly,),
            ).fetchall()
        )
    requests = int(usage["requests"] or 0)
    successes = int(usage["successes"] or 0)
    return AdminProductMetricsResponse(
        period_days=days,
        active_entitled_users=len(current_by_user),
        plan_distribution=distribution,
        paid_orders=len(orders),
        revenue_cny_fen=sum(int(row["price_cny_fen"]) for row in orders),
        active_datahub_credentials=int(credential_count or 0),
        datahub_requests=requests,
        datahub_success_rate=round(successes / requests, 4) if requests else 0.0,
        data_credits_charged=int(usage["credits"] or 0),
        weekly_effective_research_users=len(effective_users),
        personal_funnel=_get_funnel().aggregate(start),
    )


def _admin_actor(admin: dict) -> str:
    return str(admin.get("email") or admin.get("id") or "admin")


@_router.post("/api/admin/personal-support/credits")
async def admin_compensate_personal_credits(
    body: AdminCompensateCreditsRequest, admin: dict = Depends(require_admin)
) -> dict:
    try:
        operation_id = _get_support_operations().compensate(
            _admin_actor(admin), body.user_id, body.ledger, body.amount, body.reason
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"operation_id": operation_id}


@_router.post("/api/admin/personal-support/devices/revoke")
async def admin_revoke_personal_device(
    body: AdminSecurityRevokeRequest, admin: dict = Depends(require_admin)
) -> dict:
    try:
        _get_support_operations().revoke_device(
            _admin_actor(admin), body.user_id, body.target_id, body.reason
        )
    except SupportTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@_router.post("/api/admin/personal-support/credentials/revoke")
async def admin_revoke_personal_credential(
    body: AdminSecurityRevokeRequest, admin: dict = Depends(require_admin)
) -> dict:
    try:
        _get_support_operations().revoke_credential(
            _admin_actor(admin), body.user_id, body.target_id, body.reason
        )
    except SupportTargetNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


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


@_router.post("/api/admin/data-credit-codes", response_model=CreateActivationCodeResponse)
async def create_data_credit_codes(
    body: CreateDataCreditCodeRequest, _: dict = Depends(require_admin)
) -> CreateActivationCodeResponse:
    try:
        codes = [
            _get_commerce().admin_create_data_credit_code(pack_code=body.pack_code)
            for _ in range(body.count)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CreateActivationCodeResponse(codes=[
        CreatedCodeItem(
            plaintext=code.plaintext,
            code_hash=code.code_hash,
            plan_code=code.plan_code,
            months=0,
        )
        for code in codes
    ])


def register_product_routes(app: FastAPI) -> APIRouter:
    """Attach the product router to ``app``. Idempotent across reloads."""
    already = any(getattr(r, "path", "") == "/api/catalog/plans" for r in app.routes)
    if not already:
        app.include_router(_router)
    logger.info("Product lifecycle routes registered")
    return _router
