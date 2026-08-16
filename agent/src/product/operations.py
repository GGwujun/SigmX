"""Audited operations domain for the personal SigmX product."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from src.product.store import ProductStore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ProductOverride:
    code: str; enabled: bool; price_cny_fen: int; updated_at: str


@dataclass(frozen=True)
class EndpointOperation:
    code: str; enabled: bool; credit_cost: int; unit_cost_cny_fen: float; quality_score: float; updated_at: str


@dataclass(frozen=True)
class ContentPlacement:
    slot: str; title: str; href: str; enabled: bool; updated_at: str


@dataclass(frozen=True)
class RefundRecord:
    id: str; order_id: str; user_id: str; status: str; reason: str; created_at: str


@dataclass(frozen=True)
class OperationAudit:
    id: str; actor_id: str; object_type: str; object_id: str; action: str
    reason: str; before: dict[str, Any]; after: dict[str, Any]; created_at: str


@dataclass(frozen=True)
class OperationsMetrics:
    desktop_research_users: int
    desktop_active_sessions: int
    usage_revenue_cny_fen: int
    usage_cost_cny_fen: int
    gross_margin_rate: float


class ProductOperations:
    def __init__(self, store: ProductStore, now: Callable[[], str] = _now_iso) -> None:
        self.store = store
        self._now = now
        self._create_schema()

    def _create_schema(self) -> None:
        conn = self.store._get_conn()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS operation_products (code TEXT PRIMARY KEY,enabled INTEGER NOT NULL,price_cny_fen INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_endpoints (code TEXT PRIMARY KEY,enabled INTEGER NOT NULL,credit_cost INTEGER NOT NULL,unit_cost_cny_fen REAL NOT NULL,quality_score REAL NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_content (slot TEXT PRIMARY KEY,title TEXT NOT NULL,href TEXT NOT NULL,enabled INTEGER NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_refunds (id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE,user_id TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,idempotency_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_desktop_events (id TEXT PRIMARY KEY,user_id TEXT NOT NULL,event TEXT NOT NULL,session_id TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,event,session_id));
        CREATE TABLE IF NOT EXISTS operation_usage_costs (id TEXT PRIMARY KEY,endpoint_code TEXT NOT NULL,revenue_cny_fen INTEGER NOT NULL,cost_cny_fen INTEGER NOT NULL,idempotency_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_audit (id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,object_type TEXT NOT NULL,object_id TEXT NOT NULL,action TEXT NOT NULL,reason TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,created_at TEXT NOT NULL);
        """)
        conn.commit()

    def upsert_product(self, code: str, *, enabled: bool, price_cny_fen: int, actor_id: str, reason: str) -> ProductOverride:
        self._validate_reason(reason)
        before = self._row("operation_products", "code", code)
        now = self._now()
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO operation_products VALUES (?,?,?,?) ON CONFLICT(code) DO UPDATE SET enabled=excluded.enabled,price_cny_fen=excluded.price_cny_fen,updated_at=excluded.updated_at", (code, int(enabled), max(0, int(price_cny_fen)), now))
            after = {"code": code, "enabled": int(enabled), "price_cny_fen": max(0, int(price_cny_fen)), "updated_at": now}
            self._audit(conn, actor_id, "product", code, "upsert", reason, before, after)
        return ProductOverride(code, enabled, max(0, int(price_cny_fen)), now)

    def upsert_endpoint(self, code: str, *, enabled: bool, credit_cost: int, unit_cost_cny_fen: float, quality_score: float, actor_id: str, reason: str) -> EndpointOperation:
        self._validate_reason(reason)
        before = self._row("operation_endpoints", "code", code)
        now = self._now(); quality = min(1.0, max(0.0, float(quality_score)))
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO operation_endpoints VALUES (?,?,?,?,?,?) ON CONFLICT(code) DO UPDATE SET enabled=excluded.enabled,credit_cost=excluded.credit_cost,unit_cost_cny_fen=excluded.unit_cost_cny_fen,quality_score=excluded.quality_score,updated_at=excluded.updated_at", (code, int(enabled), max(0, int(credit_cost)), max(0.0, float(unit_cost_cny_fen)), quality, now))
            after = {"code": code, "enabled": int(enabled), "credit_cost": max(0, int(credit_cost)), "unit_cost_cny_fen": max(0.0, float(unit_cost_cny_fen)), "quality_score": quality, "updated_at": now}
            self._audit(conn, actor_id, "endpoint", code, "upsert", reason, before, after)
        return EndpointOperation(code, enabled, after["credit_cost"], after["unit_cost_cny_fen"], quality, now)

    def upsert_content(self, slot: str, *, title: str, href: str, enabled: bool, actor_id: str, reason: str) -> ContentPlacement:
        self._validate_reason(reason)
        before = self._row("operation_content", "slot", slot); now = self._now()
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO operation_content VALUES (?,?,?,?,?) ON CONFLICT(slot) DO UPDATE SET title=excluded.title,href=excluded.href,enabled=excluded.enabled,updated_at=excluded.updated_at", (slot, title, href, int(enabled), now))
            after = {"slot": slot, "title": title, "href": href, "enabled": int(enabled), "updated_at": now}
            self._audit(conn, actor_id, "content", slot, "upsert", reason, before, after)
        return ContentPlacement(slot, title, href, enabled, now)

    def refund_activation_order(self, order_id: str, *, actor_id: str, reason: str, idempotency_key: str) -> RefundRecord:
        self._validate_reason(reason)
        existing = self.store._get_conn().execute("SELECT * FROM operation_refunds WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing: return self._refund(existing)
        order = self.store._get_conn().execute("SELECT * FROM orders WHERE id=? AND channel='activation_code'", (order_id,)).fetchone()
        if not order: raise KeyError(order_id)
        now = self._now(); refund_id = uuid.uuid4().hex
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO operation_refunds VALUES (?,?,?,?,?,?,?)", (refund_id, order_id, order["user_id"], "recorded", reason, idempotency_key, now))
            conn.execute("UPDATE orders SET status='refunded' WHERE id=?", (order_id,))
            conn.execute("DELETE FROM entitlement_grants WHERE order_id=?", (order_id,))
            self._audit(conn, actor_id, "activation_order", order_id, "refund", reason, dict(order), {**dict(order), "status": "refunded"})
        return self._refund(self.store._get_conn().execute("SELECT * FROM operation_refunds WHERE id=?", (refund_id,)).fetchone())

    def record_desktop_event(self, user_id: str, event: str, *, session_id: str) -> None:
        with self.store.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO operation_desktop_events VALUES (?,?,?,?,?)", (uuid.uuid4().hex, user_id, event, session_id, self._now()))

    def record_usage_cost(self, endpoint_code: str, *, revenue_cny_fen: int, cost_cny_fen: int, idempotency_key: str) -> None:
        with self.store.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO operation_usage_costs VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex, endpoint_code, max(0, revenue_cny_fen), max(0, cost_cny_fen), idempotency_key, self._now()))

    def metrics(self, *, days: int) -> OperationsMetrics:
        cutoff = (datetime.fromisoformat(self._now().replace("Z", "+00:00")) - timedelta(days=days)).isoformat()
        conn = self.store._get_conn()
        desktop_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM operation_desktop_events WHERE event='research_completed' AND created_at>=?", (cutoff,)).fetchone()[0]
        sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM operation_desktop_events WHERE created_at>=?", (cutoff,)).fetchone()[0]
        usage = conn.execute("SELECT COALESCE(SUM(revenue_cny_fen),0),COALESCE(SUM(cost_cny_fen),0) FROM operation_usage_costs WHERE created_at>=?", (cutoff,)).fetchone()
        revenue, cost = int(usage[0]), int(usage[1])
        margin = (revenue - cost) / revenue if revenue else 0.0
        return OperationsMetrics(int(desktop_users), int(sessions), revenue, cost, round(margin, 4))

    def audit_log(self, limit: int = 100) -> list[OperationAudit]:
        rows = self.store._get_conn().execute("SELECT * FROM operation_audit ORDER BY created_at,id LIMIT ?", (limit,)).fetchall()
        return [OperationAudit(row["id"], row["actor_id"], row["object_type"], row["object_id"], row["action"], row["reason"], json.loads(row["before_json"]), json.loads(row["after_json"]), row["created_at"]) for row in rows]

    def products(self) -> list[ProductOverride]:
        return [ProductOverride(row["code"], bool(row["enabled"]), int(row["price_cny_fen"]), row["updated_at"]) for row in self.store._get_conn().execute("SELECT * FROM operation_products ORDER BY code")]

    def endpoints(self) -> list[EndpointOperation]:
        return [EndpointOperation(row["code"], bool(row["enabled"]), int(row["credit_cost"]), float(row["unit_cost_cny_fen"]), float(row["quality_score"]), row["updated_at"]) for row in self.store._get_conn().execute("SELECT * FROM operation_endpoints ORDER BY code")]

    def content(self) -> list[ContentPlacement]:
        return [ContentPlacement(row["slot"], row["title"], row["href"], bool(row["enabled"]), row["updated_at"]) for row in self.store._get_conn().execute("SELECT * FROM operation_content ORDER BY slot")]

    def refunds(self) -> list[RefundRecord]:
        return [self._refund(row) for row in self.store._get_conn().execute("SELECT * FROM operation_refunds ORDER BY created_at DESC")]

    def _row(self, table: str, key: str, value: str) -> dict[str, Any]:
        row = self.store._get_conn().execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        return dict(row) if row else {}

    def _audit(self, conn, actor: str, object_type: str, object_id: str, action: str, reason: str, before: dict, after: dict) -> None:
        conn.execute("INSERT INTO operation_audit VALUES (?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, actor, object_type, object_id, action, reason, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), self._now()))

    @staticmethod
    def _validate_reason(reason: str) -> None:
        if not 5 <= len(reason.strip()) <= 500: raise ValueError("operation reason must contain 5 to 500 characters")

    @staticmethod
    def _refund(row) -> RefundRecord:
        return RefundRecord(row["id"], row["order_id"], row["user_id"], row["status"], row["reason"], row["created_at"])
