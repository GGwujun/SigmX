from datetime import datetime, timedelta, timezone
from pathlib import Path
import asyncio

import pytest
from fastapi import HTTPException

import src.api.product_routes as product_routes

from src.product.research_handoffs import (
    HandoffExpired,
    HandoffNotFound,
    HandoffUsed,
    ResearchHandoffService,
)
from src.product.store import ProductStore


@pytest.fixture
def clock():
    value = [datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)]
    return value, lambda: value[0]


def test_ticket_is_hashed_owner_bound_and_consumed_once(tmp_path: Path, clock) -> None:
    value, now = clock
    store = ProductStore(tmp_path / "product.db")
    service = ResearchHandoffService(store, now=now)

    created = service.create(
        "u1", "saved_query", {"query": "低估值高股息", "saved_query_id": "q1"}
    )

    row = store._get_conn().execute(
        "SELECT * FROM research_handoffs WHERE id=?", (created.id,)
    ).fetchone()
    assert created.token.startswith("sxrh_")
    assert created.token not in tuple(row)
    assert datetime.fromisoformat(created.expires_at) == value[0] + timedelta(minutes=10)
    with pytest.raises(HandoffNotFound):
        service.consume("u2", created.token)
    consumed = service.consume("u1", created.token)
    assert consumed.payload == {"query": "低估值高股息", "saved_query_id": "q1"}
    with pytest.raises(HandoffUsed):
        service.consume("u1", created.token)


def test_ticket_expiry_and_payload_allowlist(tmp_path: Path, clock) -> None:
    value, now = clock
    service = ResearchHandoffService(ProductStore(tmp_path / "product.db"), now=now)
    with pytest.raises(ValueError):
        service.create("u1", "saved_query", {"query": "x", "filesystem_path": "C:/secret"})
    with pytest.raises(ValueError):
        service.create("u1", "instrument", {"symbol": "600519.SH", "api_key": "secret"})
    with pytest.raises(ValueError):
        service.create("u1", "unknown", {"query": "x"})

    created = service.create("u1", "instrument", {"symbol": "600519.SH"})
    value[0] += timedelta(minutes=11)
    with pytest.raises(HandoffExpired):
        service.consume("u1", created.token)


def test_authenticated_handoff_routes_serialize_safe_contract(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "routes.db")
    product_routes._store = store
    product_routes._research_handoffs = None
    created = asyncio.run(product_routes.create_research_handoff(
        product_routes.CreateResearchHandoffRequest(
            kind="instrument", payload={"symbol": "600519.SH"}
        ),
        user={"id": "u1"},
    ))
    assert created.deep_link == f"sigmx://research/{created.token}"
    consumed = asyncio.run(product_routes.consume_research_handoff(
        created.token, user={"id": "u1"}
    ))
    assert consumed.kind == "instrument"
    assert consumed.payload == {"symbol": "600519.SH"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(product_routes.consume_research_handoff(created.token, user={"id": "u1"}))
    assert exc.value.status_code == 409
