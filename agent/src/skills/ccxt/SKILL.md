---
name: ccxt
category: data-source
description: CCXT unified crypto exchange library (100+ exchanges). Free public market data. Fallback when OKX is unavailable.
sigmx:
  schema_version: 1
  ownership: third_party
  execution: instructional
  primary_source: public_source
  datahub_endpoints:
    []
  fallback_sources:
    - ccxt
  markets:
    - CRYPTO
  credentials:
    []
  capability_status: full
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

当前能力由公共数据源（ccxt）提供；不得标记为 Data Hub 返回。 通过统一路由执行，并在结果中标明公共来源、时间和可用性限制。

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
## Overview

CCXT is a unified cryptocurrency exchange trading library supporting 100+ exchanges including Binance, Bybit, OKX, Coinbase, Kraken, and more. Public market data (OHLCV, tickers, order books) requires no API key.

- GitHub: https://github.com/ccxt/ccxt (35k+ stars)
- Install: `pip install ccxt`

## Quick Start

```python
import ccxt

exchange = ccxt.binance({"enableRateLimit": True})

# Fetch daily OHLCV
ohlcv = exchange.fetch_ohlcv("BTC/USDT", "1d", limit=100)
# Returns: [[timestamp, open, high, low, close, volume], ...]

# Fetch ticker
ticker = exchange.fetch_ticker("ETH/USDT")
print(f"ETH price: {ticker['last']}")
```

## Key Methods

| Method | Description | Returns |
|--------|-------------|---------|
| `fetch_ohlcv(symbol, timeframe, since, limit)` | Historical candles | `[[ts, o, h, l, c, v], ...]` |
| `fetch_ticker(symbol)` | Latest quote | `{last, bid, ask, volume, ...}` |
| `fetch_tickers(symbols)` | Batch quotes | `{symbol: ticker}` |
| `fetch_order_book(symbol, limit)` | Order book | `{bids, asks, timestamp}` |
| `fetch_trades(symbol, since, limit)` | Recent trades | `[{price, amount, side, timestamp}, ...]` |

## Timeframes

`1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `12h`, `1d`, `1w`, `1M`

Note: not all exchanges support all timeframes. Use `exchange.timeframes` to check.

## Symbol Format

CCXT uses slash format: `BTC/USDT`, `ETH/BTC`, `SOL/USDT`

The project's DataLoader automatically converts `BTC-USDT` (hyphen) to `BTC/USDT` (slash).

## Exchange Selection

Set via environment variable: `CCXT_EXCHANGE=binance` (default)

Popular exchanges: `binance`, `bybit`, `okx`, `coinbase`, `kraken`, `bitget`, `gate`

## Built-in Loader

The project has a built-in CCXT DataLoader at `backtest/loaders/ccxt_loader.py`. It serves as a fallback when the OKX loader is unavailable.

## Pagination

For long history, CCXT paginates via the `since` parameter (millisecond timestamp). The built-in loader handles this automatically (up to 200 pages).
