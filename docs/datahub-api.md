# SigmX Data Hub API 目录（/api/v1/*）

> Base: `https://sigmx.dsx-family.site/api/v1` · Timezone: Asia/Shanghai · 金额单位: 亿元（除非另有注明）
> 鉴权: Data Hub 模式下远程请求需 `X-API-Key` 头或产品 Bearer 令牌；响应统一 `{ok, data, meta}` 信封。
> 实现于 `agent/src/api/sigmx_routes.py`，health 端点回显最新清单。

## 市场总览（既有）

| 端点 | 说明 | 数据表 |
|---|---|---|
| `GET /health` | 健康 + 端点清单 | — |
| `GET /market/latest-trade-date` | 最新交易日 | bars_daily |
| `GET /market/overview?trade_date` | 大盘涨跌/涨跌停/成交额 | market_breadth_snapshot |
| `GET /market/breadth?trade_date` | 三层宽度 | 多表 |
| `GET /market/fund-summary?trade_date` | 大盘资金汇总 | sector/stock_capital_flow |
| `GET /indices/daily?trade_date&codes` | 指数日K | index_daily |
| `GET /sectors/fund-flow?trade_date` | 板块资金流排名 | sector_capital_flow |
| `GET /sectors/fund-flow/intraday` | 板块分时资金（插值） | sector_capital_flow |
| `GET /stocks/hot-pool?pool_type` | 热门股池 | stock_pool |
| `GET /stocks/metadata?codes` | 股票元数据 | security_master |
| `GET /news/finance/rss-summary` | 财经 RSS 摘要 | RSSHub |
| `GET /content/morning-briefing-triptych` | 早盘内参三图 | 多表 |

## 行情K线（A1，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/daily` | `code`*；`start/end`；`limit≤2000`（默认250） | 个股日K历史（倒序） | bars_daily |
| `GET /stocks/daily-basic` | `trade_date`；`codes`≤50；`limit≤500` | 每日估值 PE/PB/换手/市值 | stock_daily_basic |
| `GET /etf/daily` | `code`*；`start/end`；`limit` | ETF 日K | etf_daily |
| `GET /fund/daily` | `code`*；`start/end`；`limit` | 基金日K（含 nav/iopv） | fund_daily |
| `GET /boards/daily` | `board_code` 或 `trade_date+board_type`；`start/end` | 板块日K（按代码查历史 / 按日期查排行） | board_daily |
| `GET /boards/members` | `board_code`*；`limit≤2000` | 板块成分股 | board_members |
| `GET /quotes/realtime` | `codes`*≤50 | 实时快照（5分钟粒度） | realtime_quote_snapshot |

`*` = 必填。个股历史端点按 trade_date 倒序返回；快照类端点 `trade_date` 缺省取该表最新日期。

<!-- A2-A6 批次端点文档随实施追加 -->
