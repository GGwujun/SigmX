"""SigmX product domain — catalog, credits, commerce, devices, tokens.

Bounded domain for the public-website / Data-Hub / desktop product closure
(design ``docs/superpowers/specs/2026-08-02-product-closure-design.md``). Keeps
its own ``product.db`` and transaction boundary so it never disturbs the
existing local databases.
"""

from src.product.commerce import (
    ActivationError,
    ActivationResult,
    CommerceService,
    CreatedCode,
    EntitlementSnapshot,
)
from src.product.credits import (
    Balance,
    CreditLedger,
    GrantResult,
    InsufficientCredits,
    Reservation,
    migrate_legacy_balances,
)
from src.product.devices import (
    DeviceLimitReached,
    DeviceService,
    PollStatus,
)
from src.product.tokens import (
    PRODUCT_AUDIENCE,
    create_product_token,
    verify_product_token,
)
from src.product.models import (
    ENTITLEMENT_KEYS,
    OrderStatus,
    PaymentChannel,
    PlanCode,
)
from src.product.payment import (
    ActivationCodeProvider,
    PaymentEvent,
    PaymentProvider,
    hash_code,
)
from src.product.store import ProductStore

__all__ = [
    "ProductStore",
    "CreditLedger",
    "CommerceService",
    "ActivationResult",
    "ActivationError",
    "CreatedCode",
    "EntitlementSnapshot",
    "Balance",
    "GrantResult",
    "InsufficientCredits",
    "Reservation",
    "migrate_legacy_balances",
    "DeviceService",
    "DeviceLimitReached",
    "PollStatus",
    "PRODUCT_AUDIENCE",
    "create_product_token",
    "verify_product_token",
    "ActivationCodeProvider",
    "PaymentProvider",
    "PaymentEvent",
    "hash_code",
    "PlanCode",
    "OrderStatus",
    "PaymentChannel",
    "ENTITLEMENT_KEYS",
]
