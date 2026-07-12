"""Bridge alert engine → existing notify senders + Redis pub/sub.

Formats alert messages with tiered severity and dispatches via the
platform-configured webhooks (feishu/dingtalk/wechat).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _format_alert(alert: dict[str, Any]) -> tuple[str, str]:
    """Return (title, markdown_body) for the notification.

    Tiered severity:
    - |premium| >= 8%  → 🚨 紧急模板
    - Otherwise         → 📊 标准模板
    """
    premium = alert.get("premium_rate", 0.0)
    abs_prem = abs(premium)
    fund_name = alert.get("fund_name", "")
    fund_code = alert.get("fund_code", "")
    price = alert.get("price", 0.0)
    nav = alert.get("nav", 0.0)
    amount = alert.get("amount", 0.0)
    triggered_at = alert.get("triggered_at", "")

    if abs_prem >= 8:
        title = f"🚨 超高溢价套利机会！{fund_name}({fund_code})"
    else:
        title = f"📊 套利提醒 — {fund_name}({fund_code})"

    direction = "溢价" if premium > 0 else "折价"
    amount_wan = amount / 10000 if amount else 0

    lines = [
        f"**{fund_name}**（{fund_code}）",
        f"折溢价率：**{premium:+.2f}%**（{direction}）",
        f"场内价格：{price:.4f} | 净值：{nav:.4f}",
        f"成交额：{amount_wan:,.0f} 万元",
        f"触发时间：{triggered_at}",
    ]
    body = "\n\n".join(lines)
    return title, body


def send_alert_notifications(triggered: list[dict[str, Any]]) -> None:
    """Send webhook notifications for all triggered alerts.

    Uses the system-level notify config (same as scheduled pushes).
    Each alert is dispatched to the webhook type specified in its rule.
    """
    if not triggered:
        return

    try:
        from src.notify.store import load_config
        from src.notify.sender import send
    except ImportError as exc:
        logger.warning("alert_notifier: notify modules not available: %s", exc)
        return

    cfg = load_config()
    platform_map = {
        "feishu": cfg.feishu,
        "dingtalk": cfg.dingtalk,
        "wechat": cfg.wechat,
    }

    for alert in triggered:
        webhook_type = alert.get("webhook_type", "wechat")
        platform_cfg = platform_map.get(webhook_type)
        if platform_cfg is None or not platform_cfg.webhook_url:
            logger.debug("alert_notifier: no webhook for %s, skipping", webhook_type)
            continue

        title, body = _format_alert(alert)
        ok, msg = send(webhook_type, platform_cfg, title, body)
        if ok:
            logger.info("alert_notifier: sent alert for %s via %s", alert.get("fund_code"), webhook_type)
        else:
            logger.warning("alert_notifier: failed to send for %s: %s", alert.get("fund_code"), msg)

    # Also publish to Redis for real-time SSE (if Redis available)
    try:
        from src.lib.redis_client import publish
        for alert in triggered:
            publish("fund:alerts", alert)
    except ImportError:
        pass  # Redis not installed, skip
    except Exception as exc:
        logger.debug("alert_notifier: redis publish skipped: %s", exc)
