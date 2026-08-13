"""Payment provider protocol and the activation-code provider.

Design §5.2: every payment channel (activation code now; Alipay/WeChat later)
implements the same five-method contract, so the commerce layer never branches
on channel. The activation-code provider is the only one that ships in the first
operable release; real providers may only set an order paid via signed webhook
or active query — never from a frontend redirect result.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


def hash_code(plaintext: str) -> str:
    """SHA-256 hash of an activation code. Plaintext is never persisted (§9)."""
    return hashlib.sha256(plaintext.strip().upper().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PaymentEvent:
    """Normalized outcome parsed from a provider callback/query."""

    order_ref: str           # the local order id / idempotency ref
    provider_payment_id: str
    paid: bool
    amount_cny_fen: int
    raw: dict[str, Any]


@runtime_checkable
class PaymentProvider(Protocol):
    """Adapter contract every payment channel implements (design §5.2)."""

    def create_checkout(self, order: dict[str, Any]) -> dict[str, Any]:
        """Create a payment session for an order. Returns provider-specific handle."""
        ...

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        """Verify a callback's signature/authenticity."""
        ...

    def parse_event(self, body: bytes) -> PaymentEvent:
        """Convert a callback body into a normalized PaymentEvent."""
        ...

    def query_payment(self, provider_payment_id: str) -> PaymentEvent:
        """Actively query the provider for a payment's status."""
        ...

    def refund(self, provider_payment_id: str, amount: int) -> bool:
        """Refund a payment. Returns True on success."""
        ...


class ActivationCodeProvider:
    """The first-channel provider: activation codes are zero-value, instantly paid.

    A code is "verified" by looking it up in ``activation_codes`` and confirming
    it is unused + unexpired. There is no external callback, so webhook/query
    surface exists only to satisfy the protocol — activation is decided inside
    :class:`src.product.commerce.CommerceService` in the same transaction.
    """

    channel = "activation_code"

    def __init__(self, store: Any | None = None) -> None:
        self.store = store

    def create_checkout(self, order: dict[str, Any]) -> dict[str, Any]:
        # Codes need no checkout session — the user types the code directly.
        return {"channel": self.channel, "order_ref": order.get("id")}

    def verify_webhook(self, headers: dict[str, str], body: bytes) -> bool:
        # No external callback path for activation codes.
        return False

    def parse_event(self, body: bytes) -> PaymentEvent:
        import json

        data = json.loads(body.decode("utf-8"))
        return PaymentEvent(
            order_ref=data.get("order_ref", ""),
            provider_payment_id=data.get("code_hash", ""),
            paid=bool(data.get("paid", False)),
            amount_cny_fen=0,
            raw=data,
        )

    def query_payment(self, provider_payment_id: str) -> PaymentEvent:
        # Activation has no async provider state to query.
        return PaymentEvent(
            order_ref="",
            provider_payment_id=provider_payment_id,
            paid=False,
            amount_cny_fen=0,
            raw={},
        )

    def refund(self, provider_payment_id: str, amount: int) -> bool:
        # Zero-value orders have nothing to refund.
        return True
