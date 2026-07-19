"""Alert rule engine — CRUD, evaluation, throttle.

Rules are stored as JSON in ``~/.vibe-trading/alert_rules.json``.
Notification history (last 500 triggers) in ``alert_history.json``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BASE_DIR = Path.home() / ".vibe-trading"
_RULES_PATH = _BASE_DIR / "alert_rules.json"
_HISTORY_PATH = _BASE_DIR / "alert_history.json"
_HISTORY_MAX = 500


def _ensure_dir() -> None:
    _BASE_DIR.mkdir(parents=True, exist_ok=True)


# ── Storage ──────────────────────────────────────────────────────────


def load_rules() -> list[dict[str, Any]]:
    """Load all alert rules from disk. Returns [] on missing/corrupt file."""
    try:
        if _RULES_PATH.is_file():
            data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.warning("alert_engine: failed to load rules: %s", exc)
    return []


def save_rules(rules: list[dict[str, Any]]) -> None:
    """Atomically write rules to disk (tmp + rename)."""
    _ensure_dir()
    payload = json.dumps(rules, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(_BASE_DIR), suffix=".tmp")
    try:
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, _RULES_PATH)
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_history() -> list[dict[str, Any]]:
    """Load notification history."""
    try:
        if _HISTORY_PATH.is_file():
            data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.warning("alert_engine: failed to load history: %s", exc)
    return []


def append_history(triggered: list[dict[str, Any]]) -> None:
    """Append triggered alerts to history (FIFO, capped at _HISTORY_MAX)."""
    if not triggered:
        return
    _ensure_dir()
    history = load_history()
    history.extend(triggered)
    # Keep only the most recent entries
    if len(history) > _HISTORY_MAX:
        history = history[-_HISTORY_MAX:]
    payload = json.dumps(history, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(_BASE_DIR), suffix=".tmp")
    try:
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, _HISTORY_PATH)
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)


# ── CRUD ─────────────────────────────────────────────────────────────


def create_rule(
    fund_code: str,
    fund_name: str = "",
    premium_above: float | None = None,
    premium_below: float | None = None,
    amount_above: float | None = None,
    premium_change_above: float | None = None,
    premium_change_below: float | None = None,
    nav_change_above: float | None = None,
    webhook_type: str = "wechat",
    throttle_minutes: int = 60,
) -> dict[str, Any]:
    """Create a new alert rule and persist it."""
    rule = {
        "rule_id": str(uuid.uuid4()),
        "enabled": True,
        "created_at": _now_iso(),
        "last_triggered": None,
        "trigger_count": 0,
        "fund_code": fund_code.strip(),
        "fund_name": fund_name.strip(),
        "condition": {
            "premium_above": premium_above,
            "premium_below": premium_below,
            "amount_above": amount_above,
            "premium_change_above": premium_change_above,
            "premium_change_below": premium_change_below,
            "nav_change_above": nav_change_above,
        },
        "notification": {
            "webhook_type": webhook_type,
            "throttle_minutes": max(1, throttle_minutes),
        },
    }
    rules = load_rules()
    rules.append(rule)
    save_rules(rules)
    logger.info("alert_engine: created rule %s for %s", rule["rule_id"], fund_code)
    return rule


def delete_rule(rule_id: str) -> bool:
    """Delete a rule by ID. Returns True if found and deleted."""
    rules = load_rules()
    new_rules = [r for r in rules if r.get("rule_id") != rule_id]
    if len(new_rules) == len(rules):
        return False
    save_rules(new_rules)
    return True


def toggle_rule(rule_id: str) -> dict[str, Any] | None:
    """Toggle enabled status. Returns the updated rule or None if not found."""
    rules = load_rules()
    for r in rules:
        if r.get("rule_id") == rule_id:
            r["enabled"] = not r.get("enabled", True)
            save_rules(rules)
            return r
    return None


def update_rule(rule_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Update rule fields. Returns updated rule or None."""
    rules = load_rules()
    for r in rules:
        if r.get("rule_id") == rule_id:
            # Update top-level fields
            for key in ("fund_code", "fund_name"):
                if key in updates:
                    r[key] = updates[key]
            # Update condition
            if "condition" in updates and isinstance(updates["condition"], dict):
                r.setdefault("condition", {}).update(updates["condition"])
            # Update notification
            if "notification" in updates and isinstance(updates["notification"], dict):
                r.setdefault("notification", {}).update(updates["notification"])
            save_rules(rules)
            return r
    return None


# ── Evaluation ───────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_throttled(rule: dict[str, Any]) -> bool:
    """True if the rule was triggered recently and throttle hasn't expired."""
    last = rule.get("last_triggered")
    if not last:
        return False
    throttle_min = rule.get("notification", {}).get("throttle_minutes", 60)
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
        return elapsed < throttle_min
    except (ValueError, TypeError):
        return False


