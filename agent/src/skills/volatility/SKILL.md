---
name: volatility
description: Volatility strategy. Trades mean reversion based on percentile ranking of historical volatility (HV). Suitable for any OHLCV data.
category: strategy
sigmx:
  schema_version: 1
  ownership: official
  execution: executable
  primary_source: data_hub
  datahub_endpoints:
    - option_chain
    - stocks.daily
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

默认且优先使用 SigmX Data Hub；只在清单声明允许且指标口径一致时使用候补源。 `python -m src.skill_runtime.cli option_chain --params '<JSON>'`

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# Volatility Strategy

## Purpose

Uses percentile ranking of historical volatility (HV) to capture volatility mean reversion: build positions in low-volatility regimes while waiting for volatility expansion, and exit or short in high-volatility regimes to capture contraction.

## Signal Logic

1. **Compute HV**: annualized standard deviation of returns over the past `hv_window` days
2. **Percentile ranking**: percentile position of HV within the past `lookback` days (0-100)
3. **Signal generation**:
   - Percentile < `low_pct` → go long (volatility is low, waiting for expansion)
   - Percentile > `high_pct` → exit / go short (volatility is high, waiting for contraction)
   - Middle region → keep the current position

## Key Implementation Details

- HV = `returns.rolling(hv_window).std() * sqrt(252)` (annualized)
- Percentile = `hv.rolling(lookback).rank(pct=True) * 100`
- For cryptocurrencies, use 365 instead of 252 as the annualization factor

## Parameters

| Parameter | Default | Description |
|------|--------|------|
| hv_window | 20 | Historical volatility calculation window |
| lookback | 120 | Lookback period for percentile ranking |
| low_pct | 20.0 | Low-volatility threshold (percentile) |
| high_pct | 80.0 | High-volatility threshold (percentile) |
| annualize | 252 | Annualization factor (252 for China A-shares, 365 for crypto) |

## Common Pitfalls

- Before the lookback window is filled, there is not enough data to compute percentiles, so the signal should be 0 (`fillna`)
- Volatility is not direction. Going long in low-volatility regimes does not guarantee price appreciation; it only means volatility expansion is statistically more likely
- Cryptocurrencies trade 7x24, so `annualize` should be set to 365

## Dependencies

```bash
pip install pandas numpy
```

## Signal Convention

- `1` = long (low-volatility regime), `-1` = short (high-volatility regime), `0` = stand aside
