from pathlib import Path

from cryptography.fernet import Fernet

from src.product.ai_runtime_config import AIModelBinding, AIRuntimeConfigService, build_configured_chat
from src.product.store import ProductStore


def test_provider_secret_is_encrypted_at_rest_and_masked_on_read(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    service = AIRuntimeConfigService(store, encryption_key=Fernet.generate_key())

    provider = service.save_provider(
        code="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-live-secret-value",
        models=["deepseek-chat", "deepseek-reasoner"],
        enabled=True,
        actor="admin-1",
    )

    raw = store._get_conn().execute(
        "SELECT api_key_ciphertext FROM ai_model_providers WHERE code='deepseek'"
    ).fetchone()[0]
    assert "sk-live-secret-value" not in raw
    assert provider.api_key_masked == "sk-l…alue"
    assert service.reveal_api_key("deepseek") == "sk-live-secret-value"


def test_effective_config_uses_enabled_strategy_and_source_priority(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    service = AIRuntimeConfigService(store, encryption_key=Fernet.generate_key())
    service.save_provider(
        code="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="secret",
        models=["gpt-5"],
        enabled=True,
        actor="admin-1",
    )
    service.save_strategy(
        planning_provider="openai",
        planning_model="gpt-5",
        execution_provider="openai",
        execution_model="gpt-5",
        summary_provider="openai",
        summary_model="gpt-5",
        temperature=0.2,
        max_tokens=8000,
        timeout_seconds=90,
        max_retries=2,
        actor="admin-1",
    )
    service.save_source("data_hub", enabled=True, priority=10, markets=["A股"], actor="admin-1")
    service.save_source("akshare", enabled=True, priority=20, markets=["A股"], actor="admin-1")

    effective = service.get_effective()

    assert effective.planning.model == "gpt-5"
    assert effective.planning.api_key == "secret"
    assert [source.code for source in effective.sources] == ["data_hub", "akshare"]


def test_admin_changes_are_audited_without_secret_material(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    service = AIRuntimeConfigService(store, encryption_key=Fernet.generate_key())
    service.save_provider(
        code="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="never-log-this",
        models=["gpt-5"],
        enabled=True,
        actor="admin@example.com",
    )

    row = store._get_conn().execute(
        "SELECT actor, action, metadata_json FROM audit_log ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row["actor"] == "admin@example.com"
    assert row["action"] == "ai.provider.save"
    assert "never-log-this" not in row["metadata_json"]


def test_configured_chat_uses_platform_binding_without_mutating_environment() -> None:
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    chat = build_configured_chat(
        AIModelBinding("deepseek", "deepseek-chat", "https://api.deepseek.com/v1", "secret"),
        temperature=0.3,
        timeout_seconds=45,
        max_retries=1,
        constructor=FakeClient,
    )

    assert chat.model_name == "deepseek-chat"
    assert captured == {
        "model": "deepseek-chat", "temperature": 0.3, "timeout": 45,
        "max_retries": 1, "api_key": "secret", "base_url": "https://api.deepseek.com/v1",
    }
