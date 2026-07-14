"""The business API must remain a read-only market-data consumer."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from src.api import market_sync_routes as routes


@pytest.mark.parametrize(
    ("handler", "body"),
    [
        (routes.sync_daily, routes.DailySyncRequest()),
        (routes.sync_code, routes.CodeSyncRequest(code="600000.SH")),
        (routes.backfill, routes.BackfillRequest()),
        (routes.snapshot, routes.DailySyncRequest()),
    ],
)
def test_mutating_sync_endpoints_require_worker(handler, body) -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(handler(body))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SYNC_WORKER_REQUIRED"


def test_push_endpoint_is_disabled() -> None:
    with pytest.raises(HTTPException) as exc:
        routes.push_data(routes.PushRequest(table="bars_daily", trade_date="2026-07-14", rows=[]))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SYNC_WORKER_REQUIRED"
