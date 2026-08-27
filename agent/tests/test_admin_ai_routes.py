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


def test_platform_provider_catalog_includes_every_supported_runtime_provider() -> None:
    codes = {item["code"] for item in routes.PROVIDER_PRESETS}
    assert codes == {
        "openrouter", "openai", "openai-codex", "deepseek", "gemini", "groq",
        "dashscope", "qwen", "zhipu", "moonshot", "minimax", "mimo", "zai", "ollama",
    }
    codex = next(item for item in routes.PROVIDER_PRESETS if item["code"] == "openai-codex")
    assert codex["auth_type"] == "oauth"
    assert codex["api_key_required"] is False


def test_platform_settings_expose_single_model_and_never_return_secrets(tmp_path: Path) -> None:
    service = AIRuntimeConfigService(ProductStore(tmp_path / "product.db"), encryption_key=Fernet.generate_key())
    routes._service = service
    try:
        service.save_provider(code="deepseek", name="DeepSeek", base_url="https://api.deepseek.com/v1", api_key="sk-secret", models=["deepseek-chat"], enabled=True, actor="admin")
        response = routes.save_platform_settings(
            routes.PlatformSettingsInput(provider="deepseek", model_name="deepseek-chat", base_url="https://api.deepseek.com/v1", temperature=0.1, timeout_seconds=60, max_retries=2, reasoning_effort="high"),
            admin={"email": "admin@sigmx.local"},
        )
        assert response["provider"] == "deepseek"
        assert response["model_name"] == "deepseek-chat"
        assert response["reasoning_effort"] == "high"
        assert "secret" not in str(response)
        legacy = service.get_strategy()
        assert legacy["planning_provider"] == legacy["execution_provider"] == legacy["summary_provider"] == "deepseek"
    finally:
        routes._service = None


def test_platform_data_source_credentials_are_encrypted_and_masked(tmp_path: Path) -> None:
    service = AIRuntimeConfigService(ProductStore(tmp_path / "product.db"), encryption_key=Fernet.generate_key())
    routes._service = service
    try:
        result = routes.save_source_credentials(
            routes.SourceCredentialsInput(tushare_token="ts-private", tpdog_token="tp-private"),
            admin={"email": "admin@sigmx.local"},
        )
        assert result == {"tushare_token_configured": True, "tpdog_token_configured": True}
        assert "private" not in str(routes.get_source_credentials(admin={"email": "admin@sigmx.local"}))
        assert service.reveal_source_secret("tushare") == "ts-private"
    finally:
        routes._service = None
