from pathlib import Path

from src.product.operations import ProductOperations
from src.product.store import ProductStore


def test_operations_manage_catalog_endpoints_content_and_audit(tmp_path: Path) -> None:
    ops = ProductOperations(ProductStore(tmp_path / "product.db"), now=lambda: "2026-08-16T04:00:00Z")

    product = ops.upsert_product("desktop_pro", enabled=True, price_cny_fen=26800, actor_id="admin", reason="季度定价确认")
    endpoint = ops.upsert_endpoint("market.daily", enabled=True, credit_cost=3, unit_cost_cny_fen=1.2, quality_score=0.998, actor_id="admin", reason="生产成本校准")
    content = ops.upsert_content("home.hero", title="AI 选股入口", href="/query", enabled=True, actor_id="admin", reason="首页运营调整")

    assert product.price_cny_fen == 26800
    assert endpoint.credit_cost == 3
    assert content.slot == "home.hero"
    assert len(ops.audit_log()) == 3
    assert ops.audit_log()[0].before == {}


def test_manual_activation_refund_is_idempotent_and_commercial_metrics_include_margin(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    ops = ProductOperations(store, now=lambda: "2026-08-16T04:00:00Z")
    with store.transaction() as conn:
        conn.execute("INSERT INTO orders (id,user_id,plan_code,status,channel,price_cny_fen,entitlements_snapshot_json,months,idempotency_key,created_at,paid_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", ("o1", "u1", "desktop_pro", "paid", "activation_code", 26800, "{}", 3, "order:1", "2026-08-16T00:00:00Z", "2026-08-16T00:00:00Z"))

    first = ops.refund_activation_order("o1", actor_id="admin", reason="激活码误发", idempotency_key="refund:1")
    second = ops.refund_activation_order("o1", actor_id="admin", reason="激活码误发", idempotency_key="refund:1")
    ops.record_desktop_event("u1", "research_completed", session_id="device-day-1")
    ops.record_usage_cost("market.daily", revenue_cny_fen=30, cost_cny_fen=12, idempotency_key="usage:1")

    assert first.id == second.id
    assert first.status == "recorded"
    metrics = ops.metrics(days=30)
    assert metrics.desktop_research_users == 1
    assert metrics.usage_revenue_cny_fen == 30
    assert metrics.usage_cost_cny_fen == 12
    assert metrics.gross_margin_rate == 0.6
