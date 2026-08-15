"""Product-domain DTOs and stable enums.

These types are the contract every later product-closure task consumes. They are
defined once here so credits, activation, devices, tokens and routes never branch
on Chinese plan labels (design §6 — stable entitlement keys only).
"""

from __future__ import annotations

from enum import StrEnum


class PlanCode(StrEnum):
    """Canonical plan codes — the only plan identifier business code may use."""

    FREE = "free"
    DESKTOP_PRO = "desktop_pro"
    DATA_DEVELOPER = "data_developer"
    PRO_BUNDLE = "pro_bundle"


class OrderStatus(StrEnum):
    """Lifecycle of an activation/payment order (design §5)."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentChannel(StrEnum):
    """Adapter-protocol channel identifiers. ``activation_code`` ships first."""

    ACTIVATION_CODE = "activation_code"
    ALIPAY = "alipay"
    WECHAT = "wechat"


# Stable entitlement keys — never compare against a translated plan name.
ENTITLEMENT_KEYS = {
    "datahub.enabled",
    "datahub.dataset_groups",
    "datahub.monthly_credits",
    "datahub.rate_limit_per_minute",
    "datahub.concurrent_limit",
    "datahub.max_rows_per_request",
    "datahub.history_depth_days",
    "datahub.commercial_use",
    "cloud_ai.enabled",
    "cloud_ai.concurrent_jobs",
    "cloud_ai.credit_per_alphaforge",
    "cloud_ai.credit_per_fund_arb",
    "desktop.connected_mode",
    "desktop.device_limit",
    "reports.cloud_history",
    "admin.operations",
}
