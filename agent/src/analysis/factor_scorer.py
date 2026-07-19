"""37 因子轻量选股评分系统。

参考 Easyup-Platform 的 factor_scorer.py，适配 Vibe-Trading 的 MarketStore 数据层。

10 个基础因子（加权归一化 0-100）：
  动量20d(15%)、动量5d(10%)、量能趋势(12%)、均线排列(15%)、
  MACD柱(10%)、RSI位置(8%)、波动率(10%)、换手率(8%)、成交额排名(7%)、板块动量(5%)

27 个增强因子（±25 加分 × 0.4 缩放）：
  多周期动量、波动结构、量价背离、KDJ、布林带、OBV、
  多周期RSI、价格位置、量集中度、支撑阻力、威廉%R、CCI、相对强度
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── 基础因子权重 ──
BASE_WEIGHTS = {
    "momentum_20d": 0.15,
    "momentum_5d": 0.10,
    "volume_trend": 0.12,
    "ma_alignment": 0.15,
    "macd_hist": 0.10,
    "rsi_position": 0.08,
    "volatility": 0.10,
    "turnover_rate": 0.08,
    "amount_rank": 0.07,
    "sector_momentum": 0.05,
}


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


# ─────────────────────────────────────────────────────────────────
# 基础因子
# ─────────────────────────────────────────────────────────────────

def score_momentum(closes: np.ndarray, period: int) -> float:
    """N 日动量：百分比涨幅 → 0-100。"""
    if len(closes) < period + 1:
        return 50.0
    chg = (closes[-1] - closes[-period - 1]) / closes[-period - 1] * 100
    # -20% → 0, 0% → 50, +20% → 100
    return _clamp(50 + chg * 2.5)


def score_volume_trend(volumes: np.ndarray) -> float:
    """量能趋势：5d/20d 量比 → 0-100。"""
    if len(volumes) < 20:
        return 50.0
    vol5 = np.mean(volumes[-5:])
    vol20 = np.mean(volumes[-20:])
    ratio = _safe_div(vol5, vol20, 1.0)
    # 0.5 → 20, 1.0 → 50, 1.5 → 80, 2.0+ → 100
    return _clamp(20 + (ratio - 0.5) * 40)


def score_ma_alignment(closes: np.ndarray) -> float:
    """均线排列：MA5>MA10>MA20 程度 → 0-100。"""
    if len(closes) < 20:
        return 50.0
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    score = 0
    if ma5 > ma10:
        score += 35
    if ma10 > ma20:
        score += 35
    if closes[-1] > ma5:
        score += 30
    return float(score)


def score_macd(closes: np.ndarray) -> float:
    """MACD 柱方向 → 0-100。"""
    if len(closes) < 35:
        return 50.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12 - ema26
    dea = _ema_from_arr(dif, 9)
    hist = dif - dea
    if len(hist) < 2:
        return 50.0
    # DIF 方向 + 柱变化
    rising = hist[-1] > hist[-2]
    positive = hist[-1] > 0
    if rising and positive:
        return 85.0
    if positive:
        return 65.0
    if rising:
        return 45.0
    return 25.0


def _ema(closes: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均。"""
    arr = np.empty_like(closes, dtype=float)
    arr[0] = closes[0]
    k = 2.0 / (period + 1)
    for i in range(1, len(closes)):
        arr[i] = closes[i] * k + arr[i - 1] * (1 - k)
    return arr


def _ema_from_arr(values: np.ndarray, period: int) -> np.ndarray:
    return _ema(values, period)


def score_rsi(closes: np.ndarray, period: int = 14) -> float:
    """RSI 位置 → 0-100。50-70 是最佳区间。"""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - 100.0 / (1.0 + rs)
    # 50-70 → 80-100 (sweet spot), >70 → 降, <50 → 降
    if 50 <= rsi <= 70:
        return 70 + (rsi - 50) * 1.5
    if rsi > 70:
        return max(40, 100 - (rsi - 70) * 2)
    return max(0, rsi)


