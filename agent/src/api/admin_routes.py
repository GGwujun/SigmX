"""Admin-only Data Hub subscription management endpoints.

Mounted by api_server.py. All endpoints require admin auth.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateSubscriptionRequest(BaseModel):
    email: str
    tier: str = "free"  # free | basic | pro
    quota_daily: int | None = None
    days: int = 365


class SubscriptionResponse(BaseModel):
    id: str
    email: str
    api_key: str | None = None  # Only returned on creation
    api_key_prefix: str
    tier: str
    quota_daily: int
    created_at: str
    expires_at: str | None
    active: bool


# The require_admin dependency is injected by register_admin_routes.
_require_admin = None


def register_admin_routes(app: FastAPI, require_admin_dep) -> None:
    """Register admin routes with the given require_admin dependency."""
    global _require_admin
    _require_admin = require_admin_dep

    @router.get("/subscriptions")
    async def list_subscriptions(
        _user: dict[str, Any] = Depends(require_admin_dep),
    ) -> list[dict[str, Any]]:
        """List all Data Hub subscriptions."""
        from src.data.subscription_store import get_subscription_store

        store = get_subscription_store()
        subs = store.list_all()
        # Never return api_key_hash — only the prefix.
        return [
            {
                "id": s["id"],
                "email": s["email"],
                "api_key_prefix": s.get("api_key_prefix", ""),
                "tier": s["tier"],
                "quota_daily": s["quota_daily"],
                "created_at": s["created_at"],
                "expires_at": s["expires_at"],
                "active": bool(s["active"]),
            }
            for s in subs
        ]

    @router.post("/subscriptions", status_code=status.HTTP_201_CREATED)
    async def create_subscription(
        body: CreateSubscriptionRequest,
        _user: dict[str, Any] = Depends(require_admin_dep),
    ) -> SubscriptionResponse:
        """Create a new Data Hub subscription and return the API key."""
        if body.tier not in ("free", "basic", "pro"):
            raise HTTPException(status_code=400, detail="Invalid tier. Use free, basic, or pro.")

        from src.data.subscription_store import get_subscription_store

        store = get_subscription_store()
        try:
            sub = store.create(
                email=body.email,
                tier=body.tier,
                quota_daily=body.quota_daily,
                days=body.days,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        return SubscriptionResponse(
            id=sub["id"],
            email=sub["email"],
            api_key=sub["api_key"],
            api_key_prefix=sub["api_key_prefix"],
            tier=sub["tier"],
            quota_daily=sub["quota_daily"],
            created_at=sub["created_at"],
            expires_at=sub["expires_at"],
            active=True,
        )

    @router.delete("/subscriptions/{subscription_id}")
    async def revoke_subscription(
        subscription_id: str,
        _user: dict[str, Any] = Depends(require_admin_dep),
    ) -> dict[str, str]:
        """Revoke (deactivate) a Data Hub subscription."""
        from src.data.subscription_store import get_subscription_store

        store = get_subscription_store()
        ok = store.revoke(subscription_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return {"status": "revoked", "id": subscription_id}

    @router.get("/subscriptions/{subscription_id}/usage")
    async def get_subscription_usage(
        subscription_id: str,
        days: int = 30,
        _user: dict[str, Any] = Depends(require_admin_dep),
    ) -> dict[str, Any]:
        """Get daily usage stats for a subscription."""
        from src.data.subscription_store import get_subscription_store

        store = get_subscription_store()
        usage = store.get_usage(subscription_id, days=days)
        total = sum(row["count"] for row in usage)
        return {
            "subscription_id": subscription_id,
            "days": days,
            "total_requests": total,
            "daily": usage,
        }

    @router.get("/data-hub/stats")
    async def get_data_hub_stats(
        _user: dict[str, Any] = Depends(require_admin_dep),
    ) -> dict[str, Any]:
        """Get overall Data Hub statistics."""
        from src.data.subscription_store import get_subscription_store

        store = get_subscription_store()
        subs = store.list_all()
        active = sum(1 for s in subs if s.get("active"))
        by_tier: dict[str, int] = {}
        for s in subs:
            if s.get("active"):
                tier = s["tier"]
                by_tier[tier] = by_tier.get(tier, 0) + 1

        return {
            "total_subscriptions": len(subs),
            "active_subscriptions": active,
            "by_tier": by_tier,
        }

    app.include_router(router)
    logger.info("Admin routes registered")
