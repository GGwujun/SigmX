"""Pydantic models for the auth surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class User(BaseModel):
    """Public user representation (never exposes password_hash)."""
    id: str
    email: str
    disclaimer_accepted_at: str | None = None
    created_at: str
    is_admin: bool = False


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    agree: bool = Field(default=False)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)


class AuthResponse(BaseModel):
    token: str
    user: User
