"""Unified personal Data Hub authentication, entitlement and credit billing."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger, InsufficientDataCredits
from src.product.datahub_catalog import DataHubEndpointCatalog, EndpointPricing
from src.product.datahub_budgets import DataHubBudgetService, DailyBudgetExceeded
from src.product.datahub_contracts import RequestContract, ResponseContract
from src.product.datahub_contracts import HistoryDepthExceeded, RequestRowsExceeded
from src.product.datahub_credentials import (
    CredentialExpired,
    CredentialIpNotAllowed,
    CredentialNotFound,
    CredentialRevoked,
    DataHubCredentialService,
)
from src.product.datahub_limits import (
    ConcurrentLimitExceeded,
    DataHubLimitService,
    RateLimitExceeded,
)
from src.product.store import ProductStore

logger = logging.getLogger(__name__)


class CredentialRequired(Exception):
    pass


class CredentialInvalid(Exception):
    pass


class DatasetNotEntitled(Exception):
    pass


class ScopeDenied(Exception):
    pass


class DataHubDisabled(Exception):
    pass


@dataclass(frozen=True)
class PreparedDataHubRequest:
    request_id: str
    user_id: str
    credential_id: str
    endpoint: EndpointPricing
    requested_units: int
    credits_authorized: int
    reservation_id: str | None
    lease_id: str
    rate_limit: int
    rate_remaining: int
    started_at: float


class DataHubRequestGateway:
    def __init__(self, store: ProductStore) -> None:
        self.store = store
        self.credentials = DataHubCredentialService(store)
        self.catalog = DataHubEndpointCatalog(store)
        self.limits = DataHubLimitService(store)
        self.data_credits = DataCreditLedger(store)
        self.commerce = CommerceService(store, CreditLedger(store))
        self.budgets = DataHubBudgetService(store)

    def prepare(self, request: Any, method: str, path: str) -> PreparedDataHubRequest:
        endpoint = self.catalog.match(method, path)
        plaintext = self._bearer(request)
        remote_ip = request.client.host if getattr(request, "client", None) else ""
        try:
            principal = self.credentials.authenticate(plaintext, remote_ip)
        except CredentialIpNotAllowed:
            raise
        except (CredentialNotFound, CredentialRevoked, CredentialExpired) as exc:
            raise CredentialInvalid(str(exc)) from exc

        snapshot = self.commerce.current_entitlements(principal.user_id)
        entitlements = snapshot.entitlements
        if not entitlements.get("datahub.enabled", False):
            raise DataHubDisabled("Data Hub is disabled for this plan")
        groups = tuple(entitlements.get("datahub.dataset_groups", []))
        if endpoint.dataset_group not in groups:
            raise DatasetNotEntitled(endpoint.dataset_group)
        if (
            endpoint.endpoint_code not in principal.scopes
            and f"group:{endpoint.dataset_group}" not in principal.scopes
        ):
            raise ScopeDenied(endpoint.endpoint_code)

        usage = RequestContract.evaluate(endpoint, request.query_params, entitlements)
        request_id = self._request_id(request)
        rate_limit = int(entitlements.get("datahub.rate_limit_per_minute", 0))
        concurrent_limit = int(entitlements.get("datahub.concurrent_limit", 0))
        lease = self.limits.acquire(
            principal.user_id,
            principal.credential_id,
            request_id,
            rate_limit,
            concurrent_limit,
        )
        try:
            self.commerce.ensure_monthly_data_grant(
                principal.user_id, snapshot.plan_code, datetime.now(timezone.utc).date()
            )
            authorized = self.catalog.estimate(endpoint, usage.requested_units)
            self.budgets.reserve(
                principal.user_id, principal.credential_id, request_id, authorized
            )
            reservation_id = None
            if authorized > 0:
                authorization = self.data_credits.authorize(
                    principal.user_id,
                    endpoint.endpoint_code,
                    authorized,
                    f"datahub:{principal.credential_id}:{request_id}",
                )
                reservation_id = authorization.reservation_id
        except Exception:
            self.budgets.release(request_id)
            self.limits.release(lease.lease_id)
            raise
        return PreparedDataHubRequest(
            request_id=request_id,
            user_id=principal.user_id,
            credential_id=principal.credential_id,
            endpoint=endpoint,
            requested_units=usage.requested_units,
            credits_authorized=authorized,
            reservation_id=reservation_id,
            lease_id=lease.lease_id,
            rate_limit=rate_limit,
            rate_remaining=lease.rate_remaining,
            started_at=time.monotonic(),
        )

    def complete(self, prepared: PreparedDataHubRequest, response: Any):
        charged = 0
        actual_units = 0
        error_code = None
        try:
            if 200 <= response.status_code < 300:
                if prepared.endpoint.pricing_mode == "per_unit":
                    try:
                        payload = json.loads(bytes(response.body))
                    except (TypeError, ValueError, json.JSONDecodeError) as exc:
                        raise ValueError("billing response is not valid JSON") from exc
                    actual_units = ResponseContract.count(prepared.endpoint, payload)
                charged = self.catalog.calculate(prepared.endpoint, actual_units)
                if prepared.reservation_id is not None:
                    self.data_credits.settle(
                        prepared.reservation_id,
                        charged,
                        f"datahub-settle:{prepared.request_id}",
                    )
            else:
                error_code = f"http_{response.status_code}"
                self._release_reservation(prepared, error_code)
            self._safe_write_usage(prepared, response.status_code, actual_units, charged, error_code)
            self._headers(response, prepared, charged)
            return response
        except Exception:
            self._release_reservation(prepared, "billing_contract_error")
            self._safe_write_usage(prepared, 500, 0, 0, "billing_contract_error")
            raise
        finally:
            self.limits.release(prepared.lease_id)

    def fail(
        self, prepared: PreparedDataHubRequest, error_code: str, *, status_code: int = 500
    ) -> None:
        try:
            self._release_reservation(prepared, error_code)
            self._safe_write_usage(prepared, status_code, 0, 0, error_code)
        finally:
            self.limits.release(prepared.lease_id)

    @staticmethod
    def _bearer(request: Any) -> str:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth:
            raise CredentialRequired("Authorization Bearer credential is required")
        parts = auth.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].startswith("sxd_live_"):
            raise CredentialRequired("Authorization Bearer sxd_live_ credential is required")
        return parts[1]

    @staticmethod
    def _request_id(request: Any) -> str:
        supplied = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
        if supplied:
            try:
                return str(uuid.UUID(supplied))
            except ValueError as exc:
                raise ValueError("X-Request-ID must be a UUID") from exc
        return str(uuid.uuid4())

    def _release_reservation(self, prepared: PreparedDataHubRequest, error_code: str) -> None:
        if prepared.reservation_id is not None:
            self.data_credits.release(
                prepared.reservation_id, f"datahub-release:{prepared.request_id}:{error_code}"
            )

    def _write_usage(
        self,
        prepared: PreparedDataHubRequest,
        status_code: int,
        actual_units: int,
        charged: int,
        error_code: str | None,
    ) -> None:
        duration_ms = max(0, int((time.monotonic() - prepared.started_at) * 1000))
        with self.store.transaction() as conn:
            self.budgets.release(prepared.request_id, conn)
            conn.execute(
                "INSERT OR IGNORE INTO datahub_request_usage "
                "(request_id, user_id, credential_id, endpoint_code, status_code, "
                "requested_units, actual_units, credits_authorized, credits_charged, "
                "duration_ms, error_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    prepared.request_id,
                    prepared.user_id,
                    prepared.credential_id,
                    prepared.endpoint.endpoint_code,
                    status_code,
                    prepared.requested_units,
                    actual_units,
                    prepared.credits_authorized,
                    charged,
                    duration_ms,
                    error_code,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            if charged > 0:
                self.budgets.record_events(conn, prepared.user_id, prepared.credential_id)

    def _safe_write_usage(self, *args) -> None:
        try:
            self._write_usage(*args)
        except Exception:
            logger.exception("Data Hub usage audit write failed")

    def _headers(self, response: Any, prepared: PreparedDataHubRequest, charged: int) -> None:
        response.headers["X-Request-ID"] = prepared.request_id
        response.headers["X-DataHub-Endpoint"] = prepared.endpoint.endpoint_code
        response.headers["X-DataHub-Credits-Authorized"] = str(prepared.credits_authorized)
        response.headers["X-DataHub-Credits-Charged"] = str(charged)
        response.headers["X-DataHub-Credits-Remaining"] = str(
            self.data_credits.balance(prepared.user_id).available
        )
        response.headers["X-DataHub-RateLimit-Limit"] = str(prepared.rate_limit)
        response.headers["X-DataHub-RateLimit-Remaining"] = str(prepared.rate_remaining)


class DataHubBillingRoute(APIRoute):
    """Wrap every SigmX data route in the personal Data Hub gateway."""

    def get_route_handler(self):
        original = super().get_route_handler()
        method = next(iter(self.methods or {"GET"}))
        path = self.path

        async def billed(request):
            from src.api import sigmx_routes

            if not sigmx_routes._is_data_hub_enabled():
                return await original(request)
            gateway = sigmx_routes._get_gateway()
            try:
                prepared = gateway.prepare(request, method, path)
            except Exception as exc:
                return self._error_response(exc)
            try:
                response = await original(request)
            except Exception:
                gateway.fail(prepared, "handler_error", status_code=500)
                raise
            try:
                return gateway.complete(prepared, response)
            except Exception:
                return JSONResponse(
                    status_code=500,
                    content={"ok": False, "error": {"code": "billing_contract_error", "message": "Data Hub billing contract failed"}},
                    headers={"X-Request-ID": prepared.request_id},
                )

        return billed

    @staticmethod
    def _error_response(exc: Exception):
        request_id = str(uuid.uuid4())
        if isinstance(exc, CredentialRequired):
            status_code, code = 401, "credential_required"
        elif isinstance(exc, (CredentialInvalid, CredentialExpired, CredentialRevoked)):
            status_code, code = 401, "credential_invalid"
        elif isinstance(exc, CredentialIpNotAllowed):
            status_code, code = 403, "ip_not_allowed"
        elif isinstance(exc, DatasetNotEntitled):
            status_code, code = 403, "dataset_not_entitled"
        elif isinstance(exc, ScopeDenied):
            status_code, code = 403, "scope_denied"
        elif isinstance(exc, InsufficientDataCredits):
            status_code, code = 402, "insufficient_data_credits"
        elif isinstance(exc, DailyBudgetExceeded):
            status_code, code = 429, "daily_budget_exceeded"
        elif isinstance(exc, RequestRowsExceeded):
            status_code, code = 422, "request_rows_exceeded"
        elif isinstance(exc, HistoryDepthExceeded):
            status_code, code = 422, "history_depth_exceeded"
        elif isinstance(exc, RateLimitExceeded):
            status_code, code = 429, "rate_limit_exceeded"
        elif isinstance(exc, ConcurrentLimitExceeded):
            status_code, code = 429, "concurrent_limit_exceeded"
        else:
            status_code, code = 500, "endpoint_uncataloged"
        return JSONResponse(
            status_code=status_code,
            content={"ok": False, "error": {"code": code, "message": str(exc)}},
            headers={"X-Request-ID": request_id},
        )
