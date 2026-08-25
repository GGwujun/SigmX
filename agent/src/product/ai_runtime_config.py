"""Administrator-owned AI runtime configuration with encrypted secrets."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

from src.product.store import ProductStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AIProviderView:
    code: str
    name: str
    base_url: str
    models: list[str]
    enabled: bool
    api_key_masked: str | None
    configured: bool
    updated_at: str


@dataclass(frozen=True)
class AIModelBinding:
    provider: str
    model: str
    base_url: str
    api_key: str


@dataclass(frozen=True)
class AIDataSource:
    code: str
    enabled: bool
    priority: int
    markets: list[str]


@dataclass(frozen=True)
class AIRuntimeConfig:
    planning: AIModelBinding
    execution: AIModelBinding
    summary: AIModelBinding
    temperature: float
    max_tokens: int
    timeout_seconds: int
    max_retries: int
    sources: list[AIDataSource]


class AIConfigurationError(RuntimeError):
    pass


class AIRuntimeConfigService:
    def __init__(self, store: ProductStore, *, encryption_key: bytes | None = None) -> None:
        self.store = store
        self._fernet = Fernet(encryption_key or self._environment_key())

    @staticmethod
    def _environment_key() -> bytes:
        explicit = os.getenv("SIGMX_AI_CONFIG_KEY", "").strip()
        if explicit:
            return explicit.encode("ascii")
        seed = os.getenv("JWT_SECRET", "").strip()
        if not seed:
            raise AIConfigurationError("SIGMX_AI_CONFIG_KEY or JWT_SECRET is required")
        return base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) <= 8:
            return "••••••••"
        return f"{value[:4]}…{value[-4:]}"

    def save_provider(
        self, *, code: str, name: str, base_url: str, api_key: str | None,
        models: list[str], enabled: bool, actor: str,
    ) -> AIProviderView:
        normalized = code.strip().lower()
        if not normalized or not name.strip() or not base_url.strip():
            raise ValueError("provider code, name and base_url are required")
        existing = self.store._get_conn().execute(
            "SELECT api_key_ciphertext FROM ai_model_providers WHERE code=?", (normalized,)
        ).fetchone()
        ciphertext = existing[0] if existing else None
        if api_key is not None:
            if not api_key.strip():
                raise ValueError("api_key cannot be empty")
            ciphertext = self._fernet.encrypt(api_key.strip().encode("utf-8")).decode("ascii")
        now = _now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO ai_model_providers(code,name,base_url,api_key_ciphertext,models_json,enabled,updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET name=excluded.name,base_url=excluded.base_url,"
                "api_key_ciphertext=excluded.api_key_ciphertext,models_json=excluded.models_json,enabled=excluded.enabled,updated_at=excluded.updated_at",
                (normalized, name.strip(), base_url.rstrip("/"), ciphertext, json.dumps(models), int(enabled), now),
            )
            self._audit(conn, actor, "ai.provider.save", normalized, {"enabled": enabled, "models": models})
        return self.get_provider(normalized)

    def get_provider(self, code: str) -> AIProviderView:
        row = self.store._get_conn().execute(
            "SELECT * FROM ai_model_providers WHERE code=?", (code,)
        ).fetchone()
        if row is None:
            raise KeyError(code)
        secret = self._decrypt(row["api_key_ciphertext"]) if row["api_key_ciphertext"] else None
        return AIProviderView(
            code=row["code"], name=row["name"], base_url=row["base_url"],
            models=json.loads(row["models_json"]), enabled=bool(row["enabled"]),
            api_key_masked=self._mask(secret) if secret else None,
            configured=bool(secret), updated_at=row["updated_at"],
        )

    def list_providers(self) -> list[AIProviderView]:
        rows = self.store._get_conn().execute("SELECT code FROM ai_model_providers ORDER BY code").fetchall()
        return [self.get_provider(row[0]) for row in rows]

    def reveal_api_key(self, code: str) -> str:
        row = self.store._get_conn().execute(
            "SELECT api_key_ciphertext FROM ai_model_providers WHERE code=?", (code,)
        ).fetchone()
        if row is None or not row[0]:
            raise AIConfigurationError(f"provider {code} has no API key")
        return self._decrypt(row[0])

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise AIConfigurationError("AI provider secret cannot be decrypted") from exc

    def save_strategy(self, *, actor: str, **values) -> None:
        required = ("planning_provider", "planning_model", "execution_provider", "execution_model", "summary_provider", "summary_model")
        if any(not str(values.get(key, "")).strip() for key in required):
            raise ValueError("all model bindings are required")
        now = _now()
        columns = required + ("temperature", "max_tokens", "timeout_seconds", "max_retries")
        payload = tuple(values[key] for key in columns)
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ai_model_strategy(id," + ",".join(columns) + ",updated_at) VALUES(1," + ",".join("?" for _ in columns) + ",?)",
                (*payload, now),
            )
            self._audit(conn, actor, "ai.strategy.save", "default", {key: values[key] for key in columns})

    def save_source(self, code: str, *, enabled: bool, priority: int, markets: list[str], actor: str) -> AIDataSource:
        if priority < 0:
            raise ValueError("priority must be non-negative")
        now = _now()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO ai_data_sources(code,enabled,priority,markets_json,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET enabled=excluded.enabled,priority=excluded.priority,markets_json=excluded.markets_json,updated_at=excluded.updated_at",
                (code, int(enabled), priority, json.dumps(markets, ensure_ascii=False), now),
            )
            self._audit(conn, actor, "ai.source.save", code, {"enabled": enabled, "priority": priority, "markets": markets})
        return AIDataSource(code, enabled, priority, markets)

    def get_effective(self) -> AIRuntimeConfig:
        strategy = self.store._get_conn().execute("SELECT * FROM ai_model_strategy WHERE id=1").fetchone()
        if strategy is None:
            raise AIConfigurationError("AI model strategy is not configured")

        def binding(prefix: str) -> AIModelBinding:
            code = strategy[f"{prefix}_provider"]
            provider = self.get_provider(code)
            if not provider.enabled:
                raise AIConfigurationError(f"provider {code} is disabled")
            return AIModelBinding(code, strategy[f"{prefix}_model"], provider.base_url, self.reveal_api_key(code))

        source_rows = self.store._get_conn().execute(
            "SELECT * FROM ai_data_sources WHERE enabled=1 ORDER BY priority,code"
        ).fetchall()
        return AIRuntimeConfig(
            planning=binding("planning"), execution=binding("execution"), summary=binding("summary"),
            temperature=float(strategy["temperature"]), max_tokens=int(strategy["max_tokens"]),
            timeout_seconds=int(strategy["timeout_seconds"]), max_retries=int(strategy["max_retries"]),
            sources=[AIDataSource(row["code"], True, row["priority"], json.loads(row["markets_json"])) for row in source_rows],
        )

    @staticmethod
    def _audit(conn, actor: str, action: str, target: str, metadata: dict) -> None:
        conn.execute(
            "INSERT INTO audit_log(id,actor,action,target,reason,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, actor, action, target, "AI runtime configuration", json.dumps(metadata, ensure_ascii=False), _now()),
        )


def build_configured_chat(
    binding: AIModelBinding, *, temperature: float, timeout_seconds: int,
    max_retries: int, constructor=None,
):
    """Build a ChatLLM from server-owned settings without mutating process env."""
    if constructor is None:
        from src.providers.llm import ChatOpenAIWithReasoning

        constructor = ChatOpenAIWithReasoning
    client = constructor(
        model=binding.model,
        temperature=temperature,
        timeout=timeout_seconds,
        max_retries=max_retries,
        api_key=binding.api_key,
        base_url=binding.base_url,
    )
    from src.providers.chat import ChatLLM

    return ChatLLM(model_name=binding.model, client=client)
