"""Tests for the product credit ledger — Task 2 of the product-closure plan.

The ledger is the authoritative credits source for the product closure: expiring
monthly lots + permanent lots, an immutable ledger, and idempotent grant /
reserve / settle / refund. Design §4.2 defines the rules these encode.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.product.credits import CreditLedger
from src.product.store import ProductStore


def _month_end() -> str:
    """End of the current natural month — monthly lots expire here (design §4.2)."""
    now = datetime.now(timezone.utc)
    # Last second of the current month.
    if now.month == 12:
        end = now.replace(year=now.year + 1, month=1, day=1) - timedelta(seconds=1)
    else:
        end = now.replace(month=now.month + 1, day=1) - timedelta(seconds=1)
    return end.isoformat()


@pytest.fixture
def ledger(tmp_path: Path) -> CreditLedger:
    store = ProductStore(tmp_path / "product.db")
    return CreditLedger(store, now=lambda: datetime.now(timezone.utc).isoformat())


def test_reserve_uses_expiring_lot_before_permanent(ledger: CreditLedger) -> None:
    """Expiring (monthly) credits are consumed before permanent credits (§4.2)."""
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")
    ledger.grant("u1", 30, source="monthly", expires_at=_month_end(), idempotency_key="m1")

    reservation = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")

    # The 30 expiring credits go first, then 20 of the permanent 100.
    assert dict(reservation.allocations) == {"m1": 30, "p1": 20}
    assert ledger.balance("u1").available == 80  # 130 granted − 50 reserved


def test_balance_excludes_expired_lots_without_deleting_history(ledger: CreditLedger) -> None:
    """An expired lot contributes 0 to availability but its ledger rows remain."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ledger.grant("u1", 50, source="monthly", expires_at=past, idempotency_key="m-old")
    ledger.grant("u1", 20, source="purchase", expires_at=None, idempotency_key="p1")

    bal = ledger.balance("u1")
    assert bal.available == 20           # the 50 expired monthly credits are gone
    assert bal.expiring_soon == 0
    # History is intact — the grant is still in the ledger.
    entries = ledger.list_entries("u1")
    assert any(e["idempotency_key"] == "m-old" for e in entries)


def test_grant_is_idempotent(ledger: CreditLedger) -> None:
    """Re-granting the same idempotency key does not double-grant."""
    lot = ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")
    again = ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")

    assert again.lot_id == lot.lot_id   # same lot returned, no second lot created
    assert ledger.balance("u1").available == 100


def test_reserve_is_idempotent(ledger: CreditLedger) -> None:
    """Re-reserving the same idempotency key returns the same reservation."""
    ledger.grant("u1", 200, source="purchase", expires_at=None, idempotency_key="p1")
    first = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")
    second = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")

    assert second.reservation_id == first.reservation_id
    assert ledger.balance("u1").available == 150  # only one reservation deducted


def test_reserve_insufficient_raises(ledger: CreditLedger) -> None:
    ledger.grant("u1", 10, source="purchase", expires_at=None, idempotency_key="p1")
    with pytest.raises(Exception):
        ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")
    # Nothing was deducted on failure.
    assert ledger.balance("u1").available == 10


def test_settle_consumes_a_reservation(ledger: CreditLedger) -> None:
    """A successful task settles its reservation — credits leave the lots for good."""
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")
    res = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")

    ledger.settle(res.reservation_id, idempotency_key="run-1")

    # After settle the 50 are gone entirely (reserved → consumed).
    assert ledger.balance("u1").available == 50


def test_refund_restores_a_settled_reservation_exactly_once(ledger: CreditLedger) -> None:
    """A failed task refunds its settled reservation — idempotent (§4.2, §9)."""
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")
    res = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")
    ledger.settle(res.reservation_id, idempotency_key="run-1")
    assert ledger.balance("u1").available == 50

    ledger.refund(res.reservation_id, idempotency_key="run-1")
    assert ledger.balance("u1").available == 100  # restored

    # Refunding the same reservation again does nothing.
    ledger.refund(res.reservation_id, idempotency_key="run-1")
    assert ledger.balance("u1").available == 100


def test_list_lots_reports_remaining_and_expiry(ledger: CreditLedger) -> None:
    exp = _month_end()
    ledger.grant("u1", 30, source="monthly", expires_at=exp, idempotency_key="m1")
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")

    lots = {l["idempotency_key"]: l for l in ledger.list_lots("u1")}
    assert lots["m1"]["amount_remaining"] == 30
    assert lots["m1"]["expires_at"] == exp
    assert lots["p1"]["amount_remaining"] == 100
    assert lots["p1"]["expires_at"] is None


def test_reservation_failure_does_not_partially_allocate(ledger: CreditLedger) -> None:
    """If reserve can't be satisfied, no lot's remaining is touched."""
    ledger.grant("u1", 10, source="purchase", expires_at=None, idempotency_key="p1")
    with pytest.raises(Exception):
        ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")
    lots = ledger.list_lots("u1")
    assert sum(l["amount_remaining"] for l in lots) == 10
