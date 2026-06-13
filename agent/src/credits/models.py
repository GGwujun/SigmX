"""Pydantic models for the credits surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BalanceResponse(BaseModel):
    balance: int


class Transaction(BaseModel):
    id: str
    delta: int
    type: str
    ref: str
    balance_after: int
    note: str
    created_at: str


class TransactionsResponse(BaseModel):
    items: list[Transaction]
    count: int


class RedeemRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)


class RedeemResponse(BaseModel):
    ok: bool
    credits: int = 0          # credits gained (0 if failed)
    balance: int              # balance after
    message: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6, max_length=128)


class AccountInfo(BaseModel):
    id: str
    email: str
    created_at: str
    disclaimer_accepted_at: str | None = None
    balance: int
