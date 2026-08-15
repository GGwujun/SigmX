from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest

from src.product.datahub_limits import (
    ConcurrentLimitExceeded,
    DataHubLimitNotConfigured,
    DataHubLimitService,
    RateLimitExceeded,
)
from src.product.store import ProductStore


NOW = datetime(2026, 8, 15, 12, 34, 10, tzinfo=timezone.utc)


@pytest.fixture
def limiter(tmp_path: Path) -> DataHubLimitService:
    return DataHubLimitService(ProductStore(tmp_path / "product.db"))


def test_two_credentials_share_user_rate_limit(limiter: DataHubLimitService) -> None:
    first = limiter.acquire("u1", "key-a", "r1", 2, 10, now=NOW)
    second = limiter.acquire("u1", "key-b", "r2", 2, 10, now=NOW)
    assert first.rate_remaining == 1
    assert second.rate_remaining == 0
    with pytest.raises(RateLimitExceeded):
        limiter.acquire("u1", "key-a", "r3", 2, 10, now=NOW)


def test_users_have_independent_rate_buckets(limiter: DataHubLimitService) -> None:
    limiter.acquire("u1", "key-a", "r1", 1, 10, now=NOW)
    assert limiter.acquire("u2", "key-b", "r2", 1, 10, now=NOW).rate_remaining == 0


def test_concurrency_is_shared_and_release_is_idempotent(limiter: DataHubLimitService) -> None:
    lease = limiter.acquire("u1", "key-a", "r1", 10, 1, now=NOW)
    with pytest.raises(ConcurrentLimitExceeded):
        limiter.acquire("u1", "key-b", "r2", 10, 1, now=NOW)
    limiter.release(lease.lease_id)
    limiter.release(lease.lease_id)
    assert limiter.acquire("u1", "key-b", "r3", 10, 1, now=NOW).lease_id


def test_expired_leases_are_cleaned_before_count(limiter: DataHubLimitService) -> None:
    limiter.acquire("u1", "key-a", "r1", 10, 1, now=NOW)
    later = NOW + timedelta(seconds=121)
    assert limiter.acquire("u1", "key-b", "r2", 10, 1, now=later).lease_id


def test_non_positive_plan_limits_fail_closed(limiter: DataHubLimitService) -> None:
    with pytest.raises(DataHubLimitNotConfigured):
        limiter.acquire("u1", "key", "r1", 0, 1, now=NOW)
    with pytest.raises(DataHubLimitNotConfigured):
        limiter.acquire("u1", "key", "r2", 1, 0, now=NOW)


def test_request_id_replay_returns_same_lease(limiter: DataHubLimitService) -> None:
    first = limiter.acquire("u1", "key", "r1", 10, 2, now=NOW)
    replay = limiter.acquire("u1", "key", "r1", 10, 2, now=NOW)
    assert replay == first


def test_two_connections_cannot_exceed_concurrency(tmp_path: Path) -> None:
    db = tmp_path / "shared.db"
    services = [DataHubLimitService(ProductStore(db)), DataHubLimitService(ProductStore(db))]
    gate = Barrier(2)

    def attempt(index: int) -> str:
        gate.wait()
        try:
            services[index].acquire("u1", f"key-{index}", f"r{index}", 10, 1, now=NOW)
            return "acquired"
        except ConcurrentLimitExceeded:
            return "full"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, (0, 1)))
    assert sorted(outcomes) == ["acquired", "full"]