def check_condition(fund: dict[str, Any], rule: dict[str, Any],
                    prev_premium: float | None = None,
                    prev_nav: float | None = None) -> bool:
    """Check if a fund matches the rule's conditions.

    Args:
        fund: Current fund data dict
        rule: Alert rule dict
        prev_premium: Previous day's premium rate (for change detection)
        prev_nav: Previous day's NAV (for change detection)
    """
    cond = rule.get("condition", {})
    premium = float(fund.get("premium_rate") or 0.0)
    amount = float(fund.get("amount") or 0.0)
    nav = float(fund.get("nav") or 0.0)

    # Static thresholds
    premium_above = cond.get("premium_above")
    if premium_above is not None and premium < float(premium_above):
        return False

    premium_below = cond.get("premium_below")
    if premium_below is not None and premium > float(premium_below):
        return False

    amount_above = cond.get("amount_above")
    if amount_above is not None and amount < float(amount_above):
        return False

    # Premium rate change (日环比)
    premium_change_above = cond.get("premium_change_above")
    if premium_change_above is not None:
        if prev_premium is None:
            return False  # 无法评估变化条件，不触发
        change = premium - prev_premium
        if change < float(premium_change_above):
            return False

    premium_change_below = cond.get("premium_change_below")
    if premium_change_below is not None:
        if prev_premium is None:
            return False  # 无法评估变化条件，不触发
        change = premium - prev_premium
        if change > float(premium_change_below):
            return False

    # NAV change (净值跳变)
    nav_change_above = cond.get("nav_change_above")
    if nav_change_above is not None:
        if prev_nav is None or prev_nav <= 0:
            return False  # 无法评估净值变化，不触发
        nav_change_pct = abs(nav - prev_nav) / prev_nav * 100
        if nav_change_pct < float(nav_change_above):
            return False

    return True


def check_all_rules(funds_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluate all enabled rules against current fund data.

    Returns list of triggered alert dicts (ready for notification + history).
    Updates last_triggered and trigger_count in the rules file.
    Automatically fetches historical data for change-detection conditions.
    """
    rules = load_rules()
    triggered: list[dict[str, Any]] = []
    rules_modified = False

    # 只对有 change-detection 规则的基金查历史（避免对所有基金无意义查询）
    change_rule_codes = {
        r.get("fund_code", "").strip()
        for r in rules
        if r.get("enabled", True) and any(
            r.get("condition", {}).get(k) is not None
            for k in ("premium_change_above", "premium_change_below", "nav_change_above")
        )
    }

    # Build historical lookup: fund_code → {prev_premium, prev_nav}
    history_map: dict[str, dict] = {}
    if change_rule_codes:
        try:
            from src.data.market_store import get_market_store
            store = get_market_store()
            if store is not None:
                for code in change_rule_codes:
                    if not code:
                        continue
                    try:
                        hist = store.get_fund_premium_history(code, days=2)
                        if hist and len(hist) >= 2:
                            prev = hist[-2]  # second most recent
                            history_map[code] = {
                                "prev_premium": float(prev.get("premium_rate") or 0.0),
                                "prev_nav": float(prev.get("nav") or 0.0),
                            }
                    except Exception:
                        continue
        except Exception:
            logger.debug("alert_engine: failed to load historical data", exc_info=True)

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if is_throttled(rule):
            continue

        fund_code = rule.get("fund_code", "").strip()
        if not fund_code:
            continue

        # Find matching fund
        fund = None
        for f in funds_data:
            if str(f.get("code", "")).strip() == fund_code:
                fund = f
                break

        if fund is None:
            continue

        # Get historical data for this fund
        hist = history_map.get(fund_code, {})
        if not check_condition(fund, rule,
                               prev_premium=hist.get("prev_premium"),
                               prev_nav=hist.get("prev_nav")):
            continue

        # Rule triggered!
        rule["last_triggered"] = _now_iso()
        rule["trigger_count"] = rule.get("trigger_count", 0) + 1
        rules_modified = True

        alert = {
            "rule_id": rule["rule_id"],
            "fund_code": fund_code,
            "fund_name": rule.get("fund_name") or fund.get("name", ""),
            "premium_rate": float(fund.get("premium_rate") or 0.0),
            "amount": float(fund.get("amount") or 0.0),
            "price": float(fund.get("price") or 0.0),
            "nav": float(fund.get("nav") or 0.0),
            "prev_premium": hist.get("prev_premium"),
            "prev_nav": hist.get("prev_nav"),
            "webhook_type": rule.get("notification", {}).get("webhook_type", "wechat"),
            "triggered_at": _now_iso(),
        }
        triggered.append(alert)

    if rules_modified:
        save_rules(rules)

    if triggered:
        logger.info("alert_engine: %d rules triggered", len(triggered))

    return triggered
