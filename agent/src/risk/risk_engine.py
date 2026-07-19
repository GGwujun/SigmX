"""8 层量化风控检查引擎。

每层是独立的纯函数，返回 RiskCheckResult。全部不执行交易，仅产出告警/评分。
参考 Easyup-Platform 的 monitor.py，适配 Vibe-Trading 分析平台。

层级（按优先级）：
  L1: 组合回撤熔断     — 峰值回撤 ≥10% → critical
  L2: 移动止盈           — 浮盈≥10%后回落50% → critical
  L3: ATR 动态止损       — 止损 = -atr_mult × 20d ATR → warning
  L4: 分级止盈           — TP1/TP2/TP3 分级提醒 → info/warning
  L5: 防踩踏+指数熔断    — ≥50%持仓跌>3% 或 上证跌>3% → critical
  L6: 持仓天数管理       — ≥20天未达TP1 → warning
  L7: 跌停封板检测       — 跌停+卖盘封死 → critical
  L8: 持仓相关性         — 任意两仓相关≥0.7 → warning
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))


# ─────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────

@dataclass
class RiskCheckResult:
    layer: int
    name: str
    triggered: bool
    severity: str           # "info" | "warning" | "critical"
    message: str
    details: dict = field(default_factory=dict)
    action: str = "alert"   # "alert" | "warn" | "suggest_sell"


@dataclass
class RiskReport:
    trade_date: str
    regime: str
    checks: list[RiskCheckResult] = field(default_factory=list)
    portfolio_health_score: float = 100.0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date,
            "regime": self.regime,
            "checks": [
                {
                    "layer": c.layer,
                    "name": c.name,
                    "triggered": c.triggered,
                    "severity": c.severity,
                    "message": c.message,
                    "details": c.details,
                    "action": c.action,
                }
                for c in self.checks
            ],
            "portfolio_health_score": round(self.portfolio_health_score, 1),
            "summary": self.summary,
        }


def _pass(layer: int, name: str) -> RiskCheckResult:
    return RiskCheckResult(layer=layer, name=name, triggered=False,
                           severity="info", message="✅ 正常")


# ─────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────

def _calc_atr(bars: list[dict], period: int = 20) -> float:
    """计算 ATR（Average True Range）。"""
    if len(bars) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = bars[i].get("high", 0)
        l = bars[i].get("low", 0)
        pc = bars[i - 1].get("close", 0)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return float(np.mean(trs)) if trs else 0.0
    return float(np.mean(trs[-period:]))


def _get_current_price(store, symbol: str) -> tuple[float, dict]:
    """获取最新价格和行情数据。返回 (price, quote_dict)。"""
    quote = store.get_latest_realtime_quote(symbol)
    if quote:
        price = quote.get("price", 0) or quote.get("close", 0) or 0
        return float(price), quote
    return 0.0, {}


def _get_bars(store, symbol: str, days: int = 30) -> list[dict]:
    """获取历史 K 线。"""
    df = store.get_daily_bars(symbol, days=days)
    if df is None or df.empty:
        return []
    return df.reset_index().to_dict("records")


def _trading_days_between(date_str: str, now=None) -> int:
    """粗略估计交易日天数（忽略节假日，用工作日近似）。"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        if now is None:
            now = datetime.now(_CST)
        delta = (now - d.replace(tzinfo=_CST)).days
        return max(0, int(delta * 5 / 7))  # 工作日近似
    except Exception:
        return 0


def _calc_price_limit(code: str, pre_close: float) -> tuple[float, float]:
    """计算涨跌停价。"""
    if not pre_close:
        return 0, 0
    # 判断板块
    prefix = code[:3] if code else ""
    if prefix in ("300", "301"):
        pct = 0.20  # 创业板
    elif prefix in ("688", "689"):
        pct = 0.20  # 科创板
    else:
        pct = 0.10  # 主板
    limit_up = round(pre_close * (1 + pct), 2)
    limit_down = round(pre_close * (1 - pct), 2)
    return limit_up, limit_down


# ─────────────────────────────────────────────────────────────────
# 8 层检查
# ─────────────────────────────────────────────────────────────────

