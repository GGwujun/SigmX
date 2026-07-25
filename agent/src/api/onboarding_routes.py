"""Desktop first-run onboarding routes.

Detects whether the ~/.vibe-trading/ data directory needs initialization and
provides an initialize endpoint called by the Electron setup wizard. Loopback-only
— remote callers are rejected.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_DATA_HOME = Path.home() / ".vibe-trading"
_USERS_DB = _DATA_HOME / "users.db"
_MARKET_DB = _DATA_HOME / "market.db"


def _require_loopback(request: Request) -> None:
    """Reject remote callers — onboarding is desktop-only."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="onboarding is only available from loopback",
        )


class OnboardingStatus(BaseModel):
    needs_setup: bool
    data_dir: str
    has_users: bool
    has_market_db: bool
    tushare_configured: bool
    tpdog_configured: bool
    llm_configured: bool


@router.get("/status", response_model=OnboardingStatus)
def get_status(request: Request) -> OnboardingStatus:
    """Check whether first-run setup is needed."""
    _require_loopback(request)

    has_users = _USERS_DB.exists() and _USERS_DB.stat().st_size > 0
    has_market_db = _MARKET_DB.exists()

    # Check env for tokens — read from agent/.env if present, or process env.
    env_path = _find_env_path()
    env_vals = _read_dotenv(env_path) if env_path else {}

    tushare_ok = bool(
        _is_configured(env_vals.get("TUSHARE_TOKEN", ""))
        or _is_configured(os.getenv("TUSHARE_TOKEN", ""))
    )
    tpdog_ok = bool(
        _is_configured(env_vals.get("TPDOG_TOKEN", ""))
        or _is_configured(os.getenv("TPDOG_TOKEN", ""))
    )
    llm_ok = bool(
        _is_configured(env_vals.get("OPENROUTER_API_KEY", ""))
        or _is_configured(env_vals.get("OPENAI_API_KEY", ""))
        or _is_configured(env_vals.get("DEEPSEEK_API_KEY", ""))
        or _is_configured(os.getenv("OPENROUTER_API_KEY", ""))
        or _is_configured(os.getenv("OPENAI_API_KEY", ""))
    )

    needs_setup = not has_users

    return OnboardingStatus(
        needs_setup=needs_setup,
        data_dir=str(_DATA_HOME),
        has_users=has_users,
        has_market_db=has_market_db,
        tushare_configured=tushare_ok,
        tpdog_configured=tpdog_ok,
        llm_configured=llm_ok,
    )


class InitializeRequest(BaseModel):
    email: str = "admin@local"
    password: str = "admin123"
    tushare_token: str = ""
    tpdog_token: str = ""


class InitializeResponse(BaseModel):
    ok: bool
    email: str
    message: str


@router.post("/initialize", response_model=InitializeResponse)
def initialize(request: Request, body: InitializeRequest) -> InitializeResponse:
    """Create the admin account and optionally write data-source tokens.

    Idempotent — if users.db already exists, it won't overwrite.
    Only accessible from loopback.
    """
    _require_loopback(request)

    # 1) Create admin user.
    from src.auth.store import UserStore

    store = UserStore()
    admin = store.find_admin() or store.get_first_user()

    if admin is None:
        try:
            admin = store.create_user(body.email.strip().lower(), body.password)
            store.set_admin(admin["id"])
            logger.info("Onboarding: created admin %s", body.email)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    else:
        logger.info("Onboarding: admin already exists (%s), skipping user creation", admin.get("email"))

    # 2) Write data-source tokens to agent/.env if provided.
    if body.tushare_token.strip() or body.tpdog_token.strip():
        _write_tokens_to_env(body.tushare_token.strip(), body.tpdog_token.strip())

    return InitializeResponse(
        ok=True,
        email=body.email,
        message="Setup complete. The app is ready.",
    )


# ================================================================ helpers

_PLACEHOLDERS = {"", "your-tushare-token", "your-tpdog-token", "sk-or-v1-your-key-here", "sk-xxx", "xxx"}


def _is_configured(value: str) -> bool:
    """Return True when a token is set and not a documented placeholder."""
    return value.strip().lower() not in _PLACEHOLDERS and len(value.strip()) > 4


def _find_env_path() -> Path | None:
    """Locate agent/.env relative to this file's package root."""
    # api/onboarding_routes.py → src/api/ → src/ → agent/src/ → agent/
    here = Path(__file__).resolve().parent  # api/
    for _ in range(3):  # api → src → agent
        here = here.parent
    env = here / ".env"
    return env if env.exists() else None


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read KEY=value pairs from a dotenv file."""
    vals: dict[str, str] = {}
    if not path.exists():
        return vals
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().strip('"').strip("'")
        value = value.strip().strip('"').strip("'")
        if key:
            vals[key] = value
    return vals


def _write_tokens_to_env(tushare: str, tpdog: str) -> None:
    """Write TUSHARE_TOKEN / TPDOG_TOKEN to agent/.env."""
    env_path = _find_env_path()
    if env_path is None:
        # No .env yet — create a minimal one.
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated: dict[str, str] = {}
    if tushare:
        updated["TUSHARE_TOKEN"] = tushare
    if tpdog:
        updated["TPDOG_TOKEN"] = tpdog

    seen: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in updated and key not in seen:
            lines[i] = f"{key}={updated[key]}"
            seen.add(key)

    for key in updated:
        if key not in seen:
            lines.append(f"{key}={updated[key]}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Also set in the running process so the worker picks it up immediately.
    for key, val in updated.items():
        os.environ[key] = val
    logger.info("Onboarding: wrote %s to %s", ", ".join(updated.keys()), env_path)


def register_onboarding_routes(app: FastAPI) -> None:
    app.include_router(router)
    logger.info("Onboarding routes registered")
