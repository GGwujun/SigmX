# -*- coding: utf-8 -*-
"""明日验证对账（学习 VA verification.ts 四件套防自欺设计）。

复盘汇总段输出的明日验证条件（``shortline_conditions`` 表）在 T+1 收盘数据
落定后对账：prev=读数(T)、cur=读数(T+1)，逐 metric eps 噪声阈值判方向。

四件套：
1. **eps 噪声阈值**——差值不超阈值的日常波动算 flat，不赏分不扣分；
2. **防事后**——写于 T+1 09:15 之后的条件照样对账，但 late=1 不计战绩；
3. **没数据≠判错**——cur/prev 任一缺失记 no_data，等数据补齐后重对账；
4. **基准发生率校正**——metric+direction 在历史快照对里的自然出现频率
   （样本 ≥12 才给），edge = 实际命中 − decided × expected_rate：预测
   "明天涨停家数 up"在牛市里命中率高不代表复盘有水平，基准扣除后才是 edge。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from src.data.trade_calendar import previous_trading_day

# metric → [(快照 kind, payload 路径), ...] 多级 fallback（主口径优先）
METRIC_PATHS: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "limit_up_count": (("emotion", ("promotion", "limit_up_count")),
                       ("daily", ("readings", "limit_up"))),
    "limit_down_count": (("facts", ("loss_effect", "limit_down_count")),
                         ("facts", ("loss_effect", "market_limit_down"))),
    "zt_highest_ladder": (("emotion", ("ladder_gap", "highest")),
                          ("daily", ("readings", "highest_board")),
                          ("board_ladder", ("highest",))),
    "emotion_avg": (("emotion", ("money_effect", "avg")),
                    ("daily", ("readings", "money_effect"))),
    # turnover_total_yi 特例：market_breadth_snapshot.turnover_billion
    "turnover_total_yi": (),
    "firstboard_total": (("firstboard", ("total",)),),
    "theme_count": (("themes", ("theme_count",)),),
    "break_times": (("facts", ("seal_quality", "avg_broken_times")),),
    "zb_count": (("facts", ("seal_quality", "broken_pool")),),
}

# eps 噪声阈值：|cur − prev| ≤ eps 判 flat（各 metric 的日常噪声量级）
METRIC_EPS: dict[str, float] = {
    "limit_up_count": 5.0, "limit_down_count": 5.0, "zt_highest_ladder": 1.0,
    "emotion_avg": 0.5, "turnover_total_yi": 500.0, "firstboard_total": 3.0,
    "theme_count": 2.0, "break_times": 0.5, "zb_count": 3.0,
}

BASELINE_MIN_SAMPLE = 12      # 基准发生率最小样本（低于不给 expected_rate）
LATE_CUTOFF_CST = "09:15:00"  # T+1 防事后分界（北京时间集合竞价后）


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 读数
# ---------------------------------------------------------------------------

def read_metric(market_store: Any, metric: str, trade_date: str) -> "float | None":
    """按 METRIC_PATHS 多级 fallback 读某日读数；取不到返回 None。"""
    if metric == "turnover_total_yi":
        snap = market_store.get_market_breadth_snapshot(trade_date)
        value = (snap or {}).get("turnover_billion")
        return float(value) if isinstance(value, (int, float)) else None
    for kind, path in METRIC_PATHS.get(metric, ()):
        snap = market_store.get_shortline_snapshot_fast(kind, trade_date)
        payload = (snap or {}).get("payload") or {}
        value: Any = payload
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def actual_direction(cur: "float | None", prev: "float | None", eps: float) -> "str | None":
    """噪声阈值方向判定：差值 ≤ eps 判 flat。任一缺失返回 None（没数据≠判错）。"""
    if cur is None or prev is None:
        return None
    diff = float(cur) - float(prev)
    if diff > eps:
        return "up"
    if diff < -eps:
        return "down"
    return "flat"


# ---------------------------------------------------------------------------
# 条件落表（复盘生成侧调用）
# ---------------------------------------------------------------------------

def insert_conditions(product_store: Any, review_id: str, trade_date: str,
                      conditions: "list[dict]", written_at: str) -> int:
    """复盘完成时把明日验证条件逐条落表（status=pending）。"""
    if not conditions:
        return 0
    with product_store.transaction() as conn:
        for c in conditions:
            conn.execute(
                "INSERT INTO shortline_conditions"
                "(id,trade_date,metric,direction,note,source_review_id,written_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, trade_date, c["metric"], c["direction"],
                 str(c.get("note") or "")[:200] or None, review_id, written_at),
            )
    return len(conditions)


def has_open_conditions(product_store: Any, trade_date: str) -> bool:
    """该复盘日是否还有 pending/no_data 条件（决定 worker 是否干活）。"""
    with product_store._lock:
        n = product_store._get_conn().execute(
            "SELECT COUNT(*) FROM shortline_conditions "
            "WHERE trade_date=? AND status IN ('pending','no_data')",
            (trade_date,)).fetchone()[0]
    return int(n) > 0


# ---------------------------------------------------------------------------
# 对账
# ---------------------------------------------------------------------------

def verify_trade_date(product_store: Any, market_store: Any, t1: str,
                      *, now: "str | None" = None) -> dict:
    """用 t1（验证日）读数对账 T=previous_trading_day(t1) 的 pending/no_data 条件。

    no_data 保持可重对账（数据补齐后下一轮升级为已决）；返回 remaining=仍未决数。
    """
    t = previous_trading_day(t1)
    late_cut = datetime.fromisoformat(f"{t1}T{LATE_CUTOFF_CST}+08:00")
    with product_store._lock:
        rows = product_store._get_conn().execute(
            "SELECT * FROM shortline_conditions "
            "WHERE trade_date=? AND status IN ('pending','no_data') ORDER BY rowid",
            (t,)).fetchall()
    stats = {"condition_date": t, "verified_date": t1, "checked": 0,
             "verified": 0, "mismatch": 0, "no_data": 0, "late": 0, "remaining": 0}
    for r in rows:
        metric = r["metric"]
        prev = read_metric(market_store, metric, t)
        cur = read_metric(market_store, metric, t1)
        actual = actual_direction(cur, prev, METRIC_EPS.get(metric, 0.0))
        try:
            written = datetime.fromisoformat(r["written_at"])
            if written.tzinfo is None:
                written = written.replace(tzinfo=timezone.utc)
            late = 1 if written > late_cut else 0
        except (TypeError, ValueError):
            late = 1
        if actual is None:
            status, verified = "no_data", 0
        else:
            ok = actual == r["direction"]
            status = "verified" if ok else "mismatch"
            verified = 1 if (ok and not late) else 0
        stats["checked"] += 1
        stats[status] += 1
        stats["late"] += late
        with product_store.transaction() as conn:
            conn.execute(
                "UPDATE shortline_conditions SET status=?, prev_value=?, cur_value=?, "
                "actual=?, verified=?, late=?, checked_at=? WHERE id=?",
                (status, prev, cur, actual, verified, late,
                 now or _now_iso(), r["id"]))
    with product_store._lock:
        remaining = product_store._get_conn().execute(
            "SELECT COUNT(*) FROM shortline_conditions "
            "WHERE trade_date=? AND status IN ('pending','no_data')",
            (t,)).fetchone()[0]
    stats["remaining"] = int(remaining)
    return stats


# ---------------------------------------------------------------------------
# 基准发生率与战绩
# ---------------------------------------------------------------------------

def _snapshot_dates(market_store: Any, metric: str, limit: int = 250) -> "list[str]":
    """该 metric 主口径有快照的交易日（升序）。跨日缺口时相邻快照近似 T/T+1。"""
    try:
        with market_store._readonly_conn() as conn:
            if metric == "turnover_total_yi":
                rows = conn.execute(
                    "SELECT DISTINCT trade_date FROM market_breadth_snapshot "
                    "WHERE turnover_billion IS NOT NULL "
                    "ORDER BY trade_date DESC LIMIT ?", (limit,)).fetchall()
            else:
                kind = METRIC_PATHS[metric][0][0]
                rows = conn.execute(
                    "SELECT DISTINCT trade_date FROM shortline_snapshot WHERE kind=? "
                    "ORDER BY trade_date DESC LIMIT ?", (kind, limit)).fetchall()
        return sorted(str(r["trade_date"]) for r in rows)
    except (sqlite3.Error, AttributeError, KeyError):
        return []


def baseline_rate(market_store: Any, metric: str, direction: str,
                  *, max_days: int = 250) -> "tuple[float | None, int]":
    """metric+direction 在历史相邻快照对里的自然出现频率。样本 <12 返回 (None, n)。"""
    dates = _snapshot_dates(market_store, metric, max_days)
    eps = METRIC_EPS.get(metric, 0.0)
    sample = hits = 0
    for prev_d, cur_d in zip(dates, dates[1:]):
        actual = actual_direction(read_metric(market_store, metric, cur_d),
                                  read_metric(market_store, metric, prev_d), eps)
        if actual is None:
            continue
        sample += 1
        if actual == direction:
            hits += 1
    if sample < BASELINE_MIN_SAMPLE:
        return None, sample
    return hits / sample, sample


def track_record(product_store: Any, market_store: Any, *,
                 metric: "str | None" = None, window: int = 60) -> dict:
    """近 window 个已决交易日（late 不计）的命中率 + 按 metric/方向的基准校正。"""
    q = ("SELECT * FROM shortline_conditions "
         "WHERE status IN ('verified','mismatch') AND late=0")
    params: list = []
    if metric:
        q += " AND metric=?"
        params.append(metric)
    q += " ORDER BY trade_date DESC"
    with product_store._lock:
        rows = product_store._get_conn().execute(q, params).fetchall()

    dates: list[str] = []
    seen: set[str] = set()
    for r in rows:
        d = str(r["trade_date"])
        if d not in seen:
            seen.add(d)
            dates.append(d)
    keep = set(dates[:window])
    rows = [r for r in rows if str(r["trade_date"]) in keep]

    hits = sum(1 for r in rows if r["status"] == "verified")
    out: dict = {"window_days": window, "metric": metric, "decided": len(rows),
                 "hits": hits,
                 "hit_rate": round(hits / len(rows), 4) if rows else None,
                 "by_metric": {}}
    grouped: dict[str, dict] = {}
    for r in rows:
        m = grouped.setdefault(r["metric"], {"decided": 0, "hits": 0,
                                             "by_direction": {}})
        m["decided"] += 1
        d = m["by_direction"].setdefault(r["direction"], {"decided": 0, "hits": 0})
        d["decided"] += 1
        if r["status"] == "verified":
            m["hits"] += 1
            d["hits"] += 1
    for name, m in grouped.items():
        m["hit_rate"] = round(m["hits"] / m["decided"], 4) if m["decided"] else None
        for direction, d in m["by_direction"].items():
            expected, sample = baseline_rate(market_store, name, direction)
            if expected is not None:
                d["expected_rate"] = round(expected, 4)
                d["baseline_sample"] = sample
                d["edge"] = round(d["hits"] - d["decided"] * expected, 2)
            else:
                d["expected_rate"] = None
                d["baseline_sample"] = sample
                d["edge"] = None
        out["by_metric"][name] = m
    return out


def conditions_with_status(product_store: Any, review_id: str,
                           conditions: "list[dict]") -> "list[dict]":
    """复盘响应附加各条件对账状态（行数对不上=旧复盘无对账行，原样返回）。"""
    if not conditions:
        return conditions
    with product_store._lock:
        rows = product_store._get_conn().execute(
            "SELECT status, prev_value, cur_value, actual, late, checked_at, written_at "
            "FROM shortline_conditions WHERE source_review_id=? ORDER BY rowid",
            (review_id,)).fetchall()
    if len(rows) != len(conditions):
        return conditions
    return [{**c, "verification": dict(r)} for c, r in zip(conditions, rows)]