def check_l1_drawdown_circuit_breaker(
    positions: list[dict], store, regime_params: dict
) -> RiskCheckResult:
    """L1: 组合回撤熔断 — 峰值回撤 ≥10% → critical。"""
    total_cost = 0.0
    total_value = 0.0
    for pos in positions:
        cost = pos.get("avg_cost", 0) or 0
        qty = pos.get("quantity", 0) or 0
        if cost <= 0 or qty <= 0:
            continue
        price, _ = _get_current_price(store, pos["symbol"])
        if price <= 0:
            continue
        total_cost += cost * qty
        total_value += price * qty

    if total_cost <= 0:
        return _pass(1, "组合回撤熔断")

    drawdown = (total_cost - total_value) / total_cost
    if drawdown >= 0.10:
        return RiskCheckResult(
            layer=1, name="组合回撤熔断", triggered=True,
            severity="critical",
            message=f"🔴 组合回撤 {drawdown:.1%} ≥ 10% 阈值，建议减仓",
            details={"drawdown_pct": round(drawdown * 100, 2), "threshold": 10},
            action="suggest_sell",
        )
    return _pass(1, "组合回撤熔断")


def check_l2_trailing_stop_profit(
    position: dict, store, regime_params: dict
) -> RiskCheckResult:
    """L2: 移动止盈 — 浮盈≥10%后回落50% → critical。"""
    avg_cost = position.get("avg_cost", 0) or 0
    peak_pct = position.get("peak_profit_pct", 0) or 0
    if avg_cost <= 0 or peak_pct < 0.10:
        return _pass(2, "移动止盈")

    price, _ = _get_current_price(store, position["symbol"])
    if price <= 0:
        return _pass(2, "移动止盈")

    current_profit = (price - avg_cost) / avg_cost
    if current_profit < peak_pct * 0.5:
        return RiskCheckResult(
            layer=2, name="移动止盈", triggered=True,
            severity="critical",
            message=f"🔴 {position.get('name', position['symbol'])} "
                    f"浮盈从 {peak_pct:.1%} 回落至 {current_profit:.1%}（回落超50%），建议止盈",
            details={
                "symbol": position["symbol"],
                "peak_profit": round(peak_pct * 100, 2),
                "current_profit": round(current_profit * 100, 2),
                "retrace_ratio": round(current_profit / peak_pct, 2) if peak_pct else 0,
            },
            action="suggest_sell",
        )
    return _pass(2, "移动止盈")


def check_l3_atr_stop_loss(
    position: dict, store, regime_params: dict
) -> RiskCheckResult:
    """L3: ATR 动态止损 — 止损 = avg_cost - atr_mult × 20d ATR → warning。"""
    avg_cost = position.get("avg_cost", 0) or 0
    if avg_cost <= 0:
        return _pass(3, "ATR动态止损")

    bars = _get_bars(store, position["symbol"], 30)
    if len(bars) < 20:
        return _pass(3, "ATR动态止损")

    atr = _calc_atr(bars, 20)
    if atr <= 0:
        return _pass(3, "ATR动态止损")

    atr_mult = regime_params.get("atr_mult", 1.5)
    stop_price = avg_cost - atr_mult * atr

    price, _ = _get_current_price(store, position["symbol"])
    if price <= 0:
        return _pass(3, "ATR动态止损")

    if price <= stop_price:
        return RiskCheckResult(
            layer=3, name="ATR动态止损", triggered=True,
            severity="warning",
            message=f"⚠️ {position.get('name', position['symbol'])} "
                    f"当前价 {price:.2f} ≤ ATR止损价 {stop_price:.2f}",
            details={
                "symbol": position["symbol"],
                "current_price": price,
                "stop_price": round(stop_price, 2),
                "atr": round(atr, 3),
                "atr_mult": atr_mult,
            },
            action="suggest_sell",
        )

    # 距离止损 < 2% 也预警
    distance_pct = (price - stop_price) / price if price > 0 else 0
    if distance_pct < 0.02:
        return RiskCheckResult(
            layer=3, name="ATR动态止损", triggered=True,
            severity="info",
            message=f"ℹ️ {position.get('name', position['symbol'])} "
                    f"距ATR止损仅 {distance_pct:.1%}",
            details={"distance_pct": round(distance_pct * 100, 2)},
        )
    return _pass(3, "ATR动态止损")


