import asyncio
from datetime import datetime, timezone

import src.api.product_routes as routes
from src.product.datahub_credentials import DataHubCredentialService
from src.product.store import ProductStore


def setup(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    routes._store = store
    routes._credential_service = DataHubCredentialService(store)
    routes._budget_service = None
    c1 = routes._credential_service.create("u1", "Notebook", ["stocks.metadata"], [], None)
    c2 = routes._credential_service.create("u2", "Other", ["stocks.metadata"], [], None)
    now = datetime.now(timezone.utc).isoformat()
    store._get_conn().executemany(
        "INSERT INTO datahub_request_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("r-ok", "u1", c1.id, "stocks.metadata", 200, 1, 1, 1, 1, 12, None, now),
            ("r-bad", "u1", c1.id, "stocks.metadata", 500, 1, 0, 1, 0, 8, "handler_error", now),
            ("r-other", "u2", c2.id, "stocks.metadata", 200, 1, 1, 1, 1, 3, None, now),
        ],
    )
    store._get_conn().commit()
    return store, c1


def test_logs_are_owner_filtered_paginated_and_error_filterable(tmp_path):
    _, _ = setup(tmp_path)
    logs = asyncio.run(routes.datahub_logs(limit=1, before=None, errors_only=False, user={"id": "u1"}))
    assert len(logs.items) == 1
    assert logs.next_cursor is not None
    errors = asyncio.run(routes.datahub_logs(limit=50, before=None, errors_only=True, user={"id": "u1"}))
    assert [item.request_id for item in errors.items] == ["r-bad"]
    assert all(not hasattr(item, "key_hash") and not hasattr(item, "authorization") for item in errors.items)


def test_budget_crud_and_alerts_are_personal(tmp_path):
    store, credential = setup(tmp_path)
    budget = asyncio.run(routes.put_datahub_budget(
        credential.id, routes.PutDataHubBudgetRequest(daily_limit=100), user={"id": "u1"}
    ))
    assert budget.daily_limit == 100
    assert asyncio.run(routes.get_datahub_budget(credential.id, user={"id": "u1"})).remaining_today == 99
    store._get_conn().execute(
        "INSERT INTO datahub_budget_events VALUES (?,?,?,?,?,?,?)",
        (credential.id, "u1", datetime.now(timezone.utc).date().isoformat(), 50, 50, 100, datetime.now(timezone.utc).isoformat()),
    )
    store._get_conn().commit()
    alerts = asyncio.run(routes.datahub_budget_alerts(limit=10, user={"id": "u1"}))
    assert alerts.items[0].credential_name == "Notebook"
    assert asyncio.run(routes.put_datahub_budget(
        credential.id, routes.PutDataHubBudgetRequest(daily_limit=None), user={"id": "u1"}
    )) is None
