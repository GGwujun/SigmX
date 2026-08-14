"""Paper broker connector — in-memory simulated broker for the live-safety gate.

Two surfaces, matching the two broker paths in ``src/live/``:
- :mod:`sdk` — the direct-SDK module functions (place_order/get_positions/...),
  used by ``service.place_order`` and ``sdk_order_gate``.
- :mod:`extractor` — the order-intent extractor registered for the MCP gate
  (``order_guard``), so a paper broker key also works through the MCP path.

No network, no real money.
"""

from src.trading.connectors.paper.sdk import (
    PaperConfig,
    build_config,
    cancel_order,
    get_account_snapshot,
    get_open_orders,
    get_positions,
    get_quote,
    place_order,
)

__all__ = [
    "PaperConfig",
    "build_config",
    "place_order",
    "cancel_order",
    "get_positions",
    "get_account_snapshot",
    "get_quote",
    "get_open_orders",
]