def check_l4_tiered_take_profit(
    position: dict, store, regime_params: dict
) -> RiskCheckResult:
    """L4: 分级止盈 — TP1/TP2/TP3 分级提醒。"""
    avg_cost = position.get("avg_cost", 0) or 0
    if avg_cost <= 0:
        return _pass(4, "分级止盈")

    tp1 = regime_params.get("tp1", 0.15)
    tp2 = regime_params.get("tp2", 0.25)
    tp3 = regime_params.get("tp3", 0.35)
    tp_triggered = set(position.get("tp_triggered", []))

    price, _ = _get_current_price(store, position["symbol"])
    if price <= 0:
        return _pass(4, "分级止盈")

    profit_pct = (price - avg_cost) / avg_cost

    # 从高到低检查
    for level, tp_val, label in [(3, tp3, "TP3"), (2, tp2, "TP2"), (1, tp1, "TP1")]:
        if profit_pct >= tp_val and level not in tp_triggered:
            sev = "warning" if level >= 2 else "info"
            return RiskCheckResult(
                layer=4, name="分级止盈", triggered=True,
                severity=sev,
                message=f"{'🟡' if sev == 'warning' else 'ℹ️'} "
                        f"{position.get('name', position['symbol'])} "
                        f"浮盈 {profit_pct:.1%} 达到 {label}（{tp_val:.0%}），建议减仓1/3",
                details={
                    "symbol": position["symbol"],
                    "profit_pct": round(profit_pct * 100, 2),
                    "level": label,
                    "threshold": round(tp_val * 100, 1),
                },
            )
    return _pass(4, "分级止盈")


def check_l5_stampede_and_index(
    positions: list[dict], store, regime_params: dict
) -> RiskCheckResult:
    """L5: 防踩踏 + 指数熔断。"""
    # 指数检查：上证跌 > 3%
    index_quote = store.get_latest_realtime_quote("000001.SH")
    if not index_quote:
        index_quote = store.get_latest_realtime_quote("sh000001")
    if index_quote:
        idx_chg = index_quote.get("rise_rate", 0) or index_quote.get("pct_chg", 0) or 0
        if float(idx_chg) <= -3.0:
            return RiskCheckResult(
                layer=5, name="指数熔断", triggered=True,
                severity="critical",
                message=f"🔴 上证指数跌幅 {float(idx_chg):.2f}% ≤ -3%，暂停买入",
                details={"index_change": float(idx_chg)},
                action="warn",
            )

    # 踩踏检查：≥50%持仓跌>3%
    if not positions:
        return _pass(5, "防踩踏检测")

    dropping = 0
    total = 0
    for pos in positions:
        price, quote = _get_current_price(store, pos["symbol"])
        if price <= 0:
            continue
        total += 1
        chg = quote.get("rise_rate", 0) or quote.get("pct_chg", 0) or 0
        if float(chg) <= -3.0:
            dropping += 1

    if total > 0 and dropping / total >= 0.5:
        return RiskCheckResult(
            layer=5, name="防踩踏检测", triggered=True,
            severity="critical",
            message=f"🔴 {dropping}/{total} 只持仓跌超3%（≥50%），暂停买入",
            details={"dropping": dropping, "total": total, "ratio": round(dropping / total, 2)},
            action="warn",
        )
    return _pass(5, "防踩踏检测")


def check_l6_max_holding_period(
    position: dict, store, regime_params: dict
) -> RiskCheckResult:
    """L6: 持仓天数管理 — ≥20天未达TP1 → warning。"""
    buy_date = position.get("buy_date")
    if not buy_date:
        return _pass(6, "持仓天数")

    avg_cost = position.get("avg_cost", 0) or 0
    tp1 = regime_params.get("tp1", 0.15)
    tp_triggered = set(position.get("tp_triggered", []))
    if 1 in tp_triggered:
        return _pass(6, "持仓天数")  # 已达 TP1，不检查

    days = _trading_days_between(buy_date)
    if days >= 20:
        return RiskCheckResult(
            layer=6, name="持仓天数", triggered=True,
            severity="warning",
            message=f"⚠️ {position.get('name', position['symbol'])} "
                    f"持仓 {days} 天未达 TP1，建议审视持仓逻辑",
            details={"symbol": position["symbol"], "holding_days": days, "tp1": round(tp1 * 100, 1)},
        )
    return _pass(6, "持仓天数")


