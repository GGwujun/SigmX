import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

import src.api.auth_routes as auth_routes
import src.api.product_routes as product_routes
from src.product.store import ProductStore
from src.product.tokens import create_product_token


class AuthUsers:
    def get_by_id(self, user_id):
        return {"id": user_id, "email": "person@example.com", "is_admin": False}


def request():
    return Request({"type": "http", "method": "GET", "path": "/api/cloud/handoffs/x/consume", "headers": [], "client": ("203.0.113.1", 1234)})


def test_require_user_accepts_only_active_device_product_token(tmp_path, monkeypatch):
    store = ProductStore(tmp_path / "product.db")
    store._get_conn().execute(
        "INSERT INTO devices (id,user_id,name,fingerprint_hash,created_at,revoked_at) VALUES (?,?,?,?,?,NULL)",
        ("d1", "u1", "Laptop", "fp", datetime.now(timezone.utc).isoformat()),
    )
    store._get_conn().commit()
    product_routes._store = store
    monkeypatch.setattr(auth_routes, "_store", AuthUsers())
    token = create_product_token(user_id="u1", device_id="d1", plan_code="free")
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    assert asyncio.run(auth_routes.require_user(request(), cred))["id"] == "u1"
    store._get_conn().execute("UPDATE devices SET revoked_at=? WHERE id='d1'", (datetime.now(timezone.utc).isoformat(),))
    store._get_conn().commit()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_routes.require_user(request(), cred))
    assert exc.value.status_code == 401
