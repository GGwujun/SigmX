"""Redis client helper — best-effort, gracefully degrades when unavailable.

Reads REDIS_URL from environment. If not set or connection fails, all
operations are no-ops (publish returns False, get_redis returns None).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_client = None
_tried = False


def get_redis():
    """Return a Redis client instance, or None if unavailable.

    Cached after first call. Safe to call repeatedly.
    """
    global _client, _tried
    if _tried:
        return _client
    _tried = True

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        logger.debug("redis_client: REDIS_URL not set, Redis disabled")
        return None

    try:
        import redis
        _client = redis.from_url(url, decode_responses=True, socket_timeout=5)
        _client.ping()
        logger.info("redis_client: connected to %s", url)
        return _client
    except Exception as exc:
        logger.warning("redis_client: connection failed: %s", exc)
        _client = None
        return None


def publish(channel: str, data: Any) -> bool:
    """Publish JSON data to a Redis channel. Returns False if unavailable."""
    r = get_redis()
    if r is None:
        return False
    try:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        r.publish(channel, payload)
        return True
    except Exception as exc:
        logger.debug("redis_client: publish failed on %s: %s", channel, exc)
        return False
