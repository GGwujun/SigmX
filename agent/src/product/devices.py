"""Device-code authorization service — Task 4.

Implements an RFC-8628-style device flow for linking the desktop client to a
cloud account (design §3.1):

    start()      → device_code + user_code (client shows the user_code)
    approve()    → user confirms in browser; binds the device to their account
    poll()       → client polls; on approval receives access + refresh tokens
    refresh()    → rotate refresh token, mint a new access token
    revoke()     → unlink a device; its refresh tokens die immediately

Refresh tokens are hashed at rest (design §9), rotated on every refresh, and
bounded by the plan's ``desktop.device_limit``.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Callable, NamedTuple, Optional

from src.product.tokens import create_product_token

logger = logging.getLogger(__name__)

_DEVICE_CODE_TTL_MINUTES = 10
_POLL_INTERVAL_SECONDS = 5
_REFRESH_TTL_DAYS = 30


def _now_default() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _mint_user_code() -> str:
    """Short, human-readable, unambiguous code (no 0/O/1/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(2))


def _mint_device_code() -> str:
    return secrets.token_urlsafe(32)


def _mint_refresh_token() -> str:
    return "rfr_" + secrets.token_urlsafe(40)


class PollStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXPIRED = "expired"


@dataclass
class DeviceStart:
    device_code: str
    user_code: str
    expires_at: str
    interval_seconds: int


@dataclass
class PollResult:
    status: PollStatus
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


@dataclass
class RefreshResult:
    status: str            # "ok" | "revoked"
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class DeviceLimitReached(Exception):
    """The user's plan does not allow another linked device."""


