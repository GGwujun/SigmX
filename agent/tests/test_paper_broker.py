"""Tests for the paper broker connector — SDK behavior + live-gate integration.

Two layers:
1. Pure SDK behavior — place_order/get_positions/get_account_snapshot math,
   buying-power rejection, sell-without-shares rejection.
2. Live-safety gate integration — paper broker as the connector_module through
   ``execute_live_order``: a valid mandate allows + fills; a notional breach
   denies and never reaches the broker.
"""

from __future__ import annotations

import pytest

from src.live import sdk_order_gate as gate
from src.live.enforcement import OrderIntent
from src.live.mandate.model import (
    AssetClass,
    ConsentMeta,
    HardCaps,
    InstrumentType,
    Mandate,
    UniverseConstraint,
)
from src.trading.connectors import paper

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _config(*, cash=100_000.0, quotes=None) -> "paper.PaperConfig":
    if quotes is None:
        quotes = {"AAPL": 150.0}
    return paper.build_config({"initial_cash": cash, "quotes": quotes})


def _mandate(*, max_order=1_000.0) -> Mandate:
    return Mandate(
        schema_version=1,
        hard_caps=HardCaps(
            account_funding_usd=1_000_000.0,
            max_order_notional_usd=max_order,
            max_total_exposure_usd=1_000_000.0,
            max_leverage=2.0,
            allowed_instruments=(InstrumentType.EQUITY,),
            max_trades_per_day=100,
        ),
        universe=UniverseConstraint(
            asset_classes=(AssetClass.US_EQUITY,),
            min_market_cap_usd=None,
            min_avg_daily_volume_usd=None,
            exclude_symbols=(),
        ),
        consent=ConsentMeta(
            created_at="2026-01-01T00:00:00+00:00",
            consent_token_sha256="deadbeef",
            broker="paper",
            account_ref="paper-1",
            expires_at="2999-01-01T00:00:00+00:00",
        ),
    )


def _patch_gate(monkeypatch, *, mandate, halted=False) -> None:
    monkeypatch.setattr(gate, "load_mandate", lambda broker: mandate)
    monkeypatch.setattr(gate, "halt_flag_set", lambda broker: halted)
    monkeypatch.setattr(gate, "write_live_action", lambda *a, **k: {"audited": True})
    monkeypatch.setattr(gate, "read_daily_count", lambda broker: 0)
    monkeypatch.setattr(gate, "increment_daily_count", lambda broker: 1)


def _intent(*, notional=None, qty=None) -> OrderIntent:
    return OrderIntent(
        symbol="AAPL", side="buy", notional_usd=notional, quantity=qty,
        instrument_type=InstrumentType.EQUITY, asset_class=AssetClass.US_EQUITY,
    )


# --------------------------------------------------------------------------- #
# 1. Pure SDK behavior
# --------------------------------------------------------------------------- #


def test_buy_updates_cash_position_and_equity() -> None:
    cfg = _config()
    r = paper.place_order(cfg, symbol="aapl", side="buy", quantity=10)
    assert r["status"] == "ok"
    assert r["filled_qty"] == 10.0
    # 10 @ 150 = 1500 spent.
    assert cfg.cash == pytest.approx(100_000 - 1500)
    pos = paper.get_positions(cfg)["positions"][0]
    assert pos["symbol"] == "AAPL"
    assert pos["quantity"] == 10.0
    assert pos["market_value"] == pytest.approx(1500)
    acct = paper.get_account_snapshot(cfg)["account"]
    assert acct["equity"] == pytest.approx(100_000)  # cash + market_value unchanged


def test_notional_order_derives_quantity_from_price() -> None:
    cfg = _config()
    r = paper.place_order(cfg, symbol="AAPL", side="buy", notional_usd=600.0)
    assert r["status"] == "ok"
    assert r["quantity"] == pytest.approx(4.0)  # 600 / 150


def test_sell_reduces_position_and_adds_cash() -> None:
    cfg = _config()
    paper.place_order(cfg, symbol="AAPL", side="buy", quantity=10)
    r = paper.place_order(cfg, symbol="AAPL", side="sell", quantity=4)
    assert r["status"] == "ok"
    assert paper.get_positions(cfg)["positions"][0]["quantity"] == pytest.approx(6.0)
    # 100000 - 1500 (buy) + 4*150 (sell) = 99100
    assert cfg.cash == pytest.approx(100_000 - 1500 + 600)


def test_insufficient_buying_power_rejected() -> None:
    cfg = _config(cash=1000.0)
    r = paper.place_order(cfg, symbol="AAPL", side="buy", quantity=100)  # 100*150=15000 > 1000
    assert r["status"] == "error"
    assert "buying power" in r["error"]
    assert cfg.cash == pytest.approx(1000.0)
    assert paper.get_positions(cfg)["positions"] == []


def test_sell_without_shares_rejected() -> None:
    cfg = _config()
    r = paper.place_order(cfg, symbol="AAPL", side="sell", quantity=1)
    assert r["status"] == "error"
    assert "insufficient" in r["error"]


def test_order_without_quote_fails_closed() -> None:
    cfg = _config(quotes={})  # no AAPL quote seeded
    r = paper.place_order(cfg, symbol="AAPL", side="buy", quantity=1)
    assert r["status"] == "error"


# --------------------------------------------------------------------------- #
# 2. Live-safety gate integration (paper broker as the connector_module)
# --------------------------------------------------------------------------- #


def test_gate_allows_and_fills_through_paper_broker(monkeypatch) -> None:
    """A valid mandate → ALLOW → paper broker fills → state updated."""
    _patch_gate(monkeypatch, mandate=_mandate(max_order=2000.0))
    cfg = _config()
    out = gate.execute_live_order(
        broker="paper",
        connector_module=paper,
        config=cfg,
        intent=_intent(qty=10),  # 10 * 150 = 1500 <= 2000 cap
        place_kwargs={"symbol": "AAPL", "side": "buy", "quantity": 10},
        session_id="test-sess",
    )
    assert out["status"] == "ok"
    # The broker actually filled.
    assert cfg.cash == pytest.approx(100_000 - 1500)
    assert paper.get_positions(cfg)["positions"][0]["quantity"] == 10.0


def test_gate_denies_notional_breach_never_reaches_broker(monkeypatch) -> None:
    """A notional cap breach → DENY → paper broker untouched."""
    _patch_gate(monkeypatch, mandate=_mandate(max_order=500.0))
    cfg = _config()
    out = gate.execute_live_order(
        broker="paper",
        connector_module=paper,
        config=cfg,
        intent=_intent(qty=10),  # 10 * 150 = 1500 > 500 cap
        place_kwargs={"symbol": "AAPL", "side": "buy", "quantity": 10},
    )
    assert out["status"] == "blocked"
    # Broker state unchanged.
    assert cfg.cash == pytest.approx(100_000)
    assert paper.get_positions(cfg)["positions"] == []


def test_paper_extractor_registered() -> None:
    """The paper broker has an order-intent extractor for the MCP gate path."""
    from src.live.extractors import get_extractor

    extractor = get_extractor("paper")
    assert extractor is not None
    intent = extractor("place_order", {"symbol": "aapl", "side": "buy", "quantity": 5})
    assert intent is not None
    assert intent.symbol == "AAPL"
    assert intent.quantity == 5.0
