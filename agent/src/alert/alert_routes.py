"""FastAPI routes for alert rule management.

Mounted by ``agent/api_server.py`` via ``register_alert_routes(app, ...)``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── Request / Response models ────────────────────────────────────────


class CreateRuleRequest(BaseModel):
    fund_code: str
    fund_name: str = ""
    premium_above: float | None = None
    premium_below: float | None = None
    amount_above: float | None = None
    webhook_type: str = "wechat"
    throttle_minutes: int = 60


class UpdateRuleRequest(BaseModel):
    fund_code: str | None = None
    fund_name: str | None = None
    condition: dict[str, Any] | None = None
    notification: dict[str, Any] | None = None


# ── Route registration ───────────────────────────────────────────────


def register_alert_routes(
    app: FastAPI,
    require_auth: Any,
) -> None:
    """Register alert rule CRUD routes."""
    from fastapi import Depends

    @app.get("/alert/rules")
    async def list_rules(_=Depends(require_auth)):
        """List all alert rules."""
        from src.alert.alert_engine import load_rules
        rules = load_rules()
        return {"rules": rules, "total": len(rules)}

    @app.post("/alert/rules")
    async def create_rule(req: CreateRuleRequest, _=Depends(require_auth)):
        """Create a new alert rule."""
        from src.alert.alert_engine import create_rule
        if not req.fund_code.strip():
            raise HTTPException(400, "基金代码不能为空")
        if req.premium_above is None and req.premium_below is None:
            raise HTTPException(400, "至少设置一个溢价阈值（premium_above 或 premium_below）")
        rule = create_rule(
            fund_code=req.fund_code,
            fund_name=req.fund_name,
            premium_above=req.premium_above,
            premium_below=req.premium_below,
            amount_above=req.amount_above,
            webhook_type=req.webhook_type,
            throttle_minutes=req.throttle_minutes,
        )
        return {"rule": rule, "message": "规则创建成功"}

    @app.put("/alert/rules/{rule_id}")
    async def update_rule(rule_id: str, req: UpdateRuleRequest, _=Depends(require_auth)):
        """Update an existing alert rule."""
        from src.alert.alert_engine import update_rule
        updates = req.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(400, "无更新内容")
        rule = update_rule(rule_id, updates)
        if rule is None:
            raise HTTPException(404, "规则不存在")
        return {"rule": rule, "message": "规则更新成功"}

    @app.delete("/alert/rules/{rule_id}")
    async def delete_rule(rule_id: str, _=Depends(require_auth)):
        """Delete an alert rule."""
        from src.alert.alert_engine import delete_rule
        if not delete_rule(rule_id):
            raise HTTPException(404, "规则不存在")
        return {"message": "规则已删除"}

    @app.post("/alert/rules/{rule_id}/toggle")
    async def toggle_rule(rule_id: str, _=Depends(require_auth)):
        """Toggle enabled status of a rule."""
        from src.alert.alert_engine import toggle_rule
        rule = toggle_rule(rule_id)
        if rule is None:
            raise HTTPException(404, "规则不存在")
        status = "已启用" if rule.get("enabled") else "已禁用"
        return {"rule": rule, "message": f"规则{status}"}

    @app.get("/alert/history")
    async def get_history(_=Depends(require_auth)):
        """Get recent alert notification history."""
        from src.alert.alert_engine import load_history
        history = load_history()
        # Return most recent first
        return {"history": list(reversed(history[-100:])), "total": len(history)}

    # ── Signal endpoints ───────────────────────────────────────────

    @app.get("/signal/active")
    async def get_active_signals(_=Depends(require_auth)):
        """Get all active arbitrage signals (Z-score anomalies)."""
        from src.data.market_store import get_market_store
        store = get_market_store()
        if store is None:
            return {"signals": [], "stats": {}}
        signals = store.get_active_signals()
        stats = store.get_signal_stats()
        return {"signals": signals, "stats": stats}

    @app.get("/signal/history")
    async def get_signal_history(
        days: int = Query(7, ge=1, le=90, description="回溯天数"),
        _=Depends(require_auth),
    ):
        """Get recent signal history."""
        from src.data.market_store import get_market_store
        store = get_market_store()
        if store is None:
            return {"signals": []}
        signals = store.get_signal_history(days)
        return {"signals": signals}

    @app.get("/signal/stats")
    async def get_signal_stats(_=Depends(require_auth)):
        """Aggregate signal statistics."""
        from src.data.market_store import get_market_store
        store = get_market_store()
        if store is None:
            return {"active": 0, "latest_count": 0}
        return store.get_signal_stats()
