"""JWT issue/verify for user sessions.

The secret is read from ``JWT_SECRET``. If unset, a random secret is generated
per process start (tokens invalidate on restart — acceptable in dev; production
must set ``JWT_SECRET``). A warning is logged when the random fallback is used.
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_TOKEN_TTL_HOURS = 24


def _load_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    # Dev fallback: random per process. Tokens won't survive a restart.
    random_secret = secrets.token_urlsafe(48)
    logger.warning(
        "JWT_SECRET not set — generated a random one for this process. "
        "Set JWT_SECRET in the environment for persistent logins."
    )
    return random_secret


_SECRET = _load_secret()


def create_token(user_id: str, email: str) -> str:
    """Issue a JWT for the given user, valid for ``_TOKEN_TTL_HOURS`` hours."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=_TOKEN_TTL_HOURS)).timestamp()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a JWT and return its payload, or None if invalid/expired."""
    if not token:
        return None
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None


def user_id_from_token(token: str) -> str | None:
    """Convenience: extract the user id (``sub``) from a valid token."""
    payload = verify_token(token)
    if payload is None:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None
