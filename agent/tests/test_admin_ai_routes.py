from pathlib import Path

from cryptography.fernet import Fernet

import src.api.admin_ai_routes as routes
from src.product.ai_runtime_config import AIRuntimeConfigService
from src.product.store import ProductStore


def test_admin_provider_response_never_returns_plaintext_secret(tmp_path: Path) -> None:
    routes._service = AIRuntimeConfigService(ProductStore(tmp_path / "product.db"), encryption_key=Fernet.generate_key())
    try:
        response = routes.save_provider(
            "deepseek",
            routes.ProviderInput(
                name="DeepSeek",
                base_url="https://api.deepseek.com/v1",
                api_key="sk-production-secret",
                models=["deepseek-chat"],
                enabled=True,
            ),
            admin={"id": "admin-1", "email": "admin@sigmx.local"},
        )
        assert response.configured is True
        assert response.api_key_masked == "sk-p…cret"
        assert "production-secret" not in response.model_dump_json()
    finally:
        routes._service = None


def test_admin_ai_router_is_admin_protected() -> None:
    assert routes.router.dependencies
