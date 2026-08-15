from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger, grant_monthly_data_credits
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
    first = grant_monthly_data_credits(ledger, "u1", "advanced", date(2026, 8, 15))
    second = grant_monthly_data_credits(ledger, "u1", "advanced", date(2026, 8, 28))
    assert first is not None
    assert second is not None and second.idempotent_replay is True
    assert ledger.balance("u1").available == 30_000
    lot = ledger.list_lots("u1")[0]
    assert lot["idempotency_key"] == "data-plan-month:u1:advanced:2026-08"
    assert lot["expires_at"] == "2026-09-01T00:00:00+00:00"


def test_monthly_data_credit_grant_skips_zero_credit_plan(store: ProductStore) -> None:
    assert grant_monthly_data_credits(
        DataCreditLedger(store), "org1", "enterprise", date(2026, 8, 15)
    ) is None
