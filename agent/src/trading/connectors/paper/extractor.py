"""Paper broker order-intent extractor (SPEC.md Mandate Enforcement §4).

The paper broker accepts plain, normalized ``place_order`` kwargs — ``symbol`` /
``side`` plus exactly one of ``notional_usd`` / ``quantity``. It exists to
exercise the full live-safety gate (mandate → enforcement → reconcile) without a
real broker, so the extractor is intentionally simple and never guesses: any
missing or ambiguous required field returns ``None`` (→ DENY).

This mirrors the Robinhood extractor's contract but with standard tool names.
"""

from __future__ import annotations

from src.live.enforcement import OrderIntent
from src.live.mandate.model import InstrumentType

#: Tools that place an order (everything else is a read / management tool).
_ORDER_TOOLS = frozenset({"place_order", "submit_order"})

#: Accepted side spellings → normalized ``"buy"`` / ``"sell"``.
_SIDE_ALIASES = {
    "buy": "buy", "b": "buy", "long": "buy", "buy_to_open": "buy",
    "sell": "sell", "s": "sell", "short": "sell", "sell_to_close": "sell",
}

#: Order-size keys for the notional path (USD amount).
_NOTIONAL_KEYS = ("notional_usd", "notional", "amount", "dollar_amount")

#: Order-size keys for the share/contract quantity path.
_QUANTITY_KEYS = ("quantity", "qty", "shares", "units")


def extract_order_intent(remote_name: str, kwargs: dict) -> OrderIntent | None:
    """Parse a paper ``place_order`` into a normalized :class:`OrderIntent`.

    Returns ``None`` (→ DENY) when the tool is not an order tool, a required
    field is absent, or a field is ambiguous/invalid. Never guesses.
    """
    if remote_name not in _ORDER_TOOLS:
        return None
    if not isinstance(kwargs, dict):
        return None

    symbol = _extract_symbol(kwargs)
    if symbol is None:
        return None
    side = _extract_side(kwargs)
    if side is None:
        return None

    notional, quantity = _extract_size(kwargs)
    if notional is None and quantity is None:
        return None  # unsized order — cannot enforce

    return OrderIntent(
        symbol=symbol,
        side=side,
        notional_usd=notional,
        quantity=quantity,
        instrument_type=_extract_instrument(kwargs),
    )


def _extract_symbol(kwargs: dict) -> str | None:
    for key in ("symbol", "ticker"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _extract_side(kwargs: dict) -> str | None:
    for key in ("side", "action", "direction"):
        value = kwargs.get(key)
        if isinstance(value, str):
            normalized = _SIDE_ALIASES.get(value.strip().lower())
            if normalized is not None:
                return normalized
    return None


def _extract_size(kwargs: dict) -> tuple[float | None, float | None]:
    """Return ``(notional_usd, quantity)`` — at least one is required."""
    notional: float | None = None
    for key in _NOTIONAL_KEYS:
        value = kwargs.get(key)
        if isinstance(value, (int, float)) and value > 0:
            notional = float(value)
            break
    quantity: float | None = None
    for key in _QUANTITY_KEYS:
        value = kwargs.get(key)
        if isinstance(value, (int, float)) and value > 0:
            quantity = float(value)
            break
    return notional, quantity


def _extract_instrument(kwargs: dict) -> InstrumentType:
    """Paper orders default to EQUITY unless an explicit type is passed."""
    raw = kwargs.get("instrument_type") or kwargs.get("type")
    if isinstance(raw, str):
        try:
            return InstrumentType(raw.strip().lower())
        except ValueError:
            pass
    return InstrumentType.EQUITY
