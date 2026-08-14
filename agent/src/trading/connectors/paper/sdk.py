"""Paper broker SDK connector — an in-memory simulated broker.

This is the **direct-SDK path** broker module (see ``src/live/sdk_order_gate.py``):
it exposes the module-level function contract every connector implements —
``build_config`` / ``place_order`` / ``get_positions`` / ``get_account_snapshot``
/ ``get_quote`` / ``cancel_order`` / ``get_open_orders``.

No network, no real money. Orders fill instantly at the seeded quote price; cash
and positions update in memory on the :class:`PaperConfig`. Use it to exercise
the full live-safety gate (mandate → enforcement → reconcile) and to demo paper
trading end-to-end via ``service.place_order`` (the ``paper`` profile bypasses
the gate and connects here directly).

Return envelopes follow the contract the gate expects: ``{"status": "ok", ...}``
on success (the gate checks the literal string ``"ok"``), and positions carry a
``market_value`` so :func:`src.live.enforcement._position_market_value` can price
exposure.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

logger = logging.getLogger(__name__)


@dataclass
class PaperConfig:
    """Carries the in-memory broker state. One config = one paper account."""

    initial_cash: float = 100_000.0
    is_paper: bool = True
    # Mutable state:
    cash: float = field(init=False)
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    quotes: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash


def build_config(
    profile_config: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> PaperConfig:
    """Build a PaperConfig from profile + overrides.

    Recognized keys: ``initial_cash``, ``quotes`` (``{symbol: price}`` seed),
    ``positions`` (``{symbol: quantity}`` seed at the seeded/zero price).
    """
    merged: dict[str, Any] = {}
    for src in (profile_config or {}, overrides or {}):
        merged.update(src)
    cfg = PaperConfig(initial_cash=float(merged.get("initial_cash", 100_000.0)))
    for symbol, price in (merged.get("quotes") or {}).items():
        cfg.quotes[str(symbol).strip().upper()] = float(price)
    for symbol, qty in (merged.get("positions") or {}).items():
        sym = str(symbol).strip().upper()
        price = cfg.quotes.get(sym, 0.0)
        q = float(qty)
        if q != 0:
            # Seed a position without spending cash (it's a starting holding, not a trade).
            cfg.positions[sym] = {"quantity": q, "avg_price": price}
    return cfg


def _resolve_symbol(kwargs: Mapping[str, Any]) -> str | None:
    for key in ("symbol", "ticker"):
        v = kwargs.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip().upper()
    return None


def place_order(config: PaperConfig, **kwargs: Any) -> dict[str, Any]:
    """Fill a paper order instantly at the quote price. Returns a status envelope."""
    symbol = _resolve_symbol(kwargs)
    if not symbol:
        return {"status": "error", "error": "symbol required"}
    side = str(kwargs.get("side") or kwargs.get("action") or "").strip().lower()
    if side not in ("buy", "sell"):
        return {"status": "error", "error": "side must be buy/sell"}

    # Price: explicit limit/price → quote table → error (fail-closed).
    price = kwargs.get("limit_price") or kwargs.get("price")
    if not isinstance(price, (int, float)) or price <= 0:
        price = config.quotes.get(symbol)
    if not price or price <= 0:
        return {"status": "error", "error": f"no quote for {symbol}; seed quotes first"}

    # Quantity: explicit → notional/price.
    qty = kwargs.get("quantity", kwargs.get("qty", kwargs.get("shares")))
    if not isinstance(qty, (int, float)) or qty <= 0:
        notional = kwargs.get("notional_usd", kwargs.get("notional", kwargs.get("amount")))
        if isinstance(notional, (int, float)) and notional > 0:
            qty = float(notional) / float(price)
        else:
            return {"status": "error", "error": "quantity or notional required"}

    qty = float(qty)
    cost = qty * float(price)
    order_id = f"paper_{uuid.uuid4().hex[:10]}"

    if side == "buy":
        if cost > config.cash + 1e-9:
            return {"status": "error", "error": "insufficient buying power", "order_id": order_id}
        config.cash -= cost
        pos = config.positions.setdefault(symbol, {"quantity": 0.0, "avg_price": 0.0})
        new_qty = pos["quantity"] + qty
        pos["avg_price"] = ((pos["avg_price"] * pos["quantity"]) + cost) / new_qty if new_qty else 0.0
        pos["quantity"] = new_qty
    else:
        pos = config.positions.get(symbol)
        if not pos or pos["quantity"] < qty - 1e-9:
            return {"status": "error", "error": f"insufficient shares of {symbol}", "order_id": order_id}
        pos["quantity"] -= qty
        config.cash += cost
        if pos["quantity"] <= 1e-9:
            pos["quantity"] = 0.0
            pos["avg_price"] = 0.0

    order = {
        "status": "ok",
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "price": float(price),
        "notional_usd": cost,
        "filled_qty": qty,
        "state": "filled",
        "is_paper": True,
    }
    config.orders.append(order)
    logger.info("paper fill %s %s %.4f @ %.2f", side, symbol, qty, price)
    return order


def cancel_order(config: PaperConfig, order_id: str = "", *, symbol: str | None = None, **_: Any) -> dict[str, Any]:
    """Paper orders fill instantly; cancel is an idempotent ack."""
    return {"status": "ok", "order_id": order_id, "cancelled": True, "state": "cancelled"}


def get_positions(config: PaperConfig | None = None) -> dict[str, Any]:
    cfg = config or build_config()
    positions = []
    for sym, p in cfg.positions.items():
        if p["quantity"] > 1e-9:
            price = cfg.quotes.get(sym, p["avg_price"])
            positions.append({
                "symbol": sym,
                "quantity": p["quantity"],
                "avg_price": p["avg_price"],
                "price": price,
                "market_value": p["quantity"] * price,
            })
    return {"status": "ok", "positions": positions}


def get_account_snapshot(config: PaperConfig | None = None) -> dict[str, Any]:
    cfg = config or build_config()
    market_value = sum(
        p["quantity"] * cfg.quotes.get(s, p["avg_price"])
        for s, p in cfg.positions.items()
    )
    return {
        "status": "ok",
        "account": {
            "equity": cfg.cash + market_value,
            "cash": cfg.cash,
            "buying_power": cfg.cash,
            "market_value": market_value,
        },
    }


def get_quote(symbol: str, *, config: PaperConfig | None = None, **_: Any) -> dict[str, Any]:
    cfg = config or build_config()
    price = cfg.quotes.get(str(symbol).strip().upper())
    if price is None:
        return {"status": "error", "error": f"no quote for {symbol}"}
    return {"status": "ok", "symbol": str(symbol).strip().upper(), "quote": {"last": price, "price": price}}


def get_open_orders(config: PaperConfig | None = None, *, include_executions: bool = False, **_: Any) -> dict[str, Any]:
    """Paper orders fill instantly, so there are never open orders.

    Pass ``include_executions=True`` to surface the filled-order history.
    """
    cfg = config or build_config()
    if include_executions:
        return {"status": "ok", "open_orders": [], "executions": list(cfg.orders)}
    return {"status": "ok", "open_orders": []}
