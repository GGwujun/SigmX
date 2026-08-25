---
name: elliott-wave
description: Elliott Wave Theory signal engine. Detects swing points through Zigzag, matches 5-wave impulse and 3-wave corrective structures, validates them with Fibonacci wave relationships, and generates trend-top / correction-complete signals. Pure in-house pandas implementation.
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
# Elliott Wave Theory

## Purpose

Classic wave theory based on the core assumption that markets move in fractal wave structures:

| Structure | Wave Count | Direction | Meaning |
|------|------|------|------|
| Impulse wave | 5 waves (1-2-3-4-5) | Trend-following | Main trend direction |
| Corrective wave | 3 waves (A-B-C) | Counter-trend | Pullback correction |

## Core Rules

### Three Iron Rules for Impulse Waves
1. Wave 2 cannot retrace beyond the start of wave 1
2. Wave 3 cannot be the shortest impulse wave
3. Wave 4 cannot enter the price territory of wave 1

### Fibonacci Relationships Between Waves
- Wave 2 retraces 0.5-0.618 of wave 1
- Wave 3 = wave 1 × 1.618 (most common)
- Wave 4 retraces 0.382 of wave 3
- Wave 5 ≈ the length of wave 1

## Signal Logic

- **5-wave advance completed** → sell (trend top)
- **ABC pullback completed** → buy (correction finished)
- **Wave 3 in progress** → stay with the trend (no reversal signal is generated)

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| swing_window | 10 | Rolling window for swing-point detection |
| fib_tolerance | 0.15 | Tolerance for Fibonacci ratios |
| min_wave_bars | 5 | Minimum number of candles per wave |

## Notes

Wave theory is highly subjective, and automatic counting can yield multiple interpretations. This implementation uses a "simplest effective single interpretation" strategy and would rather miss signals than misclassify them.

## Dependencies

```bash
pip install pandas numpy requests
```

## Signal Convention

- `1` = long, `-1` = short, `0` = stand aside
