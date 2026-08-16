import asyncio
from pathlib import Path

import src.api.operations_routes as routes
from src.product.operations import ProductOperations
from src.product.store import ProductStore


def test_admin_operations_api_updates_all_operational_domains(tmp_path: Path) -> None:
    routes._operations = ProductOperations(ProductStore(tmp_path / "product.db"), now=lambda: "2026-08-16T04:00:00Z")
    admin = {"id": "admin", "email": "admin@sigmx.cn"}
    try:
        asyncio.run(routes.put_product("desktop_pro", routes.ProductUpdate(enabled=True, price_cny_fen=26800, reason="季度价格确认"), admin))
        asyncio.run(routes.put_endpoint("market.daily", routes.EndpointUpdate(enabled=True, credit_cost=3, unit_cost_cny_fen=1.2, quality_score=0.998, reason="接口成本校准"), admin))
        asyncio.run(routes.put_content("home.hero", routes.ContentUpdate(title="AI 选股", href="/query", enabled=True, reason="首页内容调整"), admin))
        state = asyncio.run(routes.operations_state(days=30, admin=admin))

        assert state.products[0]["code"] == "desktop_pro"
        assert state.endpoints[0]["quality_score"] == 0.998
        assert state.content[0]["slot"] == "home.hero"
        assert len(state.audit) == 3
    finally:
        routes._operations = None


def test_operations_routes_require_admin_or_current_user() -> None:
    for route in (*routes.admin_router.routes, *routes.telemetry_router.routes):
        assert route.dependant.dependencies
