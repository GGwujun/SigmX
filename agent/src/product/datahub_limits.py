"""Transactional per-user Data Hub rate and concurrency limits."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.product.store import ProductStore


class RateLimitExceeded(Exception):
    pass


class ConcurrentLimitExceeded(Exception):
    pass


class DataHubLimitNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class LimitLease:
    lease_id: str
    rate_remaining: int


class DataHubLimitService:
    def __init__(self, store: ProductStore) -> None:
        self.store = store

    def acquire(
        self,
        user_id: str,
        credential_id: str,
        request_id: str,
        rate_limit: int,
        concurrent_limit: int,
        *,
        now: datetime | None = None,
    ) -> LimitLease:
        if rate_limit <= 0 or concurrent_limit <= 0:
            raise DataHubLimitNotConfigured("positive rate and concurrency limits are required")
        current = now or datetime.now(timezone.utc)
        minute = current.strftime("%Y-%m-%dT%H:%MZ")
        with self.store.transaction() as conn:
            conn.execute(
                "DELETE FROM datahub_concurrency_leases WHERE expires_at <= ?",
                (current.isoformat(),),
            )
            prior = conn.execute(
                "SELECT id, user_id, credential_id FROM datahub_concurrency_leases "
                "WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if prior is not None:
                if prior["user_id"] != user_id or prior["credential_id"] != credential_id:
                    raise ValueError("request_id belongs to another credential")
                bucket = conn.execute(
                    "SELECT consumed FROM datahub_rate_buckets WHERE user_id = ? AND minute = ?",
                    (user_id, minute),
                ).fetchone()
                consumed = int(bucket["consumed"]) if bucket else 0
                return LimitLease(prior["id"], max(0, rate_limit - consumed))

            active = conn.execute(
                "SELECT COUNT(*) FROM datahub_concurrency_leases WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
            if active >= concurrent_limit:
                raise ConcurrentLimitExceeded("concurrent request limit exceeded")
            bucket = conn.execute(
                "SELECT consumed FROM datahub_rate_buckets WHERE user_id = ? AND minute = ?",
                (user_id, minute),
            ).fetchone()
            consumed = int(bucket["consumed"]) if bucket else 0
            if consumed >= rate_limit:
                raise RateLimitExceeded("requests per minute limit exceeded")
            if bucket is None:
                conn.execute(
                    "INSERT INTO datahub_rate_buckets (user_id, minute, consumed) VALUES (?, ?, 1)",
                    (user_id, minute),
                )
            else:
                conn.execute(
                    "UPDATE datahub_rate_buckets SET consumed = consumed + 1 "
                    "WHERE user_id = ? AND minute = ?",
                    (user_id, minute),
                )
            lease_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO datahub_concurrency_leases "
                "(id, user_id, credential_id, request_id, expires_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    lease_id,
                    user_id,
                    credential_id,
                    request_id,
                    (current + timedelta(seconds=120)).isoformat(),
                    current.isoformat(),
                ),
            )
            return LimitLease(lease_id, rate_limit - consumed - 1)

    def release(self, lease_id: str) -> None:
        with self.store.transaction() as conn:
            conn.execute("DELETE FROM datahub_concurrency_leases WHERE id = ?", (lease_id,))
