from datetime import datetime, timezone
import asyncio

import pytest

from src.product.commerce import ActivationError, CommerceService
from src.product.credits import CreditLedger
from src.product.data_credits import DataCreditLedger
from src.product.store import ProductStore
import src.api.product_routes as pr


def test_pack_catalog_and_atomic_redeem(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    packs = {item["code"]: item for item in store.list_data_credit_packs()}
    assert packs["data_10k"]["credits"] == 10_000
    assert packs["data_10k"]["valid_days"] == 365

    commerce = CommerceService(store, CreditLedger(store))
    code = commerce.admin_create_data_credit_code(pack_code="data_10k")
    first = commerce.redeem_data_credit_code("u1", code.plaintext, "pack-redeem")
    replay = commerce.redeem_data_credit_code("u1", code.plaintext, "pack-redeem")

    assert first.credits_granted == 10_000
    assert replay.replayed is True
    lots = DataCreditLedger(store).list_lots("u1")
    assert len(lots) == 1 and lots[0]["source"] == "purchase"
    expiry = datetime.fromisoformat(lots[0]["expires_at"])
    assert 364 <= (expiry - datetime.now(timezone.utc)).days <= 365
    order = store._get_conn().execute("SELECT * FROM orders WHERE id=?", (first.order_id,)).fetchone()
    assert order["price_cny_fen"] == 3900
    assert order["plan_code"] == "data_10k"


def test_pack_code_is_single_use_and_does_not_grant_research_credits(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    research = CreditLedger(store)
    commerce = CommerceService(store, research)
    code = commerce.admin_create_data_credit_code(pack_code="data_10k")
    commerce.redeem_data_credit_code("u1", code.plaintext, "u1-pack")
    with pytest.raises(ActivationError):
        commerce.redeem_data_credit_code("u2", code.plaintext, "u2-pack")
    assert research.balance("u1").available == 0
    assert DataCreditLedger(store).balance("u2").available == 0


def test_pack_catalog_and_redeem_routes(tmp_path, monkeypatch):
    store = ProductStore(tmp_path / "product.db")
    pr._store = store
    pr._ledger = CreditLedger(store)
    pr._commerce = CommerceService(store, pr._ledger)
    try:
        catalog = asyncio.run(pr.list_data_credit_packs())
        assert [item.code for item in catalog.items] == ["data_10k", "data_50k", "data_200k"]
        created = pr._commerce.admin_create_data_credit_code(pack_code="data_10k")
        result = asyncio.run(pr.redeem_data_credit_pack(
            body=pr.ActivateRequest(code=created.plaintext, idempotency_key="route-pack"),
            user={"id": "u1"},
        ))
        assert result.credits_granted == 10_000
    finally:
        pr._store = pr._ledger = pr._commerce = None
