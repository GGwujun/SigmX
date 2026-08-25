---
name: data-routing
category: data-source
description: Data source selection decision tree. Load this skill BEFORE any backtest or data-fetching task to choose the best available data source.
sigmx:
  schema_version: 1
  ownership: official
  execution: instructional
  primary_source: none
  datahub_endpoints:
    []
  fallback_sources:
    []
  markets:
    - LOCAL
  credentials:
    []
  capability_status: instructional
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

该 Skill 是本地方法或文档流程，不需要市场数据源。 不要为了填充结果而调用未声明的外部数据接口。

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
## Data Source Overview

| Source | Markets | Auth Required | Network | Skill |
|--------|---------|---------------|---------|-------|
| tushare | A-shares, funds, futures, macro | Yes (`TUSHARE_TOKEN`) | China network | tushare |
| akshare | A-shares, US, HK, futures, macro, forex | No | Unrestricted | akshare |
| yfinance | US stocks, HK stocks, ETFs | No | Needs Yahoo Finance access | yfinance |
| okx | Crypto (OKX exchange) | No | Needs okx.com access | okx-market |
| ccxt | Crypto (100+ exchanges) | No | Needs exchange access | ccxt |

## Decision Tree

### Backtest Scenario (writing config.json)

Use `source: "auto"` — the runner automatically routes by symbol pattern and falls back to alternative sources if the primary one is unavailable.

You do NOT need to specify a concrete data source in config.json unless the user explicitly asks for one.

### Analysis / Research Scenario (writing Python scripts)

1. Identify the market type from the user's request
2. Pick the source by priority:

**A-shares**: tushare (if TUSHARE_TOKEN is set) > akshare (free fallback)
**US stocks**: yfinance > akshare
**HK stocks**: yfinance > akshare
**Crypto**: okx (single exchange) > ccxt (multi-exchange)
**Futures**: tushare > akshare
**Macro / economics**: akshare > tushare
**Forex**: akshare > yfinance

3. Load the corresponding skill for API details: `load_skill("akshare")`

### Availability Check

- **tushare**: check if `TUSHARE_TOKEN` environment variable exists
- **yfinance / okx / ccxt / akshare**: free but may have network restrictions
- If the user reports "connection timeout" or "cannot access", switch to the same-market fallback

## Symbol Format Reference

| Market | Format | Examples |
|--------|--------|---------|
| A-shares | `NNNNNN.SZ/SH/BJ` | 000001.SZ, 600000.SH |
| US stocks | `TICKER.US` | AAPL.US, MSFT.US |
| HK stocks | `NNN(N).HK` | 700.HK, 9988.HK |
| Crypto | `SYMBOL-USDT` | BTC-USDT, ETH-USDT |
| Futures | `XXNNNN.EXCHANGE` | CU2406.SHFE |
| Forex | `XXX/YYY` | USD/CNY, EUR/USD |

## Fallback Chain (Runner Layer)

The backtest runner implements automatic fallback at the market level:

```
User requests 000001.SZ (A-share)
  -> detect market: a_share
  -> try tushare: TUSHARE_TOKEN missing -> skip
  -> try akshare: available -> use akshare
  -> success (zero config required)
```

This is transparent to the user — they just see results.
