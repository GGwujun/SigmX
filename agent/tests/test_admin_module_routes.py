import asyncio
from pathlib import Path

import pytest

from src.api import admin_module_routes as routes
from src.auth.store import UserStore
from src.product.store import ProductStore


@pytest.fixture(autouse=True)
def stores(tmp_path: Path):
    routes._user_store = UserStore(tmp_path / "users.db")
    routes._product_store = ProductStore(tmp_path / "product.db")
    yield
    routes._user_store = None
    routes._product_store = None


def test_user_module_reports_persisted_users_without_invented_counts() -> None:
    response = asyncio.run(routes.admin_module("users", {"is_admin": True}))
    total = next(item.value for item in response.stats if item.key == "total_users")
    assert total == len(response.rows)
    assert all("demo@" not in str(cell) for row in response.rows for cell in row.cells)


def test_audit_module_is_empty_when_no_audit_rows_exist() -> None:
    response = asyncio.run(routes.admin_module("audit", {"is_admin": True}))
    assert response.rows == []
    assert next(item.value for item in response.stats if item.key == "audit_events") == 0


def test_unknown_module_is_rejected() -> None:
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.admin_module("unknown", {"is_admin": True}))
    assert error.value.status_code == 404
