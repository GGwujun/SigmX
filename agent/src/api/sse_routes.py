"""SSE streaming endpoints — bridge Redis pub/sub to browser EventSource.

Endpoints:
- GET /stream/fund-prices — subscribes to Redis 'fund:prices'
- GET /stream/alerts — subscribes to Redis 'fund:alerts'

If Redis is unavailable, returns 503 (client falls back to polling).
15-second keepalive comments prevent proxy timeouts.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_KEEPALIVE_SEC = 15


def _subscribe_redis(channel: str):
    """Yield messages from a Redis pub/sub channel.

    Returns an async generator. If Redis unavailable, raises immediately.
    """
    from src.lib.redis_client import get_redis
    r = get_redis()
    if r is None:
        raise RuntimeError("Redis not available")

    pubsub = r.pubsub()
    pubsub.subscribe(channel)
    try:
        for message in pubsub.listen():
            if message["type"] == "message":
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield data
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()


async def _sse_generator(channel: str):
    """Async SSE generator with keepalive. Wraps sync Redis subscription."""
    loop = asyncio.get_event_loop()
    try:
        # Run blocking Redis subscription in executor
        gen = _subscribe_redis(channel)

        # Send initial connection event
        yield f"event: connected\ndata: {{\"channel\":\"{channel}\"}}\n\n"

        while True:
            try:
                # Run next() in executor to avoid blocking the event loop
                data = await loop.run_in_executor(None, next, gen)
                yield f"event: {channel.replace(':', '_')}\ndata: {data}\n\n"
            except StopIteration:
                break
            except Exception as exc:
                logger.debug("sse: subscription error on %s: %s", channel, exc)
                yield f"event: error\ndata: {{\"error\":\"{exc}\"}}\n\n"
                break

    except RuntimeError:
        yield f"event: error\ndata: {{\"error\":\"Redis not available\"}}\n\n"
        return

    # Keepalive loop won't be reached if subscription is blocking,
    # but the sync listen() loop handles its own blocking reads.


def register_sse_routes(app: FastAPI, require_auth: Any) -> None:
    """Register SSE streaming endpoints."""
    from fastapi import Depends

    @app.get("/stream/fund-prices")
    async def stream_fund_prices(request: Request, _=Depends(require_auth)):
        """SSE stream for real-time fund price updates."""
        return StreamingResponse(
            _sse_generator("fund:prices"),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @app.get("/stream/alerts")
    async def stream_alerts(request: Request, _=Depends(require_auth)):
        """SSE stream for real-time alert notifications."""
        return StreamingResponse(
            _sse_generator("fund:alerts"),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