def check_l7_limit_down(
    position: dict, store, regime_params: dict
) -> RiskCheckResult:
    """L7: 跌停封板检测 — 跌停+卖盘封死 → critical。"""
    price, quote = _get_current_price(store, position["symbol"])
    if price <= 0:
        return _pass(7, "跌停封板")

    pre_close = quote.get("pre_close", 0) or 0
    if pre_close <= 0:
        return _pass(7, "跌停封板")

    _, limit_down = _calc_price_limit(position["symbol"], pre_close)
    if limit_down <= 0:
        return _pass(7, "跌停封板")

    # 价格触及跌停
    if price <= limit_down * 1.001:
        return RiskCheckResult(
            layer=7, name="跌停封板", triggered=True,
            severity="critical",
            message=f"🔴 {position.get('name', position['symbol'])} "
                    f"触及跌停价 {limit_down:.2f}，可能无法卖出",
            details={
                "symbol": position["symbol"],
                "current_price": price,
                "limit_down": limit_down,
            },
            action="warn",
        )
    return _pass(7, "跌停封板")


def check_l8_position_correlation(
    positions: list[dict], store, regime_params: dict
) -> RiskCheckResult:
    """L8: 持仓相关性 — 任意两仓 20d 相关系数 ≥0.7 → warning。"""
    if len(positions) < 2:
        return _pass(8, "持仓相关性")

    # 获取每只持仓的 20 日收益率
    returns_map: dict[str, np.ndarray] = {}
    for pos in positions:
        bars = _get_bars(store, pos["symbol"], 25)
        if len(bars) < 20:
            continue
        closes = [b.get("close", 0) for b in bars if b.get("close")]
        if len(closes) < 20:
            continue
        closes_arr = np.array(closes[-21:], dtype=float)
        if len(closes_arr) < 2:
            continue
        rets = np.diff(closes_arr) / closes_arr[:-1]
        returns_map[pos["symbol"]] = rets

    if len(returns_map) < 2:
        return _pass(8, "持仓相关性")

    # 计算相关系数矩阵
    symbols = list(returns_map.keys())
    max_warn_pair = None
    max_corr = 0.0

    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            r1 = returns_map[symbols[i]]
            r2 = returns_map[symbols[j]]
            min_len = min(len(r1), len(r2))
            if min_len < 10:
                continue
            corr = float(np.corrcoef(r1[-min_len:], r2[-min_len:])[0, 1])
            if abs(corr) >= 0.7 and abs(corr) > abs(max_corr):
                max_corr = corr
                max_warn_pair = (symbols[i], symbols[j])

    if max_warn_pair:
        return RiskCheckResult(
            layer=8, name="持仓相关性", triggered=True,
            severity="warning",
            message=f"⚠️ {max_warn_pair[0]} 与 {max_warn_pair[1]} "
                    f"20日相关系数 {max_corr:.2f}，建议分散持仓",
            details={
                "pair": list(max_warn_pair),
                "correlation": round(max_corr, 3),
            },
        )
    return _pass(8, "持仓相关性")


# ─────────────────────────────────────────────────────────────────
# 持仓健康评分
# ─────────────────────────────────────────────────────────────────

