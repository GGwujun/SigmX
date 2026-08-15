"""Auditable support actions scoped to individual SigmX users."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from src.product.store import ProductStore


class SupportTargetNotFound(ValueError):
    pass


class PersonalSupportOperations:
    def __init__(self, store: ProductStore) -> None:
        self.store = store

    def compensate(self, actor: str, user_id: str, ledger: str, amount: int, reason: str) -> str:
        self._validate(actor, user_id, reason)
        if ledger not in {"research", "data"}:
            raise ValueError("ledger must be research or data")
        if amount <= 0 or amount > 1_000_000:
            raise ValueError("amount must be between 1 and 1000000")
        now = datetime.now(timezone.utc).isoformat()
        operation_id = uuid.uuid4().hex
        with self.store.transaction() as conn:
            if ledger == "research":
                conn.execute(
                    "INSERT INTO credit_lots (id,user_id,amount_total,amount_remaining,source,expires_at,idempotency_key,created_at) VALUES (?,?,?,?,?,NULL,?,?)",
                    (operation_id, user_id, amount, amount, "admin_compensation", operation_id, now),
                )
                conn.execute(
                    "INSERT INTO credit_ledger (id,user_id,lot_id,delta,operation,idempotency_key,created_at) VALUES (?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, user_id, operation_id, amount, "grant", operation_id, now),
                )
            else:
                conn.execute(
                    "INSERT INTO data_credit_lots (id,owner_id,amount_total,amount_remaining,source,expires_at,idempotency_key,created_at) VALUES (?,?,?,?,?,NULL,?,?)",
                    (operation_id, user_id, amount, amount, "admin_compensation", operation_id, now),
                )
                conn.execute(
                    "INSERT INTO data_credit_ledger (id,owner_id,lot_id,reservation_id,delta,operation,idempotency_key,metadata_json,created_at) VALUES (?,?,?,NULL,?,?,?,?,?)",
                    (uuid.uuid4().hex, user_id, operation_id, amount, "grant", operation_id, "{}", now),
                )
            self._audit(conn, actor, "personal.credit.compensate", user_id, reason, {"ledger": ledger, "amount": amount, "operation_id": operation_id}, now)
        return operation_id

    def revoke_device(self, actor: str, user_id: str, device_id: str, reason: str) -> None:
        self._validate(actor, user_id, reason)
        now = datetime.now(timezone.utc).isoformat()
        with self.store.transaction() as conn:
            row = conn.execute("SELECT id FROM devices WHERE id=? AND user_id=?", (device_id, user_id)).fetchone()
            if row is None:
                raise SupportTargetNotFound("device not found")
            conn.execute("UPDATE devices SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, device_id))
            conn.execute("UPDATE refresh_tokens SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL", (now, device_id))
            self._audit(conn, actor, "personal.device.revoke", device_id, reason, {"user_id": user_id}, now)

    def revoke_credential(self, actor: str, user_id: str, credential_id: str, reason: str) -> None:
        self._validate(actor, user_id, reason)
        now = datetime.now(timezone.utc).isoformat()
        with self.store.transaction() as conn:
            row = conn.execute("SELECT id FROM datahub_credentials WHERE id=? AND user_id=? AND credential_kind='personal'", (credential_id, user_id)).fetchone()
            if row is None:
                raise SupportTargetNotFound("credential not found")
            conn.execute("UPDATE datahub_credentials SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (now, credential_id))
            self._audit(conn, actor, "personal.credential.revoke", credential_id, reason, {"user_id": user_id}, now)

    @staticmethod
    def _validate(actor: str, user_id: str, reason: str) -> None:
        if not actor.strip() or not user_id.strip():
            raise ValueError("actor and user_id are required")
        if len(reason.strip()) < 5 or len(reason) > 500:
            raise ValueError("reason must be 5 to 500 characters")

    @staticmethod
    def _audit(conn, actor: str, action: str, target: str, reason: str, metadata: dict, now: str) -> None:
        conn.execute(
            "INSERT INTO audit_log (id,actor,action,target,reason,metadata_json,created_at) VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, actor, action, target, reason.strip(), json.dumps(metadata, ensure_ascii=False, sort_keys=True), now),
        )
