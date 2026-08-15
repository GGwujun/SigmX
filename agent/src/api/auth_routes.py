"""Authentication HTTP routes: register / login / disclaimer / me.

These endpoints are PUBLIC (no require_auth) except /auth/disclaimer/accept
and /auth/me, which validate the JWT via ``require_user``.

Mounted by ``agent/api_server.py`` via ``register_auth_routes(app)``.
"""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.jwt_utils import create_token, user_id_from_token
from src.auth.models import AuthResponse, LoginRequest, RegisterRequest, User
from src.auth.store import UserStore

logger = logging.getLogger(__name__)

# Module-level singleton store (SQLite connection is thread-safe with the
# store's internal lock).
_store: UserStore | None = None


def _get_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
    return _store


_security = HTTPBearer(auto_error=False)

_DESKTOP_MODE_ENV = "VIBE_TRADING_DESKTOP_MODE"


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_loopback_request(request: Request) -> bool:
    """Whether the request originates from loopback (127.0.0.1 / ::1)."""
    host = request.client.host if request.client else ""
    if host in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _desktop_loopback_user(request: Request) -> dict[str, Any] | None:
    """Return the local admin user for a desktop-mode loopback request, else None.

    The desktop client (Electron shell) talks to a locally-spawned backend over
    loopback. Mirroring ``require_auth`` in api_server.py, we skip JWT for these
    requests so the UI keeps working after an app update clears the localStorage
    JWT — otherwise every ``Depends(require_user)``/``require_admin`` endpoint
    (/settings/llm, credits, /auth/me, …) returns 401 and the Settings page
    shows empty config even though ``~/.vibe-trading/.env`` is intact.

    Only loopback + DESKTOP_MODE is exempt; server / remote requests still
    require a JWT. Returns the first admin user (the desktop is single-user).
    """
    if not (_env_flag_enabled(_DESKTOP_MODE_ENV) and _is_loopback_request(request)):
        return None
    try:
        admin = _get_store().first_admin()
    except Exception:  # noqa: BLE001
        return None
    return admin


async def require_user(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict[str, Any]:
    """Validate the JWT bearer token and return the user dict.

    Used by user-gated endpoints (/auth/me, /auth/disclaimer/accept).
    """
    # Desktop client loopback: skip JWT (see _desktop_loopback_user).
    desktop_user = _desktop_loopback_user(request)
    if desktop_user is not None:
        return desktop_user
    token = cred.credentials if cred and cred.credentials else ""
    user_id = user_id_from_token(token)
    if not user_id:
        # Connected Desktop uses a distinct audience and remains valid only
        # while its server-side device registration is active.
        from src.product.tokens import verify_product_token
        product_claims = verify_product_token(token)
        if product_claims:
            candidate_user = str(product_claims.get("sub") or "")
            device_id = str(product_claims.get("device_id") or "")
            if candidate_user and device_id:
                from src.api import product_routes
                active = product_routes._get_store()._get_conn().execute(
                    "SELECT 1 FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL",
                    (device_id, candidate_user),
                ).fetchone()
                if active is not None:
                    user_id = candidate_user
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    user = _get_store().get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


async def require_admin(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_security),
) -> dict[str, Any]:
    """Validate JWT AND require the user to be an admin. Returns the user dict.

    Used by operator-only endpoints (system settings, etc.).
    """
    user = await require_user(request, cred)
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def register_auth_routes(app: FastAPI) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", response_model=AuthResponse)
    async def register(body: RegisterRequest) -> AuthResponse:
        """Register a new user. ``agree`` must be true (disclaimer checkbox)."""
        if not body.agree:
            raise HTTPException(status_code=400, detail="必须同意免责声明才能注册")
        try:
            user = _get_store().create_user(body.email, body.password)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        token = create_token(user["id"], user["email"])
        return AuthResponse(token=token, user=User(**user))

    @router.post("/login", response_model=AuthResponse)
    async def login(body: LoginRequest) -> AuthResponse:
        """Login with email + password. Returns a JWT + the user."""
        user = _get_store().verify_credentials(body.email, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        token = create_token(user["id"], user["email"])
        return AuthResponse(token=token, user=User(**user))

    @router.post("/desktop-session", response_model=AuthResponse)
    async def desktop_session(request: Request) -> AuthResponse:
        """Create or return a desktop session JWT (loopback-only).

        Desktop-mode loopback requests already skip auth in the main guard,
        but the frontend's RequireAuth component needs a token in localStorage
        to avoid redirecting to /login. This endpoint bridges that gap: it
        finds (or creates) the default admin user and returns a valid JWT so
        the desktop app "just works" without a manual login.

        Only accessible from loopback — remote callers get 403.
        """
        # Reuse the same local-client check as the desktop auth guard.
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="desktop-session is only available from loopback",
            )

        store = _get_store()
        # Find an existing admin, or fall back to the first user, or seed one.
        admin = store.find_admin()
        if admin is None:
            # Try any user (e.g. after onboarding completed but admin flag missing)
            first = store.get_first_user()
            if first:
                admin = first
            else:
                # Seed a default admin account so the desktop app always works.
                import os as _os
                email = _os.getenv("ADMIN_EMAIL", "admin@local")
                password = _os.getenv("ADMIN_PASSWORD", "admin123")
                try:
                    admin = store.create_user(email, password)
                    store.set_admin(admin["id"])
                    admin = store.get_by_id(admin["id"])
                except ValueError:
                    # Race: another call already created it. Retry.
                    admin = store.find_admin() or store.get_first_user()
                    if admin is None:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to seed desktop admin account",
                        )

        token = create_token(admin["id"], admin["email"])
        return AuthResponse(token=token, user=User(**admin))

    @router.get("/me", response_model=User)
    async def me(user: dict = Depends(require_user)) -> User:
        """Return the current user (validates the token)."""
        return User(**user)

    @router.post("/disclaimer/accept", response_model=User)
    async def accept_disclaimer(user: dict = Depends(require_user)) -> User:
        """Record that the user accepted the disclaimer."""
        _get_store().set_disclaimer_accepted(user["id"])
        updated = _get_store().get_by_id(user["id"]) or user
        return User(**updated)

    app.include_router(router)
    logger.info("Auth routes registered")
    return router