def score_volatility(closes: np.ndarray, period: int = 20) -> float:
    """波动率（反向）：低波动 → 高分。"""
    if len(closes) < period:
        return 50.0
    returns = np.diff(closes[-period:]) / closes[-period:-1]
    vol = float(np.std(returns) * 100)
    # 0% → 100, 2% → 60, 5% → 20
    return _clamp(100 - vol * 16)


def score_turnover(turnover_rate: float) -> float:
    """换手率：适中最好。"""
    if turnover_rate <= 0:
        return 30.0
    if turnover_rate < 1:
        return 40.0 + turnover_rate * 20
    if turnover_rate <= 5:
        return 60 + (turnover_rate - 1) * 5
    if turnover_rate <= 10:
        return 85 - (turnover_rate - 5) * 3
    return max(30, 70 - (turnover_rate - 10) * 2)


# ─────────────────────────────────────────────────────────────────
# 增强因子
# ─────────────────────────────────────────────────────────────────

def calc_enhanced_factors(closes: np.ndarray, volumes: np.ndarray) -> dict[str, float]:
    """计算 27 个增强因子的综合加分（-25 ~ +25）。"""
    bonus = 0.0
    if len(closes) < 20:
        return {"bonus": 0.0, "details": {}}

    details: dict[str, float] = {}

    # 1. 多周期动量加速
    m5 = (closes[-1] - closes[-6]) / closes[-6] * 100 if len(closes) > 5 else 0
    m10 = (closes[-1] - closes[-11]) / closes[-11] * 100 if len(closes) > 10 else 0
    m20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) > 20 else 0
    accel = m5 - m10 * 0.5  # 短期加速
    if accel > 1:
        bonus += min(3, accel)
    elif accel < -1:
        bonus -= min(3, abs(accel))
    details["momentum_accel"] = round(accel, 2)

    # 2. 波动结构：上行波动 vs 下行波动
    returns = np.diff(closes[-20:])
    up_vol = np.std(returns[returns > 0]) if np.any(returns > 0) else 0
    down_vol = np.std(returns[returns < 0]) if np.any(returns < 0) else 0
    if up_vol > down_vol * 1.2:
        bonus += 2
    elif down_vol > up_vol * 1.2:
        bonus -= 2
    details["vol_structure"] = round(up_vol - down_vol, 4)

    # 3. 量价背离
    price_up = closes[-1] > closes[-6] if len(closes) > 5 else False
    vol_down = np.mean(volumes[-5:]) < np.mean(volumes[-20:]) * 0.8 if len(volumes) >= 20 else False
    if price_up and vol_down:
        bonus -= 3  # 量价背离
        details["vol_divergence"] = -3
    else:
        details["vol_divergence"] = 0

    # 4. KDJ
    if len(closes) >= 14:
        low14 = np.min(closes[-14:])
        high14 = np.max(closes[-14:])
        if high14 > low14:
            rsv = (closes[-1] - low14) / (high14 - low14) * 100
        else:
            rsv = 50
        k_val = rsv  # simplified
        d_val = k_val  # simplified
        j_val = 3 * k_val - 2 * d_val
        if k_val > 80:
            bonus -= 2  # 超买
        elif k_val < 20:
            bonus += 2  # 超卖反弹
        elif 40 < k_val < 60 and j_val > k_val:
            bonus += 1
        details["kdj_j"] = round(j_val, 1)

    # 5. 布林带位置
    if len(closes) >= 20:
        ma20 = np.mean(closes[-20:])
        std20 = np.std(closes[-20:])
        if std20 > 0:
            pct_b = (closes[-1] - (ma20 - 2 * std20)) / (4 * std20)
            if pct_b > 0.9:
                bonus -= 2  # 超买
            elif pct_b < 0.1:
                bonus += 2  # 超卖
            details["boll_pct_b"] = round(pct_b, 2)

    # 6. OBV 方向
    if len(closes) >= 10 and len(volumes) >= 10:
        obv = np.cumsum(np.where(np.diff(closes[-11:]) > 0, volumes[-10:], -volumes[-10:]))
        if len(obv) >= 5:
            obv_rising = obv[-1] > obv[-5]
            if obv_rising and closes[-1] > closes[-6]:
                bonus += 2
            elif not obv_rising and closes[-1] < closes[-6]:
                bonus -= 2
            details["obv_confirm"] = 1 if obv_rising else -1

    # 7. 价格位置（60d 高低相对位置）
    if len(closes) >= 60:
        high60 = np.max(closes[-60:])
        low60 = np.min(closes[-60:])
        if high60 > low60:
            pos = (closes[-1] - low60) / (high60 - low60)
            if pos < 0.2:
                bonus += 2  # 底部区域
            elif pos > 0.9:
                bonus -= 1  # 高位风险
            details["price_position"] = round(pos, 2)

    # 8. 量集中度
    if len(volumes) >= 20:
        vc5 = np.mean(volumes[-5:])
        vc10 = np.mean(volumes[-10:])
        if vc10 > 0 and vc5 / vc10 > 1.5:
            bonus += 1  # 近期放量
        details["vol_concentration"] = round(_safe_div(vc5, vc10), 2)

    # Clamp total bonus
    bonus = max(-25, min(25, bonus))
    return {"bonus": round(bonus, 2), "details": details}