def compute_health_score(
    positions: list[dict], store, regime_params: dict
) -> float:
    """计算持仓健康评分（0-100），参考 easyup v3 校准。"""
    if not positions:
        return 100.0

    score = 100.0
    n = len(positions)

    for pos in positions:
        avg_cost = pos.get("avg_cost", 0) or 0
        if avg_cost <= 0:
            continue

        price, quote = _get_current_price(store, pos["symbol"])
        if price <= 0:
            continue

        profit_pct = (price - avg_cost) / avg_cost

        # 浮盈加分
        if profit_pct >= 0.10:
            score += 5 / n
        elif profit_pct >= 0.05:
            score += 2 / n

        # 浮亏扣分
        if profit_pct < 0:
            penalty = min(abs(profit_pct) * 5, 40) / n
            score -= penalty

        # 量能萎缩
        bars = _get_bars(store, pos["symbol"], 25)
        if len(bars) >= 20:
            vol5 = np.mean([b.get("volume", 0) for b in bars[-5:]])
            vol20 = np.mean([b.get("volume", 0) for b in bars[-20:]])
            if vol20 > 0 and vol5 / vol20 < 0.6:
                score -= 20 / n

        # MA5 下降 / 空头排列
        if len(bars) >= 20:
            closes = [b.get("close", 0) for b in bars]
            if len(closes) >= 20:
                ma5 = np.mean(closes[-5:])
                ma10 = np.mean(closes[-10:])
                ma20 = np.mean(closes[-20:])
                if ma5 < ma10 < ma20:
                    score -= 10 / n  # 空头排列
                elif ma5 < np.mean(closes[-6:-1]) if len(closes) >= 6 else False:
                    score -= 15 / n  # MA5 下降

    return max(0.0, min(100.0, score))


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────

def run_all_checks(store, trade_date: str | None = None) -> RiskReport:
    """运行全部 8 层风控检查，返回 RiskReport。"""
    from src.data.schedule_store import get_positions
    from src.risk.regime_classifier import REGIME_PARAMS

    _now = datetime.now(_CST)
    if trade_date is None:
        trade_date = _now.strftime("%Y-%m-%d")

    # 获取当前 regime
    latest_regime = store.get_latest_regime()
    regime = latest_regime.get("regime", "range") if latest_regime else "range"
    regime_params = REGIME_PARAMS.get(regime, REGIME_PARAMS["range"])

    # 获取持仓
    positions = get_positions()

    checks: list[RiskCheckResult] = []

    if not positions:
        return RiskReport(
            trade_date=trade_date,
            regime=regime,
            checks=[],
            portfolio_health_score=100.0,
            summary="无持仓数据，请在跟踪看板中填写持仓信息",
        )

    # L1: 组合回撤（全持仓级别）
    checks.append(check_l1_drawdown_circuit_breaker(positions, store, regime_params))

    # L5: 防踩踏 + 指数（全持仓级别）
    checks.append(check_l5_stampede_and_index(positions, store, regime_params))

    # L8: 持仓相关性（全持仓级别）
    checks.append(check_l8_position_correlation(positions, store, regime_params))

    # 逐持仓检查 L2-L4, L6-L7
    for pos in positions:
        checks.append(check_l2_trailing_stop_profit(pos, store, regime_params))
        checks.append(check_l3_atr_stop_loss(pos, store, regime_params))
        checks.append(check_l4_tiered_take_profit(pos, store, regime_params))
        checks.append(check_l6_max_holding_period(pos, store, regime_params))
        checks.append(check_l7_limit_down(pos, store, regime_params))

    # 更新 peak_profit_pct
    for pos in positions:
        avg_cost = pos.get("avg_cost", 0) or 0
        if avg_cost <= 0:
            continue
        price, _ = _get_current_price(store, pos["symbol"])
        if price <= 0:
            continue
        current_pct = (price - avg_cost) / avg_cost
        old_peak = pos.get("peak_profit_pct", 0) or 0
        if current_pct > old_peak:
            from src.data.schedule_store import update_position_fields
            update_position_fields(pos["task_id"], peak_profit_pct=current_pct)

    # 健康评分
    health = compute_health_score(positions, store, regime_params)

    # 汇总
    triggered = [c for c in checks if c.triggered]
    critical_count = sum(1 for c in triggered if c.severity == "critical")
    warning_count = sum(1 for c in triggered if c.severity == "warning")

    if critical_count > 0:
        summary = f"🔴 {critical_count} 项严重风险 + {warning_count} 项警告"
    elif warning_count > 0:
        summary = f"⚠️ {warning_count} 项风险警告"
    else:
        summary = "✅ 全部风控检查通过"

    return RiskReport(
        trade_date=trade_date,
        regime=regime,
        checks=checks,
        portfolio_health_score=health,
        summary=summary,
    )
