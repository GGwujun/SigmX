from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.store import ProductStore


@pytest.fixture
def product(tmp_path: Path):
    store = ProductStore(tmp_path / "product.db")
    commerce = CommerceService(store, CreditLedger(store))
    return store, commerce, DataCreditLedger(store)


@pytest.mark.parametrize(("plan", "expected"), [("advanced", 30_000), ("pro", 150_000)])
def test_activation_grants_monthly_data_credits_once(product, plan: str, expected: int) -> None:
    store, commerce, data_ledger = product
    code = commerce.admin_create_activation_code(plan=plan, months=3)
    first = commerce.activate_code("u1", code.plaintext, "activate-1")
    replay = commerce.activate_code("u1", code.plaintext, "activate-1")
    assert first.replayed is False and replay.replayed is True
    assert data_ledger.balance("u1").available == expected
    lots = data_ledger.list_lots("u1")
    assert len(lots) == 1
    assert lots[0]["idempotency_key"].startswith(f"data-plan-month:u1:{plan}:")
    expiry = datetime.fromisoformat(lots[0]["expires_at"])
    assert expiry.day == 1 and expiry.hour == 0 and expiry.tzinfo == timezone.utc


def test_same_plan_month_is_idempotent_but_next_month_gets_new_lot(product) -> None:
    _, commerce, data_ledger = product
    current = date(2026, 8, 15)
    first = commerce.ensure_monthly_data_grant("u1", "advanced", current)
    replay = commerce.ensure_monthly_data_grant("u1", "advanced", date(2026, 8, 31))
    next_month = commerce.ensure_monthly_data_grant("u1", "advanced", date(2026, 9, 1))
    assert first is not None and replay is not None and next_month is not None
    assert replay.idempotent_replay is True
    assert next_month.idempotent_replay is False
    assert len(data_ledger.list_lots("u1")) == 2


def test_free_monthly_grant_is_available_on_first_datahub_contact(product) -> None:
    _, commerce, data_ledger = product
    commerce.ensure_monthly_data_grant("u1", "free", date(2026, 8, 15))
    assert data_ledger.balance("u1").available == 1_000


def test_removed_enterprise_plan_cannot_enter_activation_flow(product) -> None:
    _, commerce, _ = product
    with pytest.raises(ValueError, match="cannot create activation code"):
        commerce.admin_create_activation_code(plan="enterprise", months=3)
