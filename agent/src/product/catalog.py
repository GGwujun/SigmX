"""Default plan catalog and entitlement seeding.

The catalog is server-driven: prices and quotas live here and in ``product.db``,
never hard-coded in the frontend (design §4.1, plan Global Constraints). Values
mirror the 2026-08-02 product-closure design §4.1/§4.2.

Amounts and quotas are initial operating values — operators can change them in
the store; orders snapshot the price+entitlements at purchase time (design §4.1).
"""

from __future__ import annotations

from typing import TypeAlias, TypedDict


EntitlementValue: TypeAlias = int | bool | list[str]


class PlanSeed(TypedDict):
    """Row shape for the canonical plan seed, as stored in ``product.db``.

    ``entitlements`` is canonical JSON — stable keys only (see ``models.ENTITLEMENT_KEYS``).
    """

    code: str
    name_zh: str
    price_cny_fen: int  # 1 fen = 1/100 CNY. 0 for free / contract-priced.
    billing_period: str  # "one_time" | "quarter" | "contract"
    monthly_credits: int  # plan credits granted per natural month; 0 if none
    welcome_credits: int  # one-time grant at registration; 0 if none
    description: str
    entitlements: dict[str, EntitlementValue]
    sort_order: int


# Free plan: basic Data Hub access, 50 one-time research credits, single device.
FREE: PlanSeed = {
    "code": "free",
    "name_zh": "免费版",
    "price_cny_fen": 0,
    "billing_period": "one_time",
    "monthly_credits": 0,
    "welcome_credits": 50,
    "description": "体验与本地基础功能",
    "entitlements": {
        "datahub.enabled": True,
        "datahub.dataset_groups": ["basic.v1"],
        "datahub.monthly_credits": 1_000,
        "datahub.rate_limit_per_minute": 30,
        "datahub.concurrent_limit": 1,
        "datahub.max_rows_per_request": 1_000,
        "datahub.history_depth_days": 365,
        "datahub.commercial_use": False,
        "desktop.connected_mode": True,
        "desktop.device_limit": 1,
        "cloud_ai.enabled": True,
        "cloud_ai.concurrent_jobs": 1,
        "reports.cloud_history": False,
    },
    "sort_order": 1,
}

# Desktop Pro: the professional harness, with a basic Data Hub allowance.
DESKTOP_PRO: PlanSeed = {
    "code": "desktop_pro",
    "name_zh": "Desktop Pro",
    "price_cny_fen": 26800,
    "billing_period": "quarter",
    "monthly_credits": 300,
    "welcome_credits": 0,
    "description": "完整金融研究工作台，附赠基础数据额度",
    "entitlements": {
        "datahub.enabled": True,
        "datahub.dataset_groups": ["basic.v1"],
        "datahub.monthly_credits": 10_000,
        "datahub.rate_limit_per_minute": 120,
        "datahub.concurrent_limit": 3,
        "datahub.max_rows_per_request": 10_000,
        "datahub.history_depth_days": 1_825,
        "datahub.commercial_use": False,
        "desktop.connected_mode": True,
        "desktop.device_limit": 1,
        "cloud_ai.enabled": True,
        "cloud_ai.concurrent_jobs": 2,
        "cloud_ai.credit_per_alphaforge": 50,
        "cloud_ai.credit_per_fund_arb": 20,
        "reports.cloud_history": True,
    },
    "sort_order": 2,
}