class DeviceService:
    def __init__(self, store, now: Callable[[], datetime] = _now_default) -> None:
        self.store = store
        self._now = now

    # ------------------------------------------------------------------ #
    # Device-code flow
    # ------------------------------------------------------------------ #

    def start(self, *, device_name: str, fingerprint_hash: str) -> DeviceStart:
        expires_at = (self._now() + timedelta(minutes=_DEVICE_CODE_TTL_MINUTES)).isoformat()
        device_code = _mint_device_code()
        user_code = _mint_user_code()
        with self.store.transaction() as conn:
            conn.execute(
                """
                INSERT INTO device_codes
                    (device_code, user_code, user_id, device_name, fingerprint_hash,
                     expires_at, interval_seconds, approved_at, consumed_at, created_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (device_code, user_code, device_name, fingerprint_hash,
                 expires_at, _POLL_INTERVAL_SECONDS, self._now().isoformat()),
            )
        return DeviceStart(
            device_code=device_code,
            user_code=user_code,
            expires_at=expires_at,
            interval_seconds=_POLL_INTERVAL_SECONDS,
        )

    def approve(self, *, user_id: str, user_code: str) -> None:
        """User confirms the device in-browser. Enforces the plan device limit."""
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM device_codes WHERE user_code = ?", (user_code,)
            ).fetchone()
            if row is None:
                raise ValueError("无效的用户码")
            if row["approved_at"] is not None:
                raise ValueError("该用户码已使用")
            if self._now() >= _fromiso(row["expires_at"]):
                raise ValueError("用户码已过期")

            limit = self._device_limit(conn, user_id)
            active = self._active_device_count(conn, user_id)
            if active >= limit:
                raise DeviceLimitReached(
                    f"已达设备上限 {limit}（用户 {user_id}）"
                )

            conn.execute(
                "UPDATE device_codes SET user_id = ?, approved_at = ? WHERE user_code = ?",
                (user_id, self._now().isoformat(), user_code),
            )

    def poll(self, *, device_code: str) -> PollResult:
        """Client polls for the outcome of its device-code grant."""
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM device_codes WHERE device_code = ?", (device_code,)
            ).fetchone()
            if row is None:
                return PollResult(status=PollStatus.EXPIRED)
            now = self._now()
            if now >= _fromiso(row["expires_at"]):
                return PollResult(status=PollStatus.EXPIRED)
            if row["consumed_at"] is not None:
                return PollResult(status=PollStatus.EXPIRED)  # one-time consumption
            if row["approved_at"] is None or row["user_id"] is None:
                return PollResult(status=PollStatus.PENDING)

            # Approved → mint tokens, register device, consume the grant.
            user_id = row["user_id"]
            device_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO devices (id, user_id, name, fingerprint_hash, created_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (device_id, user_id, row["device_name"], row["fingerprint_hash"], now.isoformat()),
            )
            plan_code, entitlements = self._plan_for_user(conn, user_id)
            access = create_product_token(
                user_id=user_id,
                device_id=device_id,
                plan_code=plan_code,
                entitlements=entitlements,
            )
            refresh_plaintext = _mint_refresh_token()
            refresh_hash = _hash_token(refresh_plaintext)
            conn.execute(
                """
                INSERT INTO refresh_tokens
                    (token_hash, user_id, device_id, rotated_to, revoked_at, expires_at, created_at)
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                """,
                (refresh_hash, user_id, device_id,
                 (now + timedelta(days=_REFRESH_TTL_DAYS)).isoformat(), now.isoformat()),
            )
            conn.execute(
                "UPDATE device_codes SET consumed_at = ? WHERE device_code = ?",
                (now.isoformat(), device_code),
            )
            return PollResult(status=PollStatus.APPROVED, access_token=access, refresh_token=refresh_plaintext)

    # ------------------------------------------------------------------ #
    # Refresh / revoke
    # ------------------------------------------------------------------ #

    def refresh(self, *, refresh_token: str) -> RefreshResult:
        """Rotate a refresh token, mint a new access token."""
        token_hash = _hash_token(refresh_token)
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row is None:
                return RefreshResult(status="revoked")
            if row["revoked_at"] is not None or row["rotated_to"] is not None:
                return RefreshResult(status="revoked")
            if row["expires_at"] and self._now() >= _fromiso(row["expires_at"]):
                return RefreshResult(status="revoked")

            new_refresh = _mint_refresh_token()
            new_hash = _hash_token(new_refresh)
            now = self._now()
            # Rotate: old token revoked + points to successor; new token issued.
            conn.execute(
                "UPDATE refresh_tokens SET revoked_at = ?, rotated_to = ? WHERE token_hash = ?",
                (now.isoformat(), new_hash, token_hash),
            )
            conn.execute(
                """
                INSERT INTO refresh_tokens
                    (token_hash, user_id, device_id, rotated_to, revoked_at, expires_at, created_at)
                VALUES (?, ?, ?, NULL, NULL, ?, ?)
                """,
                (new_hash, row["user_id"], row["device_id"],
                 (now + timedelta(days=_REFRESH_TTL_DAYS)).isoformat(), now.isoformat()),
            )
            plan_code, entitlements = self._plan_for_user(conn, row["user_id"])
            access = create_product_token(
                user_id=row["user_id"],
                device_id=row["device_id"],
                plan_code=plan_code,
                entitlements=entitlements,
            )
            return RefreshResult(status="ok", access_token=access, refresh_token=new_refresh)

    def revoke(self, *, user_id: str, device_id: str) -> None:
        """Unlink a device; its refresh tokens are revoked immediately."""
        with self.store.transaction() as conn:
            now = self._now().isoformat()
            conn.execute(
                "UPDATE devices SET revoked_at = ? WHERE id = ? AND user_id = ?",
                (now, device_id, user_id),
            )
            conn.execute(
                "UPDATE refresh_tokens SET revoked_at = ? WHERE device_id = ? AND revoked_at IS NULL",
                (now, device_id),
            )

    # ------------------------------------------------------------------ #
    # Internal: plan / device-limit lookups
    # ------------------------------------------------------------------ #

    def _device_limit(self, conn, user_id: str) -> int:
        _, entitlements = self._plan_for_user(conn, user_id)
        return int(entitlements.get("desktop.device_limit", 1))

    def _active_device_count(self, conn, user_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM devices WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,),
        ).fetchone()
        return int(row["c"])

    def _plan_for_user(self, conn, user_id: str) -> tuple[str, dict[str, Any]]:
        """Resolve the user's currently-active plan + entitlements."""
        import json

        row = conn.execute(
            """
            SELECT plan_code FROM entitlement_grants
            WHERE user_id = ? AND (valid_until IS NULL OR valid_until >= ?)
            ORDER BY valid_until DESC LIMIT 1
            """,
            (user_id, self._now().isoformat()),
        ).fetchone()
        plan_code = row["plan_code"] if row else "free"
        plan_row = conn.execute(
            "SELECT entitlements_json FROM plans WHERE code = ?", (plan_code,)
        ).fetchone()
        entitlements = json.loads(plan_row["entitlements_json"]) if plan_row else {}
        return plan_code, entitlements


def _fromiso(s: str) -> datetime:
    return datetime.fromisoformat(s)
