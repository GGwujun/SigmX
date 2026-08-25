---
name: technical-basic
description: Core technical indicator collection (trend EMA/ADX + mean-reversion BB/RSI + volume-price OBV/volume ratio), generates a composite signal via three-dimensional voting. Pure pandas implementation for any OHLCV data.
category: strategy
sigmx:
  schema_version: 1
  ownership: official
  execution: executable
  primary_source: data_hub
  datahub_endpoints:
    - stocks.daily
    - stocks.daily_basic
  fallback_sources:
    - akshare
  markets:
    - CN_A
  credentials:
    - SIGMX_DATA_HUB_BASE_URL
    - SIGMX_DATA_HUB_KEY
  capability_status: full
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

默认且优先使用 SigmX Data Hub；只在清单声明允许且指标口径一致时使用候补源。 `python -m src.skill_runtime.cli stocks.daily --params '<JSON>'`

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# Core Technical Indicator Collection

## Purpose

Combines three classic Western technical analysis approaches into one composite signal engine:

| Dimension | Indicators | Purpose |
|------|------|------|
| Trend | EMA(12/26) + ADX(14) | Determine direction and trend strength |
| Mean reversion | Bollinger Bands(20,2) + RSI(14) | Detect overbought and oversold conditions |
| Volume-price | OBV + volume ratio | Confirm volume participation |

## Signal Logic

Three-dimensional voting mechanism:
- **Long**: trend is bullish + RSI is not overbought + OBV is rising
- **Short**: trend is bearish + RSI is not oversold + OBV is falling
- **Stand aside**: mixed signals

## Key Implementation Details

- RSI and ADX use **Wilder EWM** (`ewm(alpha=1/period)`), not a rolling mean
- Full ADX chain: +DM/-DM → TR → +DI/-DI → DX → ADX
- OBV = `(volume * sign(close.diff())).cumsum()`

## Parameters

All parameters have default values and can be overridden at instantiation time:

| Parameter | Default | Description |
|------|--------|------|
| ema_fast | 12 | Fast EMA period |
| ema_slow | 26 | Slow EMA period |
| adx_period | 14 | ADX calculation period |
| adx_threshold | 25.0 | ADX trend-strength threshold |
| bb_window | 20 | Bollinger Band window |
| bb_std | 2.0 | Bollinger Band standard deviation multiplier |
| rsi_period | 14 | RSI period |
| rsi_oversold | 30 | RSI oversold threshold |
| rsi_overbought | 70 | RSI overbought threshold |
| vol_ma_period | 20 | Volume moving-average period |
| obv_ma_period | 20 | OBV moving-average period |

## Dependencies

```bash
pip install pandas numpy requests
```

## Signal Convention

- `1` = long, `-1` = short, `0` = stand aside
