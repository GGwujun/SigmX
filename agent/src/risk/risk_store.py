"""风控事件持久化存储 (~/.vibe-trading/risk_events.json)。

跟随 alert_engine.py 的 JSON 文件存储模式。
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))
_MAX_EVENTS = 500  # 最多保留 500 条事件
_LOCK = threading.Lock()


def _events_path() -> Path:
    root = Path.home() / ".vibe-trading"
    root.mkdir(parents=True, exist_ok=True)
    return root / "risk_events.json"


def _atomic_write(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _new_event_id() -> str:
    return f"re-{int(datetime.now(_CST).timestamp())}-{secrets.token_hex(3)}"


def load_events() -> list[dict[str, Any]]:
    """返回所有风控事件，最新在前。"""
    path = _events_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_event(
    layer: int,
    severity: str,
    message: str,
    *,
    code: str | None = None,
    details: dict | None = None,
    trade_date: str | None = None,
) -> dict[str, Any]:
    """保存一条风控事件。

    当天去重：同一 (trade_date, layer, code) 已有事件则替换为最新一条，
    避免长期深套/未达 TP1 的持仓逐日刷屏淹没新风险。
    """
    with _LOCK:
        events = load_events()
        today = trade_date or datetime.now(_CST).strftime("%Y-%m-%d")
        event = {
            "event_id": _new_event_id(),
            "trade_date": today,
            "layer": layer,
            "severity": severity,
            "code": code,
            "message": message,
            "details": details or {},
            "notified": False,
            "created_at": datetime.now(_CST).isoformat(),
        }
        # 移除当天同 (layer, code) 的旧事件，只保留本次最新
        events = [
            e for e in events
            if not (
                e.get("trade_date") == today
                and e.get("layer") == layer
                and e.get("code") == code
            )
        ]
        events.insert(0, event)
        # 裁剪
        if len(events) > _MAX_EVENTS:
            events = events[:_MAX_EVENTS]
        _atomic_write(_events_path(), events)
        return event


def save_risk_report(report_dict: dict) -> None:
    """将 RiskReport 中所有 triggered 的检查保存为事件。"""
    for check in report_dict.get("checks", []):
        if check.get("triggered"):
            save_event(
                layer=check["layer"],
                severity=check["severity"],
                message=check["message"],
                code=check.get("details", {}).get("symbol"),
                details=check.get("details", {}),
                trade_date=report_dict.get("trade_date"),
            )


def get_risk_events(
    days: int = 30,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """返回风控事件，支持按严重度过滤。"""
    events = load_events()

    # 日期过滤
    cutoff = (datetime.now(_CST) - timedelta(days=days)).strftime("%Y-%m-%d")
    events = [e for e in events if e.get("created_at", "")[:10] >= cutoff]

    # 严重度过滤
    if severity:
        events = [e for e in events if e.get("severity") == severity]

    return events[:limit]


def get_latest_health_score() -> float | None:
    """返回最近一次保存的健康评分。"""
    # 健康评分存在 risk_events 的 meta 中
    path = _events_path().with_suffix(".meta.json")
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("health_score")
    except (json.JSONDecodeError, OSError):
        return None


def save_health_score(score: float) -> None:
    """保存最新健康评分。"""
    path = _events_path().with_suffix(".meta.json")
    _atomic_write(path, {
        "health_score": round(score, 1),
        "updated_at": datetime.now(_CST).isoformat(),
    })
