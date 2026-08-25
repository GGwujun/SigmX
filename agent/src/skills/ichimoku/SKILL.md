---
name: ichimoku
description: Ichimoku Kinko Hyo five-line system signal engine. A standalone Japanese technical-analysis school that generates trading signals from Tenkan/Kijun crossovers, cloud position, and Chikou confirmation. Pure pandas implementation.
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
# Ichimoku Kinko Hyo

## Purpose

A standalone Japanese technical analysis framework that uses a five-line system and the cloud to provide a complete trend-evaluation structure:

| Line | Japanese | Calculation | Meaning |
|----|------|------|------|
| Conversion line | Tenkan-sen | (9H+9L)/2 | Short-term trend |
| Base line | Kijun-sen | (26H+26L)/2 | Medium-term trend |
| Leading Span A | Senkou Span A | (Tenkan+Kijun)/2 shifted forward by 26 | Upper cloud boundary |
| Leading Span B | Senkou Span B | (52H+52L)/2 shifted forward by 26 | Lower cloud boundary |
| Lagging Span | Chikou Span | Closing price shifted backward by 26 | Trend confirmation |

## Signal Logic

Signals are triggered only on TK crossover events, with three filters:
- **Strong buy**: bullish TK cross + price above the cloud + bullish cloud (A > B)
- **Strong sell**: bearish TK cross + price below the cloud + bearish cloud (A < B)
- All other cases → stand aside

Warm-up requires 78 candles (52+26).

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| tenkan_period | 9 | Tenkan-sen period |
| kijun_period | 26 | Kijun-sen period |
| senkou_b_period | 52 | Senkou Span B period |
| displacement | 26 | Forward/backward shift period |

## Dependencies

```bash
pip install pandas numpy requests
```

## Signal Convention

- `1` = long, `-1` = short, `0` = stand aside
