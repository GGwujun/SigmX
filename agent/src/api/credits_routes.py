"""Credits + account HTTP routes.

All endpoints require a logged-in user (Depends(require_user) from auth_routes).

Routes:
- GET  /credits/balance
- GET  /credits/transactions?limit=
- POST /credits/redeem
- GET  /account/me
- POST /account/password   (change password)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.auth_routes import require_user  # reuse the JWT validator
from src.auth.password import hash_password, verify_password
from src.auth.store import UserStore
from src.credits.models import (
    AccountInfo, BalanceResponse, ChangePasswordRequest, RedeemRequest,
    RedeemResponse, Transaction, TransactionsResponse,
)
from src.credits.store import CreditStore

logger = logging.getLogger(__name__)

_credits_store: CreditStore | None = None
_user_store: UserStore | None = None
_security = HTTPBearer(auto_error=False)


def _get_credits() -> CreditStore:
    global _credits_store
    if _credits_store is None:
        _credits_store = CreditStore()
    return _credits_store


def _get_users() -> UserStore:
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


def register_credits_routes(app: FastAPI) -> APIRouter:
    router = APIRouter(tags=["credits"])

    @router.get("/credits/balance", response_model=BalanceResponse)
    async def balance(user: dict = Depends(require_user)) -> BalanceResponse:
        return BalanceResponse(balance=_get_credits().get_balance(user["id"]))

    @router.get("/credits/transactions", response_model=TransactionsResponse)
    async def transactions(
        user: dict = Depends(require_user),
        limit: int = Query(50, ge=1, le=500),
    ) -> TransactionsResponse:
        rows = _get_credits().list_transactions(user["id"], limit)
        items = [Transaction(**r) for r in rows]
        return TransactionsResponse(items=items, count=len(items))

    @router.post("/credits/redeem", response_model=RedeemResponse)
    async def redeem(body: RedeemRequest, user: dict = Depends(require_user)) -> RedeemResponse:
        ok, credits, msg = _get_credits().redeem(user["id"], body.code)
        bal = _get_credits().get_balance(user["id"])
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return RedeemResponse(ok=True, credits=credits, balance=bal, message=msg)

    @router.get("/account/me", response_model=AccountInfo)
    async def account_me(user: dict = Depends(require_user)) -> AccountInfo:
        return AccountInfo(
            id=user["id"],
            email=user["email"],
            created_at=user["created_at"],
            disclaimer_accepted_at=user.get("disclaimer_accepted_at"),
            balance=_get_credits().get_balance(user["id"]),
        )

    @router.post("/account/password")
    async def change_password(
        body: ChangePasswordRequest,
        user: dict = Depends(require_user),
    ) -> dict:
        # Re-verify old password before accepting the change.
        full = _get_users().verify_credentials(user["email"], body.old_password)
        if full is None:
            raise HTTPException(status_code=400, detail="原密码错误")
        # Update password hash directly (UserStore has no setter; use raw SQL path).
        _get_users()._set_password_hash(user["id"], hash_password(body.new_password))
        return {"status": "ok", "message": "密码已更新"}

    app.include_router(router)
    logger.info("Credits + account routes registered")
    return router
