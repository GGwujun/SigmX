from datetime import datetime, timedelta, timezone

import pytest
from fastapi.responses import JSONResponse

from src.product.commerce import CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.datahub_budgets import DataHubBudgetService, DailyBudgetExceeded
from src.product.datahub_credentials import DataHubCredentialService
from src.product.datahub_gateway import DataHubRequestGateway
from src.product.store import ProductStore


class Request:
    def __init__(self, key):
        self.headers = {"authorization": f"Bearer {key}"}
        self.query_params = {}
        self.client = type("Client", (), {"host": "127.0.0.1"})()


def test_budget_is_owner_bound_and_resets_by_utc_day(tmp_path):
    now = [datetime(2026, 8, 15, 23, 59, tzinfo=timezone.utc)]
    store = ProductStore(tmp_path / "product.db")
    credential = DataHubCredentialService(store).create("u1", "dev", ["stocks.metadata"], [], None)
    budgets = DataHubBudgetService(store, now=lambda: now[0])
    budgets.set("u1", credential.id, 10)
    with pytest.raises(ValueError):
        budgets.set("u2", credential.id, 5)
    budgets.check("u1", credential.id, 10)
    store._get_conn().execute(
        "INSERT INTO datahub_request_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("r1", "u1", credential.id, "stocks.metadata", 200, 1, 1, 10, 10, 1, None, now[0].isoformat()),
    )
    store._get_conn().commit()
    with pytest.raises(DailyBudgetExceeded):
        budgets.check("u1", credential.id, 1)
    now[0] += timedelta(minutes=2)
    budgets.check("u1", credential.id, 10)


def test_gateway_rejects_before_credit_deduction_and_emits_thresholds(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    credentials = DataHubCredentialService(store)
    created = credentials.create("u1", "dev", ["stocks.metadata"], [], None)
    CommerceService(store, CreditLedger(store)).ensure_monthly_data_grant(
        "u1", "free", datetime(2026, 8, 15).date()
    )
    budgets = DataHubBudgetService(store)
    budgets.set("u1", created.id, 1)
    gateway = DataHubRequestGateway(store)

    prepared = gateway.prepare(Request(created.plaintext), "GET", "/api/v1/stocks/metadata")
    gateway.complete(prepared, JSONResponse({"ok": True, "data": []}))
    assert [event.threshold_percent for event in budgets.list_events("u1")] == [100, 80, 50]
    before = DataCreditLedger(store).balance("u1").available
    with pytest.raises(DailyBudgetExceeded):
        gateway.prepare(Request(created.plaintext), "GET", "/api/v1/stocks/metadata")
    assert DataCreditLedger(store).balance("u1").available == before


def test_in_flight_authorizations_cannot_oversubscribe_budget(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    credential = DataHubCredentialService(store).create("u1", "dev", ["stocks.metadata"], [], None)
    budgets = DataHubBudgetService(store)
    budgets.set("u1", credential.id, 10)

    budgets.reserve("u1", credential.id, "request-1", 7)
    with pytest.raises(DailyBudgetExceeded):
        budgets.reserve("u1", credential.id, "request-2", 4)

    budgets.release("request-1")
    budgets.reserve("u1", credential.id, "request-2", 4)
