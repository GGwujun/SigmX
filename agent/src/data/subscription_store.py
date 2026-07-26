"""Subscription store for Data Hub API keys and rate limiting.

Database: ``~/.vibe-trading/subscriptions.db`` (WAL mode, thread-safe).

Schema::

    subscriptions(
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL,
      api_key_hash TEXT NOT NULL,
      api_key_prefix TEXT NOT NULL,   -- first 8 chars for UI display
      tier TEXT NOT NULL DEFAULT 'free',  -- free | basic | pro
      quota_daily INTEGER NOT NULL DEFAULT 100,
      created_at TEXT NOT NULL,
      expires_at TEXT,                -- NULL = never expires
      active INTEGER NOT NULL DEFAULT 1
    )

    api_usage(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscription_id TEXT NOT NULL REFERENCES subscriptions(id),
      date TEXT NOT NULL,             -- YYYY-MM-DD
      count INTEGER NOT NULL DEFAULT 0,
      UNIQUE(subscription_id, date)
    )

Usage::

    store = SubscriptionStore()
    sub = store.create("user@example.com", tier="pro", quota_daily=10000)
    # Returns the plaintext API key (only shown once).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".vibe-trading" / "subscriptions.db"

# Tier config
_TIERS = {
    "free":    {"quota": 100,   "label": "Free"},
    "basic":   {"quota": 1000,  "label": "Basic"},
    "pro":     {"quota": 10000, "label": "Pro"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SubscriptionStore:
    """Thread-safe SQLite store for Data Hub subscriptions."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass
        return self._conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL,
                    api_key_prefix TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'free',
                    quota_daily INTEGER NOT NULL DEFAULT 100,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(subscription_id, date)
                )
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        email: str,
        tier: str = "free",
        quota_daily: int | None = None,
        days: int = 365,
    ) -> dict[str, Any]:
        """Create a subscription and return it with the PLAINTEXT api_key.

        The plaintext key is returned ONLY here — we store a SHA-256 hash.
        """
        tier_config = _TIERS.get(tier, _TIERS["free"])
        quota = quota_daily if quota_daily is not None else tier_config["quota"]

        api_key = "sx_" + secrets.token_hex(24)  # "sx_" prefix + 48 hex chars
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_prefix = api_key[:10]  # "sx_" + first 7 hex chars

        sub_id = uuid.uuid4().hex
        created_at = _now_iso()
        # days <= 0 means never expires (expires_at NULL). Otherwise expire
        # `days` days from now. (The prior nested-ternary here set expires_at
        # to the creation timestamp for days=0, making keys expire instantly.)
        if days > 0:
            from datetime import timedelta
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
        else:
            expires_at = None

        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO subscriptions
                    (id, email, api_key_hash, api_key_prefix, tier, quota_daily, created_at, expires_at, active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (sub_id, email.strip().lower(), api_key_hash, api_key_prefix,
                 tier, quota, created_at, expires_at),
            )
            conn.commit()

        logger.info("Created subscription %s for %s (tier=%s)", sub_id, email, tier)
        return {
            "id": sub_id,
            "email": email,
            "api_key": api_key,  # plaintext — show once!
            "api_key_prefix": api_key_prefix,
            "tier": tier,
            "quota_daily": quota,
            "created_at": created_at,
            "expires_at": expires_at,
            "active": True,
        }

    def validate_api_key(self, api_key: str) -> dict[str, Any] | None:
        """Check an API key and return the subscription if valid+active. Returns None if invalid."""
        if not api_key or not api_key.startswith("sx_"):
            return None

        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE api_key_hash = ?",
                (api_key_hash,),
            ).fetchone()

        if not row:
            return None

        sub = dict(row)
        sub["is_admin"] = bool(sub.get("is_admin", 0))

        if not sub["active"]:
            return None

        if sub["expires_at"] and sub["expires_at"] < _now_iso():
            # Auto-deactivate expired subs.
            self._deactivate(sub["id"])
            return None

        return {
            "id": sub["id"],
            "email": sub["email"],
            "tier": sub["tier"],
            "quota_daily": sub["quota_daily"],
            "expires_at": sub["expires_at"],
        }

    def check_quota(self, subscription_id: str) -> tuple[bool, int, int]:
        """Check if the subscription has remaining daily quota.

        Returns: (allowed, used_today, quota_daily).
        """
        today = _today_str()
        with self._lock:
            conn = self._get_conn()
            sub = conn.execute(
                "SELECT quota_daily FROM subscriptions WHERE id = ? AND active = 1",
                (subscription_id,),
            ).fetchone()
            if not sub:
                return False, 0, 0

            quota = sub["quota_daily"]
            row = conn.execute(
                "SELECT count FROM api_usage WHERE subscription_id = ? AND date = ?",
                (subscription_id, today),
            ).fetchone()
            used = row["count"] if row else 0

        return used < quota, used, quota

    def acquire_quota(self, subscription_id: str) -> bool:
        """Atomically reserve one request against today's daily quota.

        Replaces the check-then-record (check_quota + record_usage) pair, which
        was a TOCTOU race — concurrent requests could all pass the check before
        any incremented. This single statement only increments when the current
        count is still below the subscription's quota; rowcount==0 means the
        quota is exhausted.

        Returns True if a slot was reserved, False if the quota is exhausted.
        """
        today = _today_str()
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                """
                INSERT INTO api_usage (subscription_id, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(subscription_id, date)
                DO UPDATE SET count = count + 1
                WHERE (SELECT quota_daily FROM subscriptions
                       WHERE id = excluded.subscription_id) > api_usage.count
                """,
                (subscription_id, today),
            )
            conn.commit()
            return cur.rowcount > 0

    def record_usage(self, subscription_id: str) -> None:
        """Increment today's usage counter for a subscription."""
        today = _today_str()
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                """
                INSERT INTO api_usage (subscription_id, date, count)
                VALUES (?, ?, 1)
                ON CONFLICT(subscription_id, date)
                DO UPDATE SET count = count + 1
                """,
                (subscription_id, today),
            )
            conn.commit()

    def _deactivate(self, subscription_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            conn.execute("UPDATE subscriptions SET active = 0 WHERE id = ?", (subscription_id,))
            conn.commit()

    # ------------------------------------------------------------------
    # Admin queries
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        """List all subscriptions (admin)."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT id, email, api_key_prefix, tier, quota_daily, created_at, expires_at, active "
                "FROM subscriptions ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_usage(self, subscription_id: str, days: int = 30) -> list[dict[str, Any]]:
        """Return daily usage for a subscription."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT date, count FROM api_usage WHERE subscription_id = ? "
                "ORDER BY date DESC LIMIT ?",
                (subscription_id, days),
            ).fetchall()
        return [dict(r) for r in rows]

    def revoke(self, subscription_id: str) -> bool:
        """Revoke (deactivate) a subscription. Returns True if a row was updated."""
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "UPDATE subscriptions SET active = 0 WHERE id = ?",
                (subscription_id,),
            )
            conn.commit()
            return cur.rowcount > 0


# Singleton — reused across requests.
_store: SubscriptionStore | None = None


def get_subscription_store() -> SubscriptionStore:
    global _store
    if _store is None:
        _store = SubscriptionStore()
    return _store
