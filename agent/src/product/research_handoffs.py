"""Short-lived, one-time Web-to-Desktop research handoff tickets."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from src.product.store import ProductStore


class HandoffNotFound(Exception):
    pass


class HandoffExpired(Exception):
    pass


class HandoffUsed(Exception):
    pass


@dataclass(frozen=True)
class CreatedResearchHandoff:
    id: str
    token: str
    deep_link: str
    expires_at: str


@dataclass(frozen=True)
class ConsumedResearchHandoff:
    id: str
    kind: str
    payload: dict[str, str]
    created_at: str


_ALLOWED_FIELDS = {
    "saved_query": frozenset({"query", "saved_query_id"}),
    "instrument": frozenset({"symbol"}),
    "similar_query": frozenset({"query", "report_slug"}),
}
_REQUIRED_FIELDS = {
    "saved_query": frozenset({"query"}),
    "instrument": frozenset({"symbol"}),
    "similar_query": frozenset({"query"}),
}
_TOKEN_RE = re.compile(r"^sxrh_[0-9a-f]{48}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchHandoffService:
    def __init__(self, store: ProductStore, now: Callable[[], datetime] = _utc_now) -> None:
        self.store = store
        self._now = now

    def create(self, user_id: str, kind: str, payload: dict) -> CreatedResearchHandoff:
        clean = self._validate_payload(kind, payload)
        token = "sxrh_" + secrets.token_hex(24)
        handoff_id = uuid.uuid4().hex
        created_at = self._now().isoformat()
        expires_at = (self._now() + timedelta(minutes=10)).isoformat()
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO research_handoffs "
                "(id,user_id,token_hash,kind,payload_json,expires_at,consumed_at,created_at) "
                "VALUES (?,?,?,?,?,?,NULL,?)",
                (handoff_id, user_id, self._hash(token), kind,
                 json.dumps(clean, ensure_ascii=False, sort_keys=True), expires_at, created_at),
            )
        return CreatedResearchHandoff(handoff_id, token, f"sigmx://research/{token}", expires_at)

    def consume(self, user_id: str, token: str) -> ConsumedResearchHandoff:
        if not _TOKEN_RE.fullmatch(token or ""):
            raise HandoffNotFound("research handoff not found")
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM research_handoffs WHERE token_hash=? AND user_id=?",
                (self._hash(token), user_id),
            ).fetchone()
            if row is None:
                raise HandoffNotFound("research handoff not found")
            if row["consumed_at"] is not None:
                raise HandoffUsed("research handoff was already consumed")
            if datetime.fromisoformat(row["expires_at"]) <= self._now():
                raise HandoffExpired("research handoff has expired")
            conn.execute(
                "UPDATE research_handoffs SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                (self._now().isoformat(), row["id"]),
            )
            return ConsumedResearchHandoff(
                row["id"], row["kind"], json.loads(row["payload_json"]), row["created_at"]
            )

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_payload(kind: str, payload: dict) -> dict[str, str]:
        if kind not in _ALLOWED_FIELDS or not isinstance(payload, dict):
            raise ValueError("unsupported research handoff kind")
        if set(payload) - _ALLOWED_FIELDS[kind] or not _REQUIRED_FIELDS[kind].issubset(payload):
            raise ValueError("research handoff payload contains unsupported fields")
        clean: dict[str, str] = {}
        for key, value in payload.items():
            if not isinstance(value, str) or not value.strip() or len(value.strip()) > 1000:
                raise ValueError("research handoff payload values must be non-empty strings")
            clean[key] = value.strip()
        if "symbol" in clean and not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", clean["symbol"]):
            raise ValueError("invalid instrument symbol")
        return clean
