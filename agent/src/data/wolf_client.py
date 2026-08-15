"""黑狼数据 (wolf) HTTP client.

Thin wrapper around http://api.fxyz.site — reads the project-configured
``WOLF_TOKEN`` (managed via the Settings UI → agent/.env), performs GET calls
with a short timeout through the shared market limiter. Unlike tpdog, wolf has
no ``{code, message, content}`` envelope: endpoints return a bare JSON array
(or occasionally a single object), so ``call()`` normalizes to a list the same
way. Docs: docs/wolf-api-official.md (17 interfaces).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "http://api.fxyz.site"
DEFAULT_TIMEOUT = 10  # seconds
_ENV_PATH = Path.home() / ".vibe-trading" / ".env"


class WolfError(RuntimeError):
    """Raised when wolf returns a non-2xx code or the call fails."""

    def __init__(self, code: Optional[int], message: str) -> None:
        self.code = code
        super().__init__(f"[wolf] {code}: {message}" if code else f"[wolf] {message}")


class WolfNotConfiguredError(WolfError):
    """Raised when WOLF_TOKEN is missing or a placeholder."""

    def __init__(self) -> None:
        super().__init__(None, "WOLF_TOKEN 未配置（请在设置页或 agent/.env 填入黑狼数据 Token）")


def get_token() -> str:
    """Return the configured WOLF_TOKEN, or raise if unset/placeholder."""
    token = os.environ.get("WOLF_TOKEN", "").strip()
    if not token and _ENV_PATH.exists():
        try:
            for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip() == "WOLF_TOKEN":
                    token = value.strip().strip('"').strip("'")
                    break
        except OSError as exc:
            logger.debug("failed to read %s: %s", _ENV_PATH, exc)
    if not token or token.lower() == "your-wolf-token":
        raise WolfNotConfiguredError()
    return token


def is_configured() -> bool:
    """True when a non-placeholder WOLF_TOKEN is available."""
    try:
        get_token()
        return True
    except WolfNotConfiguredError:
        return False


def call(path: str, **params: Any) -> List[Dict[str, Any]]:
    """GET ``BASE_URL/{path}`` with token + params; return a list of dicts.

    ``path`` is everything after the host, e.g. ``wolf/zt`` or
    ``wolf/time/kline``. Empty params are dropped. Raises ``WolfError`` on
    non-2xx / non-JSON responses, and ``requests.RequestException`` on network
    failure. Bare-array responses are returned as-is; a single object is
    wrapped in a list; empty/None normalizes to ``[]``.
    """
    token = get_token()
    query: Dict[str, Any] = {k: v for k, v in params.items() if v is not None and v != ""}
    query["token"] = token
    url = f"{BASE_URL}/{path.lstrip('/')}"
    # Gate every outbound call through the shared limiter (same discipline as
    # tpdog) so backfills can't starve foreground requests.
    from src.data.rate_limiter import market_limiter

    with market_limiter:
        resp = requests.get(url, params=query, timeout=DEFAULT_TIMEOUT)
    if resp.status_code != 200:
        raise WolfError(resp.status_code, resp.text[:120])
    try:
        data = resp.json()
    except ValueError as exc:
        raise WolfError(None, f"non-JSON response: {resp.text[:120]}") from exc
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []
