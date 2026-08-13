"""Data Hub product-token authentication — Task 6.

Normalizes the two Data Hub credential families (design §6, §3.1):

1. **Product access tokens** — short-lived JWTs with audience ``sigmx-product``,
   issued by the device flow. Quota comes from the plan's ``datahub.daily_quota``
   entitlement, enforced atomically against ``product.db.usage_daily``.
2. **Legacy ``sx_`` API keys** — kept verbatim by :mod:`src.data.subscription_store`
   and handled in ``sigmx_routes._data_hub_auth``.

``resolve_product_principal`` returns a :class:`DataHubPrincipal` for a valid
product token, or ``None`` when there is no product token (so the legacy API-key
path keeps ownership of that case). This module never touches the legacy store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from src.product.tokens import verify_product_token

logger = logging.getLogger(__name__)

_USAGE_METRIC = "datahub.request"


def _now_default() -> datetime:
    return datetime.now(timezone.utc)


def _today_str(now: datetime) -> str:
    """UTC date key for usage_daily (resets at midnight UTC)."""
    return now.date().isoformat()


@dataclass(frozen=True)
class DataHubPrincipal:
    """Normalized identity for a Data Hub request, regardless of credential source.

    ``source`` is ``"product_token"`` for the new path or ``"legacy_api_key"`` for
    the existing ``sx_`` key path (filled in by ``sigmx_routes``).
    """

    subject: str
    source: str
    plan: str
    quota_daily: int
    featured: bool
    entitlements: dict[str, Any]
    device_id: Optional[str] = None


def resolve_product_principal(
    request: Any,
    store: Any,
    *,
    now: Optional[datetime] = None,
) -> Optional[DataHubPrincipal]:
    """Return the product-token principal on the request, or ``None``.

    ``None`` means "not a product-token request" — the caller should fall through
    to the legacy ``sx_`` API-key path. A present-but-invalid token also returns
    ``None`` (the legacy path will then reject it as an unknown key).
    """
    auth = _extract_bearer(request)
    if not auth:
        return None
    claims = verify_product_token(auth)
    if claims is None:
        return None  # wrong audience / tampered / expired → not a product token

    user_id = str(claims["sub"])
    device_id = claims.get("device_id")
    now_dt = now or _now_default()

    conn = store._get_conn()
    # 1. Device still linked (not revoked).
    if device_id:
        dev = conn.execute(
            "SELECT revoked_at FROM devices WHERE id = ? AND user_id = ?",
            (device_id, user_id),
        ).fetchone()
        if dev is None or dev["revoked_at"] is not None:
            return None

    # 2. Plan window still valid → resolve entitlements.
    grant = conn.execute(
        """
        SELECT plan_code FROM entitlement_grants
        WHERE user_id = ? AND (valid_until IS NULL OR valid_until >= ?)
        ORDER BY valid_until DESC LIMIT 1
        """,
        (user_id, now_dt.isoformat()),
    ).fetchone()
    if grant is None:
        return None  # entitlement expired

    import json

    plan_row = conn.execute(
        "SELECT entitlements_json FROM plans WHERE code = ?", (grant["plan_code"],)
    ).fetchone()
    entitlements = json.loads(plan_row["entitlements_json"]) if plan_row else {}
    quota = int(entitlements.get("datahub.daily_quota", 100))
    featured = bool(entitlements.get("datahub.featured", False))

    return DataHubPrincipal(
        subject=user_id,
        source="product_token",
        plan=grant["plan_code"],
        quota_daily=quota,
        featured=featured,
        entitlements=entitlements,
        device_id=device_id,
    )


def acquire_product_quota(
    store: Any,
    principal: DataHubPrincipal,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Atomically reserve one Data Hub request against today's plan quota.

    Mirrors :meth:`SubscriptionStore.acquire_quota`: a single INSERT ... ON
    CONFLICT that only increments when ``count < quota``. Returns True if a slot
    was reserved, False if the quota is exhausted (caller raises 429).
    """
    today = _today_str(now or _now_default())
    conn = store._get_conn()
    cur = conn.execute(
        """
        INSERT INTO usage_daily (user_id, metric, day, consumed)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(user_id, metric, day)
        DO UPDATE SET consumed = consumed + 1
        WHERE consumed < ?
        """,
        (principal.subject, _USAGE_METRIC, today, principal.quota_daily),
    )
    conn.commit()
    return cur.rowcount > 0


def require_datahub_entitlement(key: str):
    """Build a FastAPI dependency that requires ``key`` in the principal's plan.

    For future featured-data endpoints (design §6): basic ``/api/v1/*`` routes
    only need ``datahub.basic``; featured endpoints additionally require
    ``datahub.featured``. Kept as a factory so the key is explicit at the call site.
    """
    from fastapi import HTTPException, status

    def _check(principal: DataHubPrincipal) -> DataHubPrincipal:
        if key == "datahub.featured" and not principal.featured:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="此数据需要特色数据权益（专业版或更高）",
            )
        if not principal.entitlements.get("datahub.basic", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="当前套餐不含 Data Hub 基础访问权益",
            )
        return principal

    return _check


def _extract_bearer(request: Any) -> Optional[str]:
    """Pull a Bearer token off the request's Authorization header, if any."""
    headers = getattr(request, "headers", {}) or {}
    # starlette headers are case-insensitive; plain dicts may not be.
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None
