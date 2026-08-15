from datetime import datetime, timezone

from src.product.datahub_budgets import DataHubBudgetService
from src.product.datahub_credentials import DataHubCredentialService
from src.product.notifications import PersonalNotificationService
from src.product.store import ProductStore
import asyncio
import src.api.product_routes as pr


def test_notification_owner_read_and_preferences(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    service = PersonalNotificationService(store)
    service.emit("u1", "product", "已开通", "Desktop Pro", event_id="product:o1")
    assert len(service.list("u1")) == 1
    assert service.list("u2") == []
    assert service.mark_read("u2", "product:o1") is False
    assert service.mark_read("u1", "product:o1") is True
    assert service.list("u1")[0].read_at is not None
    service.set_preferences("u1", budget_alerts=False, product_updates=True, cloud_tasks=True)
    assert service.preferences("u1").budget_alerts is False


def test_budget_threshold_respects_preference_but_keeps_audit_event(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    credential = DataHubCredentialService(store).create("u1", "dev", ["stocks.metadata"], [], None)
    budgets = DataHubBudgetService(store)
    budgets.set("u1", credential.id, 10)
    PersonalNotificationService(store).set_preferences(
        "u1", budget_alerts=False, product_updates=True, cloud_tasks=True
    )
    now = datetime.now(timezone.utc).isoformat()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO datahub_request_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("r1", "u1", credential.id, "stocks.metadata", 200, 1, 1, 10, 10, 1, None, now),
        )
        budgets.record_events(conn, "u1", credential.id)
    assert [event.threshold_percent for event in budgets.list_events("u1")] == [100, 80, 50]
    assert PersonalNotificationService(store).list("u1") == []


def test_notification_routes_are_owner_scoped(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._notification_service = PersonalNotificationService(store)
    try:
        pr._notification_service.emit("u1", "cloud", "任务完成", "报告已生成", event_id="cloud:r1")
        inbox = asyncio.run(pr.list_notifications(limit=100, user={"id": "u1"}))
        assert inbox.items[0].id == "cloud:r1"
        asyncio.run(pr.read_notification("cloud:r1", user={"id": "u1"}))
        preferences = asyncio.run(pr.put_notification_preferences(
            body=pr.PutNotificationPreferencesRequest(
                budget_alerts=True, product_updates=False, cloud_tasks=True
            ),
            user={"id": "u1"},
        ))
        assert preferences.product_updates is False
    finally:
        pr._store = None
        pr._notification_service = None
