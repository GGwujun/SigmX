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

    Tiered severity (3 tiers, inspired by lof-monitor):
    - |premium| >= 8%  → 🚨 超高溢价/折价（紧急，含操作建议）
    - |premium| >= 5%  → 🔥 高溢价/折价（重要，含套利空间）
    - premium_change / nav_change → 📊 变化提醒
    - Otherwise         → 📊 套利提醒（标准）
    """
    premium = alert.get("premium_rate", 0.0)
    abs_prem = abs(premium)
    fund_name = alert.get("fund_name", "")
    fund_code = alert.get("fund_code", "")
    price = alert.get("price", 0.0)
    nav = alert.get("nav", 0.0)
    amount = alert.get("amount", 0.0)
    triggered_at = alert.get("triggered_at", "")
    prev_premium = alert.get("prev_premium")
    prev_nav = alert.get("prev_nav")

    is_premium = premium > 0
    direction = "溢价" if is_premium else "折价"
    emoji_dir = "📈" if is_premium else "📉"
    amount_wan = amount / 10000 if amount else 0

    # Detect change-based alerts
    is_change_alert = False
    change_lines: list[str] = []
    if prev_premium is not None:
        change = premium - prev_premium
        if abs(change) >= 1.0:  # significant change
            is_change_alert = True
            change_lines = [
                f"**📊 溢价率变化提醒**",
                f"前日溢价率：{prev_premium:+.2f}% → 今日：**{premium:+.2f}%**",
                f"变化：**{change:+.2f}%**",
            ]
    if prev_nav is not None and prev_nav > 0:
        nav_change = abs(nav - prev_nav) / prev_nav * 100
        if nav_change >= 1.0:
            is_change_alert = True
            change_lines.append(f"净值变化：{prev_nav:.4f} → {nav:.4f}（{nav_change:.2f}%）")

    # Calculate estimated profit for 10万 investment
    invest = 100000
    if nav > 0:
        shares = invest / nav
        if is_premium:
            est_profit = shares * price - invest - invest * 0.012 - shares * price * 0.005
        else:
            est_profit = shares * nav - invest - invest * 0.005
    else:
        est_profit = 0

    if abs_prem >= 8:
        title = f"🚨 超高{direction}套利机会！{fund_name}({fund_code})"
        lines = [
            f"## 🚨 超高{direction}警报",
            f"**{fund_name}**（{fund_code}）",
            f"{emoji_dir} 折溢价率：**{premium:+.2f}%**",
            f"场内价格：{price:.4f} | 净值：{nav:.4f}",
            f"成交额：{amount_wan:,.0f} 万元",
            f"",
            f"**💰 10万预估利润：{est_profit:+,.0f} 元**",
            f"",
            f"**⚡ 操作建议：**",
            f"{'- 场外申购 → 场内卖出（T+2交割）' if is_premium else '- 场内买入 → 赎回（T+2交割）'}",
            f"- 注意：持有<7天赎回费1.5%，≥7天降为0.5%",
            f"- 关注限购状态，限购基金溢价更持久",
        ]
    elif abs_prem >= 5:
        title = f"🔥 高{direction}提醒 — {fund_name}({fund_code})"
        lines = [
            f"## 🔥 高{direction}提醒",
            f"**{fund_name}**（{fund_code}）",
            f"{emoji_dir} 折溢价率：**{premium:+.2f}%**",
            f"场内价格：{price:.4f} | 净值：{nav:.4f}",
            f"成交额：{amount_wan:,.0f} 万元",
            f"",
            f"**💰 10万预估利润：{est_profit:+,.0f} 元**",
        ]
    elif is_change_alert:
        title = f"📊 折溢价变化提醒 — {fund_name}({fund_code})"
        lines = [
            f"## 📊 折溢价变化提醒",
            f"**{fund_name}**（{fund_code}）",
        ] + change_lines + [
            f"",
            f"当前溢价率：**{premium:+.2f}%**",
            f"场内价格：{price:.4f} | 净值：{nav:.4f}",
            f"成交额：{amount_wan:,.0f} 万元",
        ]
    else:
        title = f"📊 套利提醒 — {fund_name}({fund_code})"
        lines = [
            f"**{fund_name}**（{fund_code}）",
            f"{emoji_dir} 折溢价率：**{premium:+.2f}%**（{direction}）",
            f"场内价格：{price:.4f} | 净值：{nav:.4f}",
            f"成交额：{amount_wan:,.0f} 万元",
        ]

    lines.append(f"触发时间：{triggered_at}")
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
        from src.notify.sender import send_with_noise
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
        ok, msg = send_with_noise(
            webhook_type, platform_cfg, title, body,
            noise_cfg=cfg.noise,
            route_type="alert",
            severity="warning" if alert.get("premium_rate", 0) >= 8 else "info",
        )
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