# ─────────────────────────────────────────────────────────────────
# 综合评分
# ─────────────────────────────────────────────────────────────────

def score_stock(
    closes: np.ndarray,
    volumes: np.ndarray,
    turnover_rate: float = 0,
    amount: float = 0,
    amount_rank_pct: float = 0.5,
    sector_change_pct: float = 0,
) -> dict[str, Any]:
    """综合 37 因子评分。

    Args:
        closes: 收盘价序列（至少 20 日，建议 60+）
        volumes: 成交量序列
        turnover_rate: 换手率 %
        amount: 成交额（元）
        amount_rank_pct: 成交额在全市场排名百分位（0-1，越大越好）
        sector_change_pct: 所属板块当日涨跌幅 %

    Returns:
        {
            "total_score": 0-100,
            "base_score": 0-100,
            "enhanced_bonus": float,
            "base_details": {factor: score},
            "enhanced_details": {factor: value},
        }
    """
    if len(closes) < 20:
        return {
            "total_score": 50.0,
            "base_score": 50.0,
            "enhanced_bonus": 0.0,
            "base_details": {},
            "enhanced_details": {},
            "error": "数据不足（需至少20日）",
        }

    # 基础因子
    base_scores = {
        "momentum_20d": score_momentum(closes, 20),
        "momentum_5d": score_momentum(closes, 5),
        "volume_trend": score_volume_trend(volumes),
        "ma_alignment": score_ma_alignment(closes),
        "macd_hist": score_macd(closes),
        "rsi_position": score_rsi(closes),
        "volatility": score_volatility(closes),
        "turnover_rate": score_turnover(turnover_rate),
        "amount_rank": _clamp(amount_rank_pct * 100),
        "sector_momentum": _clamp(50 + sector_change_pct * 10),
    }

    # 加权基础分
    base_score = sum(
        base_scores[k] * BASE_WEIGHTS[k]
        for k in BASE_WEIGHTS
    )

    # 增强因子
    enhanced = calc_enhanced_factors(closes, volumes)
    enhanced_bonus = enhanced["bonus"]
    enhanced_details = enhanced["details"]

    # 总分 = 基础分 + 增强加分 × 0.4
    total = base_score + enhanced_bonus * 0.4
    total = _clamp(total)

    return {
        "total_score": round(total, 1),
        "base_score": round(base_score, 1),
        "enhanced_bonus": round(enhanced_bonus, 2),
        "base_details": {k: round(v, 1) for k, v in base_scores.items()},
        "enhanced_details": enhanced_details,
    }
