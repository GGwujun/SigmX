"""Product access tokens — Task 4.

Short-lived JWTs with a distinct audience (``sigmx-product``) so they are
unmistakable from web-session JWTs (design §3.1, plan Task 4 Step 4). Carries a
device id, the current plan, an entitlement snapshot, and a unique ``jti``.
Web JWTs (audience-less) deliberately fail verification here.

Reuses the process JWT secret from :mod:`src.auth.jwt_utils` so the whole
deployment validates against one key, but verification pins the audience.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from src.auth.jwt_utils import _ALGORITHM, _SECRET

PRODUCT_AUDIENCE = "sigmx-product"
_ACCESS_TTL_MINUTES = 15


def create_product_token(
    *,
    user_id: str,
    device_id: str,
    plan_code: str,
    entitlements: dict[str, Any] | None = None,
    ttl_minutes: int = _ACCESS_TTL_MINUTES,
) -> str:
    """Issue a short-lived product access token bound to a device + plan."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "aud": PRODUCT_AUDIENCE,
        "device_id": device_id,
        "plan": plan_code,
        "entitlements": entitlements or {},
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_product_token(token: str) -> dict[str, Any] | None:
    """Verify a product token, pinning the audience. ``None`` if invalid/wrong-audience."""
    if not token:
        return None
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM], audience=PRODUCT_AUDIENCE)
    except jwt.PyJWTError:
        return None