# Data Pro: Desktop Pro plus expanded standard market and finance APIs.
DATA_DEVELOPER: PlanSeed = {
    "code": "data_developer",
    "name_zh": "Data Pro",
    "price_cny_fen": 39800,
    "billing_period": "quarter",
    "monthly_credits": 700,
    "welcome_credits": 0,
    "description": "完整个人投研能力，增加标准行情与财务数据接口",
    "entitlements": {
        "datahub.enabled": True,
        "datahub.dataset_groups": ["basic.v1", "market.v1", "finance.v1"],
        "datahub.monthly_credits": 100_000,
        "datahub.rate_limit_per_minute": 300,
        "datahub.concurrent_limit": 5,
        "datahub.max_rows_per_request": 50_000,
        "datahub.history_depth_days": 3_650,
        "datahub.commercial_use": False,
        "desktop.connected_mode": True,
        "desktop.device_limit": 2,
        "cloud_ai.enabled": True,
        "cloud_ai.concurrent_jobs": 3,
        "cloud_ai.credit_per_alphaforge": 50,
        "cloud_ai.credit_per_fund_arb": 20,
        "reports.cloud_history": True,
    },
    "sort_order": 3,
}

# Pro Bundle: full Desktop and the broadest personal Data Hub access.
PRO_BUNDLE: PlanSeed = {
    "code": "pro_bundle",
    "name_zh": "Pro Bundle",
    "price_cny_fen": 51800,
    "billing_period": "quarter",
    "monthly_credits": 1200,
    "welcome_credits": 0,
    "description": "重度研究和批量任务",
    "entitlements": {
        "datahub.enabled": True,
        "datahub.dataset_groups": ["basic.v1", "market.v1", "finance.v1", "pro.v1"],
        "datahub.monthly_credits": 150_000,
        "datahub.rate_limit_per_minute": 600,
        "datahub.concurrent_limit": 10,
        "datahub.max_rows_per_request": 100_000,
        "datahub.history_depth_days": 7_300,
        "datahub.commercial_use": False,
        "desktop.connected_mode": True,
        "desktop.device_limit": 3,
        "cloud_ai.enabled": True,
        "cloud_ai.concurrent_jobs": 4,
        "cloud_ai.credit_per_alphaforge": 50,
        "cloud_ai.credit_per_fund_arb": 20,
        "reports.cloud_history": True,
    },
    "sort_order": 4,
}

DEFAULT_CATALOG: list[PlanSeed] = [FREE, DESKTOP_PRO, DATA_DEVELOPER, PRO_BUNDLE]


def validate_progressive_catalog(plans: list[PlanSeed]) -> None:
    """Reject personal-plan regressions before they reach the catalog API."""
    boolean_keys = ("datahub.enabled", "desktop.connected_mode", "cloud_ai.enabled", "reports.cloud_history")
    numeric_keys = (
        "datahub.monthly_credits", "datahub.rate_limit_per_minute", "datahub.concurrent_limit",
        "datahub.max_rows_per_request", "datahub.history_depth_days", "desktop.device_limit",
        "cloud_ai.concurrent_jobs",
    )
    for lower, upper in zip(plans, plans[1:]):
        for key in boolean_keys:
            if bool(lower["entitlements"].get(key)) and not bool(upper["entitlements"].get(key)):
                raise ValueError(f"{upper['code']} regresses entitlement {key}")
        lower_groups = set(lower["entitlements"].get("datahub.dataset_groups", []))
        upper_groups = set(upper["entitlements"].get("datahub.dataset_groups", []))
        if not lower_groups <= upper_groups:
            raise ValueError(f"{upper['code']} regresses entitlement datahub.dataset_groups")
        for key in numeric_keys:
            if int(upper["entitlements"].get(key, 0)) < int(lower["entitlements"].get(key, 0)):
                raise ValueError(f"{upper['code']} regresses entitlement {key}")
        if upper["monthly_credits"] < lower["monthly_credits"]:
            raise ValueError(f"{upper['code']} regresses monthly_credits")


validate_progressive_catalog(DEFAULT_CATALOG)


def to_seed_row(seed: PlanSeed) -> tuple:
    """Flatten a ``PlanSeed`` into the positional tuple stored in ``plans``."""
    import json

    return (
        seed["code"],
        seed["name_zh"],
        seed["price_cny_fen"],
        seed["billing_period"],
        seed["monthly_credits"],
        seed["welcome_credits"],
        seed["description"],
        json.dumps(seed["entitlements"], sort_keys=True, ensure_ascii=False),
        seed["sort_order"],
    )
