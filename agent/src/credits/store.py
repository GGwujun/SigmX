"""SQLite-backed credits store: balance + transactions + redeem codes.

Database: ``~/.vibe-trading/credits.db`` (WAL, check_same_thread=False — same
pattern as users.db). All mutations that touch balance run inside a single
transaction so balance + transaction log stay consistent, and consume uses a
guarded ``UPDATE ... WHERE balance >= ?`` to atomically prevent overdraw under
concurrency.

Transaction ``ref`` is overloaded: the run_id for consume/refund, the code for
redeem. Refund is idempotent: ``refund_if_not_already`` checks whether a refund
with the same ref already exists before applying.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.credits.constants import TX_ADMIN, TX_CONSUME, TX_REDEEM, TX_REFUND

logger = logging.getLogger(__name__)

_DB_PATH = Path.home() / ".vibe-trading" / "credits.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CreditStore:
    """Thread-safe credits store."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _conn_locked(self) -> sqlite3.Connection:
        # Caller must hold self._lock.
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
            conn = self._conn_locked()
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS credits_balance (
                    user_id TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS credit_transactions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    delta INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    ref TEXT NOT NULL DEFAULT '',
                    balance_after INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tx_user_time
                    ON credit_transactions(user_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS redeem_codes (
                    code TEXT PRIMARY KEY,
                    credits INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'unused',
                    redeemed_by TEXT,
                    redeemed_at TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );
                """
            )
            conn.commit()

    # ------------------------------------------------------------------ balance

    def get_balance(self, user_id: str) -> int:
        with self._lock:
            row = self._conn_locked().execute(
                "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
            ).fetchone()
        return int(row["balance"]) if row else 0

    def _ensure_balance_row(self, conn: sqlite3.Connection, user_id: str) -> int:
        """Insert a 0-balance row if missing; return current balance (within tx)."""
        row = conn.execute(
            "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO credits_balance (user_id, balance, updated_at) VALUES (?, 0, ?)",
                (user_id, _now_iso()),
            )
            return 0
        return int(row["balance"])

    def _record_tx(
        self, conn: sqlite3.Connection, user_id: str, delta: int, tx_type: str,
        ref: str, balance_after: int, note: str,
    ) -> None:
        conn.execute(
            "INSERT INTO credit_transactions (id, user_id, delta, type, ref, balance_after, note, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, delta, tx_type, ref, balance_after, note, _now_iso()),
        )

    def add_credits(
        self, user_id: str, delta: int, tx_type: str, ref: str = "", note: str = "",
    ) -> int:
        """Add (delta>0) credits and log a transaction. Returns new balance."""
        if delta == 0:
            return self.get_balance(user_id)
        with self._lock:
            conn = self._conn_locked()
            self._ensure_balance_row(conn, user_id)
            conn.execute(
                "UPDATE credits_balance SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
                (delta, _now_iso(), user_id),
            )
            row = conn.execute(
                "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
            ).fetchone()
            new_balance = int(row["balance"])
            self._record_tx(conn, user_id, delta, tx_type, ref, new_balance, note)
            conn.commit()
        return new_balance

    def consume(self, user_id: str, amount: int, ref: str, note: str) -> bool:
        """Atomically deduct ``amount`` if balance is sufficient.

        Uses ``UPDATE ... WHERE balance >= ?`` so two concurrent consume calls
        cannot both succeed (one will affect 0 rows). Returns True on success,
        False if insufficient balance.
        """
        if amount <= 0:
            return True
        with self._lock:
            conn = self._conn_locked()
            self._ensure_balance_row(conn, user_id)
            cur = conn.execute(
                "UPDATE credits_balance SET balance = balance - ?, updated_at = ? "
                "WHERE user_id = ? AND balance >= ?",
                (amount, _now_iso(), user_id, amount),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return False  # insufficient balance
            row = conn.execute(
                "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
            ).fetchone()
            new_balance = int(row["balance"])
            self._record_tx(conn, user_id, -amount, TX_CONSUME, ref, new_balance, note)
            conn.commit()
        return True

    def refund(self, user_id: str, amount: int, ref: str, note: str) -> None:
        """Return credits (analysis failed). Idempotent per ref."""
        if amount <= 0:
            return
        with self._lock:
            conn = self._conn_locked()
            # Idempotency: skip if a refund with this ref already exists.
            existing = conn.execute(
                "SELECT 1 FROM credit_transactions WHERE user_id = ? AND type = ? AND ref = ?",
                (user_id, TX_REFUND, ref),
            ).fetchone()
            if existing:
                return
            self._ensure_balance_row(conn, user_id)
            conn.execute(
                "UPDATE credits_balance SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
                (amount, _now_iso(), user_id),
            )
            row = conn.execute(
                "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
            ).fetchone()
            new_balance = int(row["balance"])
            self._record_tx(conn, user_id, amount, TX_REFUND, ref, new_balance, note)
            conn.commit()

    # ------------------------------------------------------------------ transactions

    def list_transactions(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn_locked().execute(
                "SELECT * FROM credit_transactions WHERE user_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, max(1, min(limit, 500))),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ redeem codes

    def redeem(self, user_id: str, code: str) -> tuple[bool, int, str]:
        """Redeem a code. Returns (ok, credits_granted, message)."""
        code = code.strip()
        if not code:
            return False, 0, "兑换码不能为空"
        with self._lock:
            conn = self._conn_locked()
            row = conn.execute(
                "SELECT * FROM redeem_codes WHERE code = ?", (code,)
            ).fetchone()
            if row is None:
                return False, 0, "兑换码不存在"
            if row["status"] != "unused":
                return False, 0, "兑换码已被使用或失效"
            # Expiry check
            exp = row["expires_at"]
            if exp:
                try:
                    if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                        return False, 0, "兑换码已过期"
                except ValueError:
                    pass
            credits = int(row["credits"])
            # Mark code used + grant credits atomically.
            conn.execute(
                "UPDATE redeem_codes SET status = 'used', redeemed_by = ?, redeemed_at = ? WHERE code = ?",
                (user_id, _now_iso(), code),
            )
            self._ensure_balance_row(conn, user_id)
            conn.execute(
                "UPDATE credits_balance SET balance = balance + ?, updated_at = ? WHERE user_id = ?",
                (credits, _now_iso(), user_id),
            )
            brow = conn.execute(
                "SELECT balance FROM credits_balance WHERE user_id = ?", (user_id,)
            ).fetchone()
            new_balance = int(brow["balance"])
            self._record_tx(conn, user_id, credits, TX_REDEEM, code, new_balance, f"兑换码 {code}")
            conn.commit()
        return True, credits, f"兑换成功，获得 {credits} 积分"

    def create_redeem_code(
        self, code: str, credits: int, expires_at: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            conn = self._conn_locked()
            conn.execute(
                "INSERT INTO redeem_codes (code, credits, status, created_at, expires_at) "
                "VALUES (?, ?, 'unused', ?, ?)",
                (code, credits, _now_iso(), expires_at),
            )
            conn.commit()
        return {"code": code, "credits": credits, "expires_at": expires_at}

    def list_codes(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn_locked().execute(
                "SELECT * FROM redeem_codes ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
