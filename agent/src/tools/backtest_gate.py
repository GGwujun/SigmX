"""回测前置闸口（VA/VR backtest/gate 移植）：要么 Plan 要么 Refusal。

设计原则：**没有"带警告勉强跑"**——样本不足就在进引擎前拒绝，
把理由讲清楚；能跑就带着披露清单放行。闸口只读 config.json，
不跑子进程、不拉数据，判定是纯函数（交易日数用 A 股日历估算，
日历不可用时退化到周末规则）。

post-run 守卫在引擎产出后核对交易笔数——统计指标没有足够的
成交样本就没有说明力，这层警告进 gate.json 与返回信封。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

MIN_DAILY_BARS = 60        # 日线：区间交易日下限（约一个季度）
MIN_INTRADAY_BARS = 500    # 非日线：估算 K 线根数下限
MIN_TRADES_WARN = 10       # post-run：交易笔数低于此值只给警告

# 引擎能力边界披露：跑之前就要说清楚，不藏在报告脚注里
DISCLOSURES: tuple[str, ...] = (
    "A股做空信号无法预判：引擎 can_execute 直接拒单，回测只含做多腿",
    "ST/±5% 涨跌停约束未建模：触板标的的成交假设偏乐观",
    "composite/跨市场回测沿用统一引擎规则，未覆盖各市场微观差异",
    "未建模杠杆与融资成本：收益按全现金假设计算",
)

_DAILY_ALIASES = {"1d", "d", "daily", "day"}


@dataclass(frozen=True)
class Refusal:
    """闸口拒绝：带理由清单，调用方不得启动引擎。"""

    reasons: tuple[str, ...]

    def __bool__(self) -> bool:  # bool(refusal) is False
        return False

    def as_dict(self) -> dict:
        return {"ok": False, "reasons": list(self.reasons),
                "disclosures": list(DISCLOSURES)}


@dataclass
class Plan:
    """闸口放行：携带披露清单；post-run 守卫可追加 warnings。"""

    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # bool(plan) is True
        return True

    def as_dict(self) -> dict:
        return {"ok": True, "disclosures": list(DISCLOSURES),
                "warnings": list(self.warnings)}


def count_trading_days(start: str, end: str) -> int:
    """估算 [start, end] 内的 A 股交易日数（含两端）。

    用 akshare 日历（同 trade_calendar 单一事实源）；日历不可用时
    退化到周末规则——估算宁可粗也不抛错，闸口不该因为日历断网放行一切。
    """
    try:
        s, e = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except ValueError:
        return 0
    if e < s:
        return 0
    from src.data.trade_calendar import _trading_days  # noqa: SLF001 — 同源复用缓存

    cal = _trading_days(s.year)
    n = 0
    cur = s
    while cur <= e:
        if cal:
            ok = cur in cal
        else:
            ok = cur.weekday() < 5
        n += 1 if ok else 0
        cur += timedelta(days=1)
    return n


def _bars_per_day(interval: str) -> "float | None":
    """每交易日估算 K 线根数；认不出的周期返回 None（跳过根数检查）。"""
    s = str(interval or "").strip().lower()
    if not s:
        return 1.0
    if s in _DAILY_ALIASES:
        return 1.0
    if s.endswith("m") and s[:-1].isdigit():          # 1m/5m/15m/30m/60m
        return max(240.0 / int(s[:-1]), 1.0)
    if s.endswith("h") and s[:-1].isdigit():          # 1h/2h/4h
        return max(240.0 / (60 * int(s[:-1])), 1.0)
    if s in {"w", "1w", "week", "weekly"}:
        return 1.0 / 5
    if s in {"mo", "1mo", "month", "monthly", "1mth"}:
        return 1.0 / 21
    return None


def plan_backtest(run_dir: "str | Path", *,
                  trading_days=None) -> "Plan | Refusal":
    """读 run_dir/config.json 做前置判定（纯函数，不跑引擎不拉数据）。

    trading_days: 可注入的 (start, end) -> int 估算器，测试用；
    缺省用 count_trading_days（A 股日历）。
    """
    config_path = Path(run_dir) / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Refusal(("config.json 缺失或不可解析，无法过闸口",))
    if not isinstance(config, dict):
        return Refusal(("config.json 不是对象，无法过闸口",))

    reasons: list[str] = []
    codes = config.get("codes") or []
    if isinstance(codes, str):
        codes = [codes]
    if not codes:
        reasons.append("codes 为空：没有标的就没有回测")

    start, end = config.get("start_date") or "", config.get("end_date") or ""
    if start and end:
        if str(end) < str(start):
            reasons.append(f"日期倒序：end_date({end}) 早于 start_date({start})")
    else:
        start = end = ""

    estimate = trading_days or count_trading_days
    if start and end and codes:
        interval = str(config.get("interval") or "1D")
        days = int(estimate(str(start), str(end)))
        bpd = _bars_per_day(interval)
        if bpd == 1.0:
            if days < MIN_DAILY_BARS:
                reasons.append(
                    f"日线区间交易日仅 {days} 天（< {MIN_DAILY_BARS}）："
                    "样本不足，统计结论无说明力")
        elif bpd is not None and days * bpd < MIN_INTRADAY_BARS:
            bars = int(days * bpd)
            reasons.append(
                f"区间估算仅约 {bars} 根 {interval} K 线（< {MIN_INTRADAY_BARS}）："
                "样本不足，统计结论无说明力")

    if reasons:
        return Refusal(tuple(reasons))
    return Plan()


def apply_post_run(plan: Plan, run_dir: "str | Path") -> Plan:
    """post-run 守卫：交易笔数不足只降格为警告（引擎已经跑完，不推翻结果）。"""
    trades_path = Path(run_dir) / "artifacts" / "trades.csv"
    if not trades_path.is_file():
        plan.warnings.append("未产出 trades.csv：交易笔数无法核对")
        return plan
    try:
        lines = [ln for ln in trades_path.read_text(
            encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    except OSError:
        lines = []
    trades = max(len(lines) - 1, 0)  # 去表头
    if trades < MIN_TRADES_WARN:
        plan.warnings.append(
            f"交易笔数仅 {trades} 笔（< {MIN_TRADES_WARN}）："
            "胜率/盈亏比等统计指标无说明力")
    return plan


def write_gate(run_dir: "str | Path", gate: dict) -> None:
    """把闸口判定落盘 run_dir/gate.json（放行与拒绝都留审计痕迹）。"""
    path = Path(run_dir) / "gate.json"
    try:
        path.write_text(json.dumps(gate, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except OSError:
        pass  # 落盘失败不阻断主流程
