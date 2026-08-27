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
    api_key: str | None


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
    reasoning_effort: str
    sources: list[AIDataSource]


class AIConfigurationError(RuntimeError):
    pass


class AIRuntimeConfigService:
    def __init__(self, store: ProductStore, *, encryption_key: bytes | None = None) -> None:
        self.store = store
        self._fernet = Fernet(encryption_key or self._environment_key(store))

    @staticmethod
    def _environment_key(store: ProductStore) -> bytes:
        explicit = os.getenv("SIGMX_AI_CONFIG_KEY", "").strip()
        if explicit:
            return explicit.encode("ascii")
        seed = os.getenv("JWT_SECRET", "").strip()
        if seed:
            return base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())

        # Local development generates its JWT secret in memory, so it is not
        # available through os.environ. Keep a separate machine-local Fernet
        # key beside the product database so the admin page can load and saved
        # provider secrets remain decryptable after a restart.
        key_path = store.db_path.with_name(".sigmx-ai-config.key")
        try:
            return key_path.read_bytes().strip()
        except FileNotFoundError:
            generated = Fernet.generate_key()
            try:
                with key_path.open("xb") as handle:
                    handle.write(generated + b"\n")
                try:
                    key_path.chmod(0o600)
                except OSError:
                    pass
                return generated
            except FileExistsError:
                return key_path.read_bytes().strip()

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

    def save_source_secret(self, code: str, secret: str | None, *, clear: bool, actor: str) -> None:
        normalized = code.strip().lower()
        with self.store.transaction() as conn:
            if clear:
                conn.execute("DELETE FROM ai_source_credentials WHERE code=?", (normalized,))
            elif secret and secret.strip():
                encrypted = self._fernet.encrypt(secret.strip().encode("utf-8")).decode("ascii")
                conn.execute(
                    "INSERT INTO ai_source_credentials(code,secret_ciphertext,updated_at) VALUES(?,?,?) "
                    "ON CONFLICT(code) DO UPDATE SET secret_ciphertext=excluded.secret_ciphertext,updated_at=excluded.updated_at",
                    (normalized, encrypted, _now()),
                )
            self._audit(conn, actor, "ai.source.secret.save", normalized, {"configured": bool(secret and secret.strip()) and not clear, "cleared": clear})

    def source_secret_configured(self, code: str) -> bool:
        return self.store._get_conn().execute("SELECT 1 FROM ai_source_credentials WHERE code=?", (code,)).fetchone() is not None

    def reveal_source_secret(self, code: str) -> str:
        row = self.store._get_conn().execute("SELECT secret_ciphertext FROM ai_source_credentials WHERE code=?", (code,)).fetchone()
        if row is None:
            raise AIConfigurationError(f"data source {code} has no credential")
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

    def save_platform_settings(self, *, provider: str, model_name: str, base_url: str, temperature: float,
                               timeout_seconds: int, max_retries: int, reasoning_effort: str, actor: str) -> dict:
        current = self.get_provider(provider)
        self.save_provider(code=provider, name=current.name, base_url=base_url, api_key=None,
                           models=list(dict.fromkeys([model_name, *current.models])), enabled=True, actor=actor)
        self.save_strategy(actor=actor, planning_provider=provider, planning_model=model_name,
                           execution_provider=provider, execution_model=model_name,
                           summary_provider=provider, summary_model=model_name, temperature=temperature,
                           max_tokens=8000, timeout_seconds=timeout_seconds, max_retries=max_retries)
        with self.store.transaction() as conn:
            conn.execute("INSERT OR REPLACE INTO ai_platform_settings(id,reasoning_effort,updated_at) VALUES(1,?,?)", (reasoning_effort, _now()))
        return self.get_platform_settings()

    def get_platform_settings(self) -> dict:
        strategy = self.get_strategy() or {}
        effort = self.store._get_conn().execute("SELECT reasoning_effort FROM ai_platform_settings WHERE id=1").fetchone()
        provider_code = strategy.get("execution_provider", "")
        provider = self.get_provider(provider_code) if provider_code else None
        return {"provider": provider_code, "model_name": strategy.get("execution_model", ""),
                "base_url": provider.base_url if provider else "", "api_key_configured": provider.configured if provider else False,
                "temperature": float(strategy.get("temperature", 0.2)), "timeout_seconds": int(strategy.get("timeout_seconds", 90)),
                "max_retries": int(strategy.get("max_retries", 2)), "reasoning_effort": effort[0] if effort else ""}

    def get_strategy(self) -> dict | None:
        row = self.store._get_conn().execute("SELECT * FROM ai_model_strategy WHERE id=1").fetchone()
        return dict(row) if row else None

    def list_sources(self) -> list[AIDataSource]:
        rows = self.store._get_conn().execute("SELECT * FROM ai_data_sources ORDER BY priority,code").fetchall()
        return [AIDataSource(row["code"], bool(row["enabled"]), row["priority"], json.loads(row["markets_json"])) for row in rows]

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
            api_key = None if code in {"openai-codex", "openai_codex"} else self.reveal_api_key(code)
            return AIModelBinding(code, strategy[f"{prefix}_model"], provider.base_url, api_key)

        source_rows = self.store._get_conn().execute(
            "SELECT * FROM ai_data_sources WHERE enabled=1 ORDER BY priority,code"
        ).fetchall()
        effort = self.store._get_conn().execute(
            "SELECT reasoning_effort FROM ai_platform_settings WHERE id=1"
        ).fetchone()
        return AIRuntimeConfig(
            planning=binding("planning"), execution=binding("execution"), summary=binding("summary"),
            temperature=float(strategy["temperature"]), max_tokens=int(strategy["max_tokens"]),
            timeout_seconds=int(strategy["timeout_seconds"]), max_retries=int(strategy["max_retries"]),
            reasoning_effort=str(effort[0]) if effort else "",
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
    max_retries: int, reasoning_effort: str = "", constructor=None,
    codex_constructor=None,
):
    """Build a ChatLLM from server-owned settings without mutating process env."""
    if binding.provider in {"openai-codex", "openai_codex"}:
        if codex_constructor is None:
            from src.providers.openai_codex import OpenAICodexLLM

            codex_constructor = OpenAICodexLLM
        client = codex_constructor(
            model=binding.model,
            temperature=temperature,
            timeout=timeout_seconds,
            reasoning_effort=reasoning_effort or None,
            codex_url=binding.base_url,
        )
        from src.providers.chat import ChatLLM

        return ChatLLM(model_name=binding.model, client=client)

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
