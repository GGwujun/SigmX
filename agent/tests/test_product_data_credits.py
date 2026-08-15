from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from src.product.credits import CreditLedger
from src.product.data_credits import (
    DataCreditLedger,
    InsufficientDataCredits,
    InvalidDataCreditSettlement,
    grant_monthly_data_credits,
)
from src.product.store import ProductStore


@pytest.fixture
def store(tmp_path: Path) -> ProductStore:
    return ProductStore(tmp_path / "product.db")


def test_data_grant_does_not_change_research_balance(store: ProductStore) -> None:
    research = CreditLedger(store)
    data = DataCreditLedger(store)
    research.grant("u1", 50, source="research", expires_at=None, idempotency_key="r1")
    data.grant("u1", 1_000, source="data_purchase", expires_at=None, idempotency_key="d1")
    assert research.balance("u1").available == 50
    assert data.balance("u1").available == 1_000


def test_data_grant_is_idempotent(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    first = ledger.grant("u1", 100, source="monthly", expires_at=None, idempotency_key="d1")
    second = ledger.grant("u1", 100, source="monthly", expires_at=None, idempotency_key="d1")
    assert second.lot_id == first.lot_id
    assert second.idempotent_replay is True
    assert ledger.balance("u1").available == 100


def test_data_balance_excludes_expired_and_counts_expiring_soon(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    now = datetime.now(timezone.utc)
    ledger.grant("u1", 20, source="expired", expires_at=(now - timedelta(days=1)).isoformat(), idempotency_key="old")
    ledger.grant("u1", 30, source="soon", expires_at=(now + timedelta(days=2)).isoformat(), idempotency_key="soon")
    ledger.grant("u1", 50, source="permanent", expires_at=None, idempotency_key="permanent")
    balance = ledger.balance("u1")
    assert balance.available == 80
    assert balance.expiring_soon == 30


def test_data_lots_and_entries_are_owner_isolated(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    ledger.grant("u1", 10, source="purchase", expires_at=None, idempotency_key="u1-lot")
    ledger.grant("u2", 20, source="purchase", expires_at=None, idempotency_key="u2-lot")
    assert [row["idempotency_key"] for row in ledger.list_lots("u1")] == ["u1-lot"]
    assert {row["owner_id"] for row in ledger.list_entries("u1")} == {"u1"}


def test_data_grant_rejects_non_positive_amount(store: ProductStore) -> None:
    with pytest.raises(ValueError, match="positive"):
        DataCreditLedger(store).grant("u1", 0, source="bad", expires_at=None, idempotency_key="bad")


def test_monthly_data_credit_grant_uses_plan_value_and_next_month_expiry(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    first = grant_monthly_data_credits(ledger, "u1", "desktop_pro", date(2026, 8, 15))
    second = grant_monthly_data_credits(ledger, "u1", "desktop_pro", date(2026, 8, 28))
    assert first is not None
    assert second is not None and second.idempotent_replay is True
    assert ledger.balance("u1").available == 10_000
    lot = ledger.list_lots("u1")[0]
    assert lot["idempotency_key"] == "data-plan-month:u1:desktop_pro:2026-08"
    assert lot["expires_at"] == "2026-09-01T00:00:00+00:00"


def test_monthly_data_credit_grant_rejects_removed_enterprise_plan(store: ProductStore) -> None:
    with pytest.raises(ValueError, match="unknown plan enterprise"):
        grant_monthly_data_credits(
            DataCreditLedger(store), "u1", "enterprise", date(2026, 8, 15)
        )


def test_authorize_consumes_expiring_lots_first_and_is_idempotent(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    first_lot = ledger.grant("u1", 30, source="monthly", expires_at=soon, idempotency_key="soon")
    second_lot = ledger.grant("u1", 50, source="purchase", expires_at=None, idempotency_key="forever")

    first = ledger.authorize("u1", "daily-bars", 40, "request-1")
    replay = ledger.authorize("u1", "daily-bars", 40, "request-1")

    assert first.allocations == ((first_lot.lot_id, 30), (second_lot.lot_id, 10))
    assert replay == first
    assert ledger.balance("u1").available == 40


def test_authorize_is_atomic_when_balance_is_insufficient(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    ledger.grant("u1", 10, source="purchase", expires_at=None, idempotency_key="lot")

    with pytest.raises(InsufficientDataCredits):
        ledger.authorize("u1", "daily-bars", 11, "request-1")

    assert ledger.balance("u1").available == 10
    assert not [entry for entry in ledger.list_entries("u1") if entry["operation"] == "authorize"]


def test_settle_releases_unused_allocations_back_to_original_lots(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    soon_lot = ledger.grant("u1", 30, source="monthly", expires_at=soon, idempotency_key="soon")
    permanent_lot = ledger.grant("u1", 50, source="purchase", expires_at=None, idempotency_key="forever")
    authorization = ledger.authorize("u1", "daily-bars", 40, "request-1")

    settled = ledger.settle(authorization.reservation_id, 25, "settle-1")
    replay = ledger.settle(authorization.reservation_id, 25, "settle-1")

    assert settled.amount_authorized == 40
    assert settled.amount_settled == 25
    assert settled.amount_released == 15
    assert settled.status == "settled"
    assert replay == settled
    lots = {lot["id"]: lot["amount_remaining"] for lot in ledger.list_lots("u1")}
    assert lots[soon_lot.lot_id] == 5
    assert lots[permanent_lot.lot_id] == 50
    assert ledger.balance("u1").available == 55


def test_release_returns_entire_authorization_and_is_idempotent(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    ledger.grant("u1", 50, source="purchase", expires_at=None, idempotency_key="lot")
    authorization = ledger.authorize("u1", "daily-bars", 40, "request-1")

    released = ledger.release(authorization.reservation_id, "release-1")
    replay = ledger.release(authorization.reservation_id, "release-1")

    assert released.amount_settled == 0
    assert released.amount_released == 40
    assert released.status == "released"
    assert replay == released
    assert ledger.balance("u1").available == 50


def test_settlement_rejects_overcharge_and_conflicting_replay(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    ledger.grant("u1", 50, source="purchase", expires_at=None, idempotency_key="lot")
    authorization = ledger.authorize("u1", "daily-bars", 40, "request-1")

    with pytest.raises(InvalidDataCreditSettlement):
        ledger.settle(authorization.reservation_id, 41, "settle-over")
    ledger.settle(authorization.reservation_id, 20, "settle-1")
    with pytest.raises(InvalidDataCreditSettlement):
        ledger.settle(authorization.reservation_id, 19, "settle-2")


def test_concurrent_authorizations_cannot_overdraw_same_database(tmp_path: Path) -> None:
    db_path = tmp_path / "shared.db"
    first = DataCreditLedger(ProductStore(db_path))
    second = DataCreditLedger(ProductStore(db_path))
    first.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="lot")
    gate = Barrier(2)

    def attempt(ledger: DataCreditLedger, key: str) -> str:
        gate.wait()
        try:
            ledger.authorize("u1", "daily-bars", 80, key)
            return "authorized"
        except InsufficientDataCredits:
            return "insufficient"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda args: attempt(*args), ((first, "r1"), (second, "r2"))))

    assert sorted(outcomes) == ["authorized", "insufficient"]
    assert first.balance("u1").available == 20

