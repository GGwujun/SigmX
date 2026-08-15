from datetime import datetime, timedelta, timezone
import json

import pytest

from src.product.notifications import PersonalNotificationService
from src.product.store import ProductStore
from src.product.subscriptions import SavedQuerySubscriptionService
import asyncio
import src.api.product_routes as pr


def test_subscription_is_owner_bound_and_due_processing_is_idempotent(tmp_path):
    now = [datetime(2026, 8, 15, 8, 0, tzinfo=timezone.utc)]
    store = ProductStore(tmp_path / "product.db")
    store._get_conn().execute(
        "INSERT INTO saved_queries (id,user_id,query,result_summary_json,created_at) VALUES (?,?,?,?,?)",
        ("q1", "u1", "高股息", json.dumps({}), now[0].isoformat()),
    )
    store._get_conn().commit()
    service = SavedQuerySubscriptionService(store, now=lambda: now[0])
    subscription = service.create("u1", "q1", "daily")
    with pytest.raises(ValueError): service.create("u2", "q1", "daily")
    assert service.list("u2") == []

    now[0] += timedelta(days=1, seconds=1)
    assert service.process_due("u1") == 1
    assert service.process_due("u1") == 0
    notifications = PersonalNotificationService(store).list("u1")
    assert len(notifications) == 1
    assert "高股息" in notifications[0].body
    assert service.delete("u2", subscription.id) is False
    assert service.delete("u1", subscription.id) is True


def test_subscription_routes_create_update_list_and_delete(tmp_path):
    store = ProductStore(tmp_path / "routes.db")
    pr._store = store
    pr._subscription_service = SavedQuerySubscriptionService(store)
    try:
        store._get_conn().execute(
            "INSERT INTO saved_queries (id,user_id,query,result_summary_json,created_at) VALUES (?,?,?,?,?)",
            ("q1", "u1", "低波动", json.dumps({}), datetime.now(timezone.utc).isoformat()),
        )
        store._get_conn().commit()
        created = asyncio.run(pr.put_saved_query_subscription(
            pr.PutSavedQuerySubscriptionRequest(saved_query_id="q1", frequency="weekly"),
            user={"id": "u1"},
        ))
        assert created.frequency == "weekly"
        assert asyncio.run(pr.list_saved_query_subscriptions(user={"id": "u2"})).items == []
        assert [item.id for item in asyncio.run(pr.list_saved_query_subscriptions(user={"id": "u1"})).items] == [created.id]
        with pytest.raises(pr.HTTPException) as error:
            asyncio.run(pr.delete_saved_query_subscription(created.id, user={"id": "u2"}))
        assert error.value.status_code == 404
        assert asyncio.run(pr.delete_saved_query_subscription(created.id, user={"id": "u1"})) == {"ok": True}
    finally:
        pr._store = None
        pr._subscription_service = None
