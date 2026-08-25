---
name: harmonic
description: Harmonic Patterns signal engine. Identifies XABCD five-point structures such as Gartley/Bat/Butterfly/Crab based on Fibonacci geometry, and generates trading signals in the PRZ (Potential Reversal Zone).
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
# Harmonic Patterns

## Purpose

The Fibonacci geometry school uses precise ratio relationships to identify price patterns:

| Pattern | B-Point Retracement | D-Point Retracement | Direction |
|------|---------|---------|------|
| Gartley | 0.618 XA | 0.786 XA | Reversal |
| Bat | 0.382-0.5 XA | 0.886 XA | Reversal |
| Butterfly | 0.786 XA | 1.27 XA | Reversal |
| Crab | 0.382-0.618 XA | 1.618 XA | Reversal |

## Core Concepts

- **XABCD five-point pattern**: a price structure defined by precise Fibonacci ratios
- **PRZ (Potential Reversal Zone)**: the convergence area around point D, where reversal probability is high
- Bullish pattern (point D at the bottom) → buy signal
- Bearish pattern (point D at the top) → sell signal

## Dependencies

```bash
pip install pyharmonics pandas numpy requests
```

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| is_stock | False | Whether the instrument is a stock (affects analysis parameters) |

## Signal Convention

- `1` = long, `-1` = short, `0` = stand aside
