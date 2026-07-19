"""通知噪声控制 — 去重 + 冷却 + 静默时段 + 最低严重度过滤。

参考 daily_stock_analysis 的 notification_noise.py，适配 Vibe-Trading 的 3 通道架构。

评估顺序（任一拦截即停止）：
  1. min_severity — 严重度不足
  2. quiet_hours — 处于静默时段
  3. dedup — 相同内容在 TTL 内已发送
  4. cooldown — 同类型通知在冷却窗口内

持久化：~/.vibe-trading/noise_state.json
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_QUIET_RE = re.compile(r"^(\d{2}:\d{2})-(\d{2}:\d{2})$")

SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}


# ─────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────

@dataclass
class NoiseConfig:
    """噪声控制配置。所有字段可选，默认值 = 当前行为（不拦截）。"""
    dedup_ttl_seconds: int = 0          # 内容去重窗口（0 = 不启用）
    cooldown_seconds: int = 0           # 同类型冷却（0 = 不启用）
    quiet_hours: str = ""               # "23:00-08:00" 格式（空 = 不启用）
    timezone: str = "Asia/Shanghai"
    min_severity: str = ""              # "info"/"warning"/"error"/"critical"（空 = 不过滤）

    def is_effective(self) -> bool:
        """是否有任何拦截规则生效。"""
        return bool(
            self.dedup_ttl_seconds > 0
            or self.cooldown_seconds > 0
            or self.quiet_hours.strip()
            or self.min_severity.strip()
        )


@dataclass
class NoiseDecision:
    should_send: bool
    reason_code: str = "ok"    # "ok" | "dedup" | "cooldown" | "quiet_hours" | "min_severity"
    dedup_key: str = ""
    cooldown_key: str = ""


# ─────────────────────────────────────────────────────────────────
# 持久化
# ─────────────────────────────────────────────────────────────────

_STATE_LOCK = threading.Lock()


def _state_path() -> Path:
    root = Path.home() / ".vibe-trading"
    root.mkdir(parents=True, exist_ok=True)
    return root / "noise_state.json"


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"dedup_expires": {}, "cooldown_expires": {}, "stats": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "dedup_expires": data.get("dedup_expires", {}),
            "cooldown_expires": data.get("cooldown_expires", {}),
            "stats": data.get("stats", {}),
        }
    except (json.JSONDecodeError, OSError):
        return {"dedup_expires": {}, "cooldown_expires": {}, "stats": {}}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────
# 核心评估
# ─────────────────────────────────────────────────────────────────

def _is_in_quiet_hours(quiet_hours: str, now: datetime) -> bool:
    """检查当前时间是否在静默时段内（支持跨午夜）。"""
    m = _QUIET_RE.match(quiet_hours.strip())
    if not m:
        return False
    try:
        start_h, start_m = map(int, m.group(1).split(":"))
        end_h, end_m = map(int, m.group(2).split(":"))
        current_minutes = now.hour * 60 + now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        if start_minutes <= end_minutes:
            # 同日时段：如 09:00-12:00
            return start_minutes <= current_minutes < end_minutes
        else:
            # 跨午夜：如 23:00-08:00
            return current_minutes >= start_minutes or current_minutes < end_minutes
    except (ValueError, IndexError):
        return False


def evaluate_noise(
    config: NoiseConfig,
    *,
    content: str,
    route_type: str = "report",
    severity: str = "info",
    now: datetime | None = None,
) -> NoiseDecision:
    """评估是否应发送通知。

    使用锁保护的原子检查+预留：读取状态和写入 in-flight 标记在同一个锁内完成，
    防止并发调用同时通过去重/冷却检查。
    """
    if not config.is_effective():
        return NoiseDecision(should_send=True, reason_code="ok")

    if now is None:
        now = datetime.now(_CST)
    now_iso = now.isoformat()

    # 1. 最低严重度（无锁，纯计算）
    if config.min_severity:
        min_rank = SEVERITY_RANK.get(config.min_severity, -1)
        cur_rank = SEVERITY_RANK.get(severity, 0)
        if cur_rank < min_rank:
            return NoiseDecision(should_send=False, reason_code="min_severity")

    # 2. 静默时段（无锁，纯计算）
    if config.quiet_hours.strip():
        if _is_in_quiet_hours(config.quiet_hours, now):
            return NoiseDecision(should_send=False, reason_code="quiet_hours")

    # 3+4. 去重+冷却：加锁检查并预留 in-flight 标记
    dedup_key = ""
    cooldown_key = ""
    inflight_reservation_seconds = 300  # 5 分钟预留

    with _STATE_LOCK:
        state = _load_state()

        # 内容去重
        if config.dedup_ttl_seconds > 0:
            dedup_key = _content_hash(content)
            expires = state["dedup_expires"].get(dedup_key, "")
            if expires and expires > now_iso:
                return NoiseDecision(should_send=False, reason_code="dedup", dedup_key=dedup_key)
            # 检查是否有 in-flight 预留
            inflight = state.get("dedup_inflight", {}).get(dedup_key, "")
            if inflight and inflight > now_iso:
                return NoiseDecision(should_send=False, reason_code="dedup", dedup_key=dedup_key)

        # 冷却
        if config.cooldown_seconds > 0:
            cooldown_key = route_type
            expires = state["cooldown_expires"].get(cooldown_key, "")
            if expires and expires > now_iso:
                return NoiseDecision(should_send=False, reason_code="cooldown", cooldown_key=cooldown_key)
            # 检查是否有 in-flight 预留
            inflight = state.get("cooldown_inflight", {}).get(cooldown_key, "")
            if inflight and inflight > now_iso:
                return NoiseDecision(should_send=False, reason_code="cooldown", cooldown_key=cooldown_key)

        # 预留 in-flight 标记，防止并发穿透
        inflight_expires = (now + timedelta(seconds=inflight_reservation_seconds)).isoformat()
        if dedup_key:
            state.setdefault("dedup_inflight", {})[dedup_key] = inflight_expires
        if cooldown_key:
            state.setdefault("cooldown_inflight", {})[cooldown_key] = inflight_expires
        _save_state(state)

    return NoiseDecision(
        should_send=True,
        reason_code="ok",
        dedup_key=dedup_key,
        cooldown_key=cooldown_key,
    )


def record_sent(
    decision: NoiseDecision,
    config: NoiseConfig,
    now: datetime | None = None,
) -> None:
    """发送成功后记录去重+冷却时间戳。"""
    if now is None:
        now = datetime.now(_CST)
    now_iso = now.isoformat()

    with _STATE_LOCK:
        state = _load_state()

        # 记录去重
        if decision.dedup_key and config.dedup_ttl_seconds > 0:
            expires = (now + timedelta(seconds=config.dedup_ttl_seconds)).isoformat()
            state["dedup_expires"][decision.dedup_key] = expires
            # 清除 in-flight 预留
            state.get("dedup_inflight", {}).pop(decision.dedup_key, None)

        # 记录冷却
        if decision.cooldown_key and config.cooldown_seconds > 0:
            expires = (now + timedelta(seconds=config.cooldown_seconds)).isoformat()
            state["cooldown_expires"][decision.cooldown_key] = expires
            # 清除 in-flight 预留
            state.get("cooldown_inflight", {}).pop(decision.cooldown_key, None)

        # 统计
        stats = state.get("stats", {})
        today = now.strftime("%Y-%m-%d")
        stats[f"sent_{today}"] = stats.get(f"sent_{today}", 0) + 1
        state["stats"] = stats

        # 清理过期的 keys（保留最近 1000 条）
        for key_type in ("dedup_expires", "cooldown_expires"):
            keys = list(state[key_type].keys())
            if len(keys) > 1000:
                sorted_keys = sorted(keys, key=lambda k: state[key_type].get(k, ""))
                for k in sorted_keys[:len(keys) - 1000]:
                    del state[key_type][k]

        _save_state(state)


def record_blocked(reason_code: str, now: datetime | None = None) -> None:
    """记录被拦截的通知（统计用）。"""
    if now is None:
        now = datetime.now(_CST)
    with _STATE_LOCK:
        state = _load_state()
        stats = state.get("stats", {})
        today = now.strftime("%Y-%m-%d")
        stats[f"blocked_{reason_code}_{today}"] = stats.get(f"blocked_{reason_code}_{today}", 0) + 1
        state["stats"] = stats
        _save_state(state)


def get_noise_stats() -> dict[str, Any]:
    """返回今日拦截/发送统计。"""
    state = _load_state()
    stats = state.get("stats", {})
    today = datetime.now(_CST).strftime("%Y-%m-%d")
    return {
        "date": today,
        "sent": stats.get(f"sent_{today}", 0),
        "blocked_dedup": stats.get(f"blocked_dedup_{today}", 0),
        "blocked_cooldown": stats.get(f"blocked_cooldown_{today}", 0),
        "blocked_quiet_hours": stats.get(f"blocked_quiet_hours_{today}", 0),
        "blocked_min_severity": stats.get(f"blocked_min_severity_{today}", 0),
        "dedup_entries": len(state.get("dedup_expires", {})),
        "cooldown_entries": len(state.get("cooldown_expires", {})),
    }
