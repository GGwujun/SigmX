---
name: pair-trading
description: Pair trading strategy. Trades mean reversion using the spread/ratio Z-score of two correlated instruments. Requires at least two instruments.
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
# Pair Trading Strategy

## Purpose

Select two highly correlated instruments (such as stocks from the same industry or BTC/ETH), monitor how far their price ratio (or spread) deviates from the mean, and trade against extreme deviations while waiting for mean reversion.

## Signal Logic

1. **Compute the price ratio**: `ratio = close_A / close_B`
2. **Rolling mean and standard deviation**: `mean = ratio.rolling(lookback).mean()`, `std = ratio.rolling(lookback).std()`
3. **Z-score**: `z = (ratio - mean) / std`
4. **Signal generation**:
   - Z < -entry_z → long A, short B (ratio is too low, expected to revert)
   - Z > +entry_z → short A, long B (ratio is too high, expected to revert)
   - |Z| < exit_z → close the position (reverted back near the mean)

## Implementation Notes

- Pair trading requires **exactly two instruments** (`codes` array length = 2)
- The first instrument is A (`leg1`), and the second is B (`leg2`)
- Signals for A and B are opposite: when A is long, B is short, and vice versa
- **Equal-weight allocation only**: A and B each take 50% of capital, with no precise hedge-ratio calculation

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| lookback | 60 | Lookback window for mean and standard deviation |
| entry_z | 2.0 | Entry Z-score threshold |
| exit_z | 0.5 | Exit Z-score threshold |

## Example `config.json`

```json
{
  "source": "tushare",
  "codes": ["601318.SH", "601628.SH"],
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "initial_cash": 1000000,
  "commission": 0.001,
  "extra_fields": null
}
```

Cryptocurrency version:
```json
{
  "source": "okx",
  "codes": ["BTC-USDT", "ETH-USDT"],
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_cash": 1000000,
  "commission": 0.001,
  "extra_fields": null
}
```

## Common Pitfalls

- `codes` must contain exactly 2 instruments, no more and no less
- The date indexes of the two instruments must be aligned (use an inner join), otherwise the ratio calculation will be wrong
- Before the lookback window is filled, Z-scores are `NaN`, so fill signals with 0
- Do not generate same-direction signals for both A and B; pair trading is fundamentally a long-short hedge

## Dependencies

```bash
pip install pandas numpy
```

## Signal Convention

- Instrument A: `0.5` = long, `-0.5` = short, `0` = flat
- Instrument B: direction is opposite to A
