"""市场环境分类器 — 基于技术面 + 情绪面的牛/熊/震荡三态判断。

算法参考 Easyup-Platform 的 market_regime.py，适配 Vibe-Trading 本地 SQLite 数据源。
数据全部来自 MarketStore（index_daily + market_breadth_snapshot），零外部 API 依赖。

Technical Score (上证 120 日 K 线):
  Bull: MA20>MA60×1.02(+2), 20d涨幅>5%(+2), MA排列(+1), RSI>55(+1), MA20斜率>0.5%(+1), ADX≥25&+DI>-DI(+1)
  Bear: 对称逻辑

Emotion Score (实时市场宽度):
  涨跌比/涨停跌停/成交额 → 调整分

Classification:
  bull_score ≥ 4 & bull > bear → bull
  bear_score ≥ 4 & bear > bull → bear
  else → range
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 参数库：regime → 风控参数映射
# ─────────────────────────────────────────────────────────────────

REGIME_PARAMS: dict[str, dict] = {
    "bull": {
        "stop_loss": -0.08,
        "tp1": 0.15, "tp2": 0.25, "tp3": 0.35,
        "max_position": 0.90,
        "max_holdings": 4,
        "atr_mult": 1.5,
        "change_range": (0.01, 0.095),
    },
    "range": {
        "stop_loss": -0.07,
        "tp1": 0.15, "tp2": 0.25, "tp3": 0.35,
        "max_position": 0.85,
        "max_holdings": 3,
        "atr_mult": 1.5,
        "change_range": (0.01, 0.095),
    },
    "bear": {
        "stop_loss": -0.04,
        "tp1": 0.10, "tp2": 0.18, "tp3": 0.25,
        "max_position": 0.60,
        "max_holdings": 2,
        "atr_mult": 1.2,
        "change_range": (0.01, 0.07),
    },
}


# ─────────────────────────────────────────────────────────────────
# 数据模型
# ─────────────────────────────────────────────────────────────────

@dataclass
class RegimeResult:
    """市场环境分类结果。"""
    trade_date: str
    regime: str                          # "bull" | "bear" | "range"
    confidence: float                    # 0-100
    bull_score: float
    bear_score: float
    strong_trend: bool                   # ADX≥25 & confidence≥60
    technical_indicators: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date,
            "regime": self.regime,
            "confidence": round(self.confidence, 1),
            "bull_score": round(self.bull_score, 1),
            "bear_score": round(self.bear_score, 1),
            "strong_trend": self.strong_trend,
            "technical_indicators": self.technical_indicators,
            "parameters": self.parameters,
        }


# ─────────────────────────────────────────────────────────────────
# 技术指标计算
# ─────────────────────────────────────────────────────────────────

def _calc_ma(closes: np.ndarray, period: int) -> float:
    """简单移动平均（最新值）。"""
    if len(closes) < period:
        return float(closes[-1]) if len(closes) > 0 else 0.0
    return float(np.mean(closes[-period:]))


def _calc_ma_series(closes: np.ndarray, period: int) -> np.ndarray:
    """返回完整 MA 序列（前 period-1 个为 NaN）。"""
    n = len(closes)
    if n < period:
        return np.full(n, np.nan)
    cs = np.cumsum(closes)
    ma = np.empty(n, dtype=float)
    ma[:period - 1] = np.nan
    ma[period - 1] = cs[period - 1] / period
    ma[period:] = (cs[period:] - cs[:-period]) / period
    return ma


def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
    """标准 RSI。"""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _calc_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
              period: int = 14) -> tuple[float, float, float]:
    """Wilder 平滑 ADX → (adx, +di, -di)。"""
    n = len(closes)
    if n < period + 1:
        return 0.0, 0.0, 0.0

    # True Range
    tr = np.empty(n)
    tr[0] = highs[0] - lows[0]
    tr[1:] = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1]),
        )
    )

    # Directional movement
    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Wilder smoothing (RMA)
    def _rma(arr: np.ndarray, p: int) -> np.ndarray:
        out = np.empty(len(arr), dtype=float)
        out[:p] = np.nan
        out[p - 1] = np.mean(arr[:p])
        for i in range(p, len(arr)):
            out[i] = (out[i - 1] * (p - 1) + arr[i]) / p
        return out

    atr = _rma(tr[1:], period)
    smooth_plus = _rma(plus_dm, period)
    smooth_minus = _rma(minus_dm, period)

    # DI
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = np.where(atr > 0, 100.0 * smooth_plus / atr, 0.0)
        minus_di = np.where(atr > 0, 100.0 * smooth_minus / atr, 0.0)
        dx = np.where(
            (plus_di + minus_di) > 0,
            100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di),
            0.0,
        )

    adx = _rma(dx[~np.isnan(dx)], period) if np.any(~np.isnan(dx)) else np.array([0.0])
    adx_val = float(adx[-1]) if len(adx) > 0 and not np.isnan(adx[-1]) else 0.0
    pdi_val = float(plus_di[-1]) if len(plus_di) > 0 and not np.isnan(plus_di[-1]) else 0.0
    mdi_val = float(minus_di[-1]) if len(minus_di) > 0 and not np.isnan(minus_di[-1]) else 0.0

    return adx_val, pdi_val, mdi_val


def _calc_volatility(closes: np.ndarray, period: int = 20) -> float:
    """变异系数 %（波动率）。"""
    if len(closes) < period:
        return 0.0
    recent = closes[-period:]
    mean = np.mean(recent)
    if mean == 0:
        return 0.0
    return float(np.std(recent) / mean * 100.0)


def _calc_ma20_slope(ma20: np.ndarray) -> float:
    """MA20 斜率：% 变化（近 5 日均值 vs 前 5 日均值）。"""
    valid = ma20[~np.isnan(ma20)]
    if len(valid) < 25:
        return 0.0
    recent_avg = np.mean(valid[-5:])
    prev_avg = np.mean(valid[-25:-20])
    if prev_avg == 0:
        return 0.0
    return float((recent_avg - prev_avg) / prev_avg * 100.0)


def compute_technical_indicators(bars: pd.DataFrame) -> dict:
    """从 index_daily DataFrame 计算全部技术指标。

    参数:
        bars: 必须有 close, high, low 列，按日期升序排列

    返回:
        dict with keys: ma5, ma10, ma20, ma60, rsi14, adx, plus_di, minus_di,
                        volatility, ma20_slope, change_20d, close
    """
    closes = bars["close"].values.astype(float)
    highs = bars["high"].values.astype(float)
    lows = bars["low"].values.astype(float)

    ma5 = _calc_ma(closes, 5)
    ma10 = _calc_ma(closes, 10)
    ma20 = _calc_ma(closes, 20)
    ma60 = _calc_ma(closes, 60)

    ma20_series = _calc_ma_series(closes, 20)

    rsi14 = _calc_rsi(closes, 14)
    adx, plus_di, minus_di = _calc_adx(highs, lows, closes, 14)
    volatility = _calc_volatility(closes, 20)
    ma20_slope = _calc_ma20_slope(ma20_series)

    # 20 日涨幅
    if len(closes) >= 20:
        change_20d = (closes[-1] - closes[-20]) / closes[-20] * 100.0 if closes[-20] != 0 else 0.0
    else:
        change_20d = 0.0

    return {
        "close": float(closes[-1]),
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "rsi14": rsi14,
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "volatility": volatility,
        "ma20_slope": ma20_slope,
        "change_20d": change_20d,
        "ma_aligned_bull": ma5 > ma10 > ma20,
        "ma_aligned_bear": ma5 < ma10 < ma20,
    }


# ─────────────────────────────────────────────────────────────────
# 打分逻辑
# ─────────────────────────────────────────────────────────────────

def compute_technical_score(indicators: dict) -> tuple[float, float]:
    """返回 (bull_score, bear_score)，满分各 ~8 分。"""
    bull = 0.0
    bear = 0.0

    ma20 = indicators["ma20"]
    ma60 = indicators["ma60"]

    # MA20 vs MA60
    if ma60 > 0:
        if ma20 > ma60 * 1.02:
            bull += 2
        if ma20 < ma60 * 0.98:
            bear += 2

    # 20 日涨幅
    chg = indicators["change_20d"]
    if chg > 5:
        bull += 2
    elif chg > 3:
        bull += 1
    if chg < -5:
        bear += 2
    elif chg < -3:
        bear += 1

    # MA 排列
    if indicators["ma_aligned_bull"]:
        bull += 1
    if indicators["ma_aligned_bear"]:
        bear += 1

    # RSI
    rsi = indicators["rsi14"]
    if rsi > 55:
        bull += 1
    if rsi < 40:
        bear += 1

    # MA20 斜率
    slope = indicators["ma20_slope"]
    if slope > 0.5:
        bull += 1
    if slope < -0.5:
        bear += 1

    # ADX + DI 方向
    adx = indicators["adx"]
    pdi = indicators["plus_di"]
    mdi = indicators["minus_di"]
    if adx >= 25 and pdi > mdi:
        bull += 1
    if adx >= 25 and mdi > pdi:
        bear += 1

    return bull, bear


def compute_emotion_score(breadth: dict | None) -> tuple[float, float]:
    """返回 (bull_adj, bear_adj) 情绪调整分。

    breadth 格式: {advancers, decliners, limit_up, limit_down, turnover_billion}
    """
    bull = 0.0
    bear = 0.0

    if not breadth:
        return bull, bear

    advancers = breadth.get("advancers", 0) or 0
    decliners = breadth.get("decliners", 0) or 0
    limit_up = breadth.get("limit_up", 0) or 0
    limit_down = breadth.get("limit_down", 0) or 0
    turnover = breadth.get("turnover_billion", 0) or 0  # 单位：亿元

    # 涨跌比
    if decliners > 0:
        ratio = advancers / decliners
    elif advancers > 0:
        ratio = 5.0  # 极端多头
    else:
        ratio = 1.0

    if ratio >= 2.0:
        bull += 2
    elif ratio >= 1.5:
        bull += 1
    if ratio <= 0.5:
        bear += 2
    elif ratio <= 0.7:
        bear += 1

    # 涨停/跌停
    if limit_up >= 80:
        bull += 1
    if limit_up <= 15:
        bear += 1
    if limit_down >= 30:
        bear += 2

    # 成交额（亿元）
    if turnover > 0:
        if turnover < 7000:
            bear += 1
        elif turnover > 15000:
            bull += 1

    return bull, bear


# ─────────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────────

def classify_regime(store, trade_date: str | None = None) -> RegimeResult:
    """市场环境分类主入口。

    参数:
        store: MarketStore 实例
        trade_date: 分类日期，默认最新交易日

    返回:
        RegimeResult
    """
    from datetime import datetime, timezone, timedelta
    _CST = timezone(timedelta(hours=8))

    if trade_date is None:
        trade_date = datetime.now(_CST).strftime("%Y-%m-%d")

    # 1. 获取上证指数 120 日 K 线
    bars = None
    try:
        bars = store.get_daily_bars("000001.SH", days=120)
    except Exception:
        # 尝试不带后缀的格式
        try:
            bars = store.get_daily_bars("sh000001", days=120)
        except Exception:
            logger.warning("regime: 无法获取上证指数 K 线数据")

    if bars is None or len(bars) < 20:
        logger.warning("regime: 上证指数 K 线数据不足 (%s rows)", len(bars) if bars is not None else 0)
        return RegimeResult(
            trade_date=trade_date,
            regime="range",
            confidence=0.0,
            bull_score=0.0,
            bear_score=0.0,
            strong_trend=False,
            technical_indicators={},
            parameters=REGIME_PARAMS["range"],
        )

    # 2. 获取市场宽度数据
    breadth = None
    try:
        row = store._conn.execute(
            "SELECT * FROM market_breadth_snapshot WHERE trade_date = ? ORDER BY updated_at DESC LIMIT 1",
            (trade_date,),
        ).fetchone()
        if row:
            breadth = dict(row)
    except Exception:
        logger.debug("regime: 无法获取市场宽度数据", exc_info=True)

    # 3. 计算技术指标
    indicators = compute_technical_indicators(bars)

    # 4. 打分
    tech_bull, tech_bear = compute_technical_score(indicators)
    emo_bull, emo_bear = compute_emotion_score(breadth)

    bull_score = tech_bull + emo_bull
    bear_score = tech_bear + emo_bear

    # 5. 分类
    if bull_score >= 4 and bull_score > bear_score:
        regime = "bull"
        confidence = min(bull_score / 8.0 * 100, 100)
    elif bear_score >= 4 and bear_score > bull_score:
        regime = "bear"
        confidence = min(bear_score / 8.0 * 100, 100)
    else:
        regime = "range"
        confidence = max(0, 100 - abs(bull_score - bear_score) * 15)

    strong_trend = indicators["adx"] >= 25 and confidence >= 60

    # 6. ADX 强趋势调整 ATR 倍数
    params = dict(REGIME_PARAMS[regime])
    if indicators["adx"] >= 30 and strong_trend:
        params["atr_mult"] = 1.8
    elif indicators["adx"] >= 25 and strong_trend:
        params["atr_mult"] = 1.6

    # 构建指标摘要（只保留可 JSON 序列化的值）
    tech_summary = {
        "close": indicators["close"],
        "ma5": round(indicators["ma5"], 2),
        "ma10": round(indicators["ma10"], 2),
        "ma20": round(indicators["ma20"], 2),
        "ma60": round(indicators["ma60"], 2),
        "rsi14": round(indicators["rsi14"], 1),
        "adx": round(indicators["adx"], 1),
        "plus_di": round(indicators["plus_di"], 1),
        "minus_di": round(indicators["minus_di"], 1),
        "volatility": round(indicators["volatility"], 2),
        "ma20_slope": round(indicators["ma20_slope"], 3),
        "change_20d": round(indicators["change_20d"], 2),
    }
    if breadth:
        tech_summary["breadth"] = {
            "advancers": breadth.get("advancers"),
            "decliners": breadth.get("decliners"),
            "limit_up": breadth.get("limit_up"),
            "limit_down": breadth.get("limit_down"),
            "turnover_billion": breadth.get("turnover_billion"),
        }

    result = RegimeResult(
        trade_date=trade_date,
        regime=regime,
        confidence=round(confidence, 1),
        bull_score=round(bull_score, 1),
        bear_score=round(bear_score, 1),
        strong_trend=strong_trend,
        technical_indicators=tech_summary,
        parameters=params,
    )

    logger.info(
        "regime 分类完成: %s | regime=%s confidence=%.1f | bull=%.1f bear=%.1f | ADX=%.1f",
        trade_date, regime, confidence, bull_score, bear_score, indicators["adx"],
    )

    return result
