"""Product-domain SQLite store — Task 1 foundation.

Owns ``product.db``: schema, migrations, the transaction boundary, and the
server-driven plan catalog seed. Later tasks (credits/activation/devices/tokens)
consume ``ProductStore.transaction()``, ``list_plans()``, ``get_plan()`` and the
DTOs in :mod:`src.product.models`.

Concurrency follows the same pattern as :class:`src.auth.store.UserStore`: WAL
mode, a single shared connection, and a write lock. FastAPI runs uvicorn workers
in threads by default, so one process-local connection with a lock is sufficient.

The full schema is created up front even though Task 1 only reads ``plans`` —
this keeps migrations additive so later tasks don't need to evolve the schema.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from src.product.catalog import DEFAULT_CATALOG, to_seed_row

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".vibe-trading" / "product.db"

_SCHEMA_VERSION = 2

_OLD_DATAHUB_ENTITLEMENT_KEYS = {
    "datahub.basic",
    "datahub.featured",
    "datahub.daily_quota",
    "datahub.external_api",
}


class ProductStore:
    """Thread-safe SQLite store for the product domain.

    Public surface (Task 1):
        - ``list_plans()`` / ``get_plan(code)``
        - ``transaction()`` — the single write boundary used by later tasks.
    """

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------ #
    # Public read API (Task 1 contract)
    # ------------------------------------------------------------------ #

    def list_plans(self) -> list[dict[str, Any]]:
        """Return all catalog plans sorted by ``sort_order`` (server-driven)."""
        rows = self._get_conn().execute(
            "SELECT * FROM plans ORDER BY sort_order ASC, code ASC"
        ).fetchall()
        return [self._row_to_plan(r) for r in rows]

    def get_plan(self, code: str) -> dict[str, Any] | None:
        """Return one plan by code, or ``None`` if unknown."""
        row = self._get_conn().execute(
            "SELECT * FROM plans WHERE code = ?", (code,)
        ).fetchone()
        return self._row_to_plan(row) if row else None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection inside a serialized write transaction.

        Later tasks wrap grants/reservations/activations in this context so the
        whole business operation commits atomically or rolls back together.
        Uses ``BEGIN IMMEDIATE`` to fail fast on a competing writer.
        """
        conn = self._get_conn()
        self._lock.acquire()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._lock.release()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_conn(self) -> sqlite3.Connection:
        """Read path — lazily opens the shared WAL connection."""
        if self._conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass  # WAL not available (e.g. :memory:) — degrade gracefully.
            try:
                conn.execute("PRAGMA foreign_keys=ON")
            except sqlite3.OperationalError:
                pass
            self._conn = conn
        return self._conn

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "code": row["code"],
            "name_zh": row["name_zh"],
            "price_cny_fen": row["price_cny_fen"],
            "billing_period": row["billing_period"],
            "monthly_credits": row["monthly_credits"],
            "welcome_credits": row["welcome_credits"],
            "description": row["description"],
            "entitlements": json.loads(row["entitlements_json"]),
            "sort_order": row["sort_order"],
        }

    def _init_db(self) -> None:
        conn = self._get_conn()
        with self._lock:
            self._create_tables(conn)
            self._seed_catalog(conn)
            self._migrate_v2_datahub_entitlements(conn)
            self._stamp_version(conn)
            conn.commit()

    @staticmethod
    def _create_tables(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS product_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            -- Server-driven catalog. Prices/quota snapshot at order time
            -- (design §4.1); this row is the live catalog.
            CREATE TABLE IF NOT EXISTS plans (
                code TEXT PRIMARY KEY,
                name_zh TEXT NOT NULL,
                price_cny_fen INTEGER NOT NULL,
                billing_period TEXT NOT NULL,
                monthly_credits INTEGER NOT NULL DEFAULT 0,
                welcome_credits INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                entitlements_json TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            -- Activation/payment orders (design §5). Stores the purchased
            -- price+entitlement snapshot so catalog changes never rewrite history.
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                plan_code TEXT NOT NULL,
                status TEXT NOT NULL,
                channel TEXT NOT NULL,
                price_cny_fen INTEGER NOT NULL,
                entitlements_snapshot_json TEXT NOT NULL,
                months INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT,
                provider_payment_id TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                UNIQUE(user_id, idempotency_key)
            );

            -- Active membership windows granted from paid orders.
            CREATE TABLE IF NOT EXISTS entitlement_grants (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                plan_code TEXT NOT NULL,
                order_id TEXT,
                valid_from TEXT NOT NULL,
                valid_until TEXT,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Credit lots (expiring monthly + permanent). design §4.2.
            CREATE TABLE IF NOT EXISTS credit_lots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                amount_total INTEGER NOT NULL,
                amount_remaining INTEGER NOT NULL,
                source TEXT NOT NULL,
                expires_at TEXT,
                idempotency_key TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, idempotency_key)
            );

            -- Immutable ledger — every grant/reserve/settle/refund writes here.
            CREATE TABLE IF NOT EXISTS credit_ledger (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                lot_id TEXT,
                delta INTEGER NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT,
                created_at TEXT NOT NULL
            );

            -- Credit reservations: a metered task pre-deducts credits, then
            -- either settles (consume) or refunds. Stores the per-lot allocation
            -- so refund restores exactly those credits once (design §4.2, §9).
            CREATE TABLE IF NOT EXISTS credit_reservations (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                amount INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, idempotency_key)
            );

            -- Activation codes (hashed). Plaintext shown once at creation.
            CREATE TABLE IF NOT EXISTS activation_codes (
                code_hash TEXT PRIMARY KEY,
                code_type TEXT NOT NULL,
                plan_code TEXT,
                months INTEGER NOT NULL DEFAULT 0,
                credits INTEGER NOT NULL DEFAULT 0,
                used_by TEXT,
                used_at TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                UNIQUE(used_by, code_hash)
            );

            -- Linked desktop devices (design §3.1, Task 4).
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                fingerprint_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked_at TEXT
            );

            -- In-flight device-code authorization grants.
            CREATE TABLE IF NOT EXISTS device_codes (
                device_code TEXT PRIMARY KEY,
                user_code TEXT NOT NULL,
                user_id TEXT,
                device_name TEXT NOT NULL,
                fingerprint_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL DEFAULT 5,
                approved_at TEXT,
                consumed_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_code)
            );

            -- Hashed refresh tokens, rotated on each refresh, revocable.
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                rotated_to TEXT,
                revoked_at TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );

            -- Daily Data Hub / cloud-AI usage for quota enforcement.
            CREATE TABLE IF NOT EXISTS usage_daily (
                user_id TEXT NOT NULL,
                metric TEXT NOT NULL,
                day TEXT NOT NULL,
                consumed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, metric, day)
            );

            CREATE TABLE IF NOT EXISTS data_credit_lots (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                amount_total INTEGER NOT NULL CHECK (amount_total > 0),
                amount_remaining INTEGER NOT NULL CHECK (amount_remaining >= 0),
                source TEXT NOT NULL,
                expires_at TEXT,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(owner_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS data_credit_reservations (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                endpoint_code TEXT NOT NULL,
                amount_authorized INTEGER NOT NULL CHECK (amount_authorized > 0),
                amount_settled INTEGER,
                idempotency_key TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('authorized', 'settled', 'released')),
                created_at TEXT NOT NULL,
                settled_at TEXT,
                UNIQUE(owner_id, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS data_credit_allocations (
                reservation_id TEXT NOT NULL,
                lot_id TEXT NOT NULL,
                amount INTEGER NOT NULL CHECK (amount > 0),
                PRIMARY KEY (reservation_id, lot_id),
                FOREIGN KEY (reservation_id) REFERENCES data_credit_reservations(id),
                FOREIGN KEY (lot_id) REFERENCES data_credit_lots(id)
            );

            CREATE TABLE IF NOT EXISTS data_credit_ledger (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                lot_id TEXT,
                reservation_id TEXT,
                delta INTEGER NOT NULL,
                operation TEXT NOT NULL CHECK (operation IN ('grant', 'authorize', 'settle', 'release')),
                idempotency_key TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS datahub_endpoint_catalog (
                endpoint_code TEXT NOT NULL,
                catalog_version INTEGER NOT NULL,
                http_method TEXT NOT NULL,
                path_pattern TEXT NOT NULL,
                dataset_group TEXT NOT NULL,
                pricing_mode TEXT NOT NULL CHECK (pricing_mode IN ('free', 'fixed', 'per_unit')),
                base_cost INTEGER NOT NULL CHECK (base_cost >= 0),
                unit_name TEXT,
                unit_size INTEGER,
                unit_cost INTEGER,
                max_cost INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                PRIMARY KEY (endpoint_code, catalog_version),
                UNIQUE (http_method, path_pattern, catalog_version)
            );

            -- Operator audit log (design §9).
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                reason TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

    @staticmethod
    def _seed_catalog(conn: sqlite3.Connection) -> None:
        """Seed the four canonical plans idempotently.

        Existing rows are replaced so a catalog value update (operator edits a
        quota) is not silently clobbered on the next open: re-seeding only
        happens for codes that are absent. The default catalog is the seed of
        last resort — operators edit ``product.db`` directly to change live
        values, and this method only guarantees the four base plans exist.
        """
        existing = {
            row[0] for row in conn.execute("SELECT code FROM plans").fetchall()
        }
        for seed in DEFAULT_CATALOG:
            if seed["code"] in existing:
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO plans (
                    code, name_zh, price_cny_fen, billing_period,
                    monthly_credits, welcome_credits, description,
                    entitlements_json, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                to_seed_row(seed),
            )

    @staticmethod
    def _migrate_v2_datahub_entitlements(conn: sqlite3.Connection) -> None:
        if conn.execute(
            "SELECT 1 FROM product_migrations WHERE version = 2"
        ).fetchone() is not None:
            return
        for seed in DEFAULT_CATALOG:
            row = conn.execute(
                "SELECT entitlements_json FROM plans WHERE code = ?", (seed["code"],)
            ).fetchone()
            if row is None:
                continue
            current = json.loads(row["entitlements_json"])
            for key in _OLD_DATAHUB_ENTITLEMENT_KEYS:
                current.pop(key, None)
            current.update(
                {key: value for key, value in seed["entitlements"].items() if key.startswith("datahub.")}
            )
            conn.execute(
                "UPDATE plans SET entitlements_json = ? WHERE code = ?",
                (json.dumps(current, sort_keys=True, ensure_ascii=False), seed["code"]),
            )

    @staticmethod
    def _stamp_version(conn: sqlite3.Connection) -> None:
        from datetime import datetime, timezone

        conn.execute(
            "INSERT OR IGNORE INTO product_migrations (version, applied_at) VALUES (?, ?)",
            (_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
