# SigmX Data Hub API 目录（/api/v1/*）

> Base: `https://sigmx.dsx-family.site/api/v1` · Timezone: Asia/Shanghai · 金额单位: 亿元（除非另有注明）
> 鉴权: Data Hub 模式只接受个人中心创建的 `Authorization: Bearer sxd_live_...` Credential；响应统一 `{ok, data, meta}` 信封，并返回 Data Credit 计费头。
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

## 资金流（A2，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/fund-flow` | `code`*；`start/end`；`limit≤2000` | 个股日级资金流（主力/超大/大/中/小单净额，亿元） | fund_flow_daily |
| `GET /stocks/capital-flow` | `codes`*≤50；`trade_date`；`period∈1,3,5,10` | 个股资金流快照（period 维度，亿元） | stock_capital_flow |
| `GET /stocks/capital-rank` | `trade_date`；`rank_type∈inflow,outflow`；`order`；`limit≤500` | 资金流排名（含 extra 展开字段） | stock_capital_rank |
| `GET /northbound/flow` | `trade_date` | 北向净买分钟序列（沪深股通，亿元） | northbound_flow |

## 打板/情绪（A3，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/limit-pool` | `pool_type∈zt,dt,zb,yzt`；`trade_date`；`limit≤500` | 涨停/跌停/炸板/昨日涨停池明细（连板数/封单/炸板次数等） | zt_pool / dt_pool / zb_pool / yzt_pool |
| `GET /dragon-tiger` | `trade_date`；`code`；`limit≤500` | 龙虎榜（席位详情 extra 展开，亿元） | dragon_tiger |
| `GET /hot-list` | `trade_date`；`source`；`limit≤200` | 个股热度榜（按 rank 排序） | hot_list |
| `GET /market/regime` | `trade_date` | 市场环境分类（bull/bear 分值 + indicators） | market_regime |

## 基本面（A4，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/financial-snapshot` | `codes`*≤50 | 财务快照（EPS/BVPS/ROE/净利/营收等 37 字段） | financial_snapshot |
| `GET /stocks/financial-statement` | `code`*；`report_type∈lrb,zcfzb,xjlb`；`limit≤20` | 财报三表（payload 解析后透出） | financial_statement |
| `GET /stocks/eps-forecast` | `code`*；`year` | 一致预期 EPS（机构数/min/mean/max） | eps_forecast |
| `GET /stocks/margin` | `trade_date`；`code`；`limit≤500` | 融资融券明细（元） | margin_trading |
| `GET /stocks/block-trade` | `trade_date`；`code`；`limit≤500` | 大宗交易（溢价率/买卖方） | block_trade |
| `GET /stocks/holder-num` | `code`*；`start/end` | 股东户数变化 | holder_num |
| `GET /stocks/dividends` | `code`* | 分红送转历史 | dividend_history |

## 基金/ETF（A5，2026-08-15 新增，特色数据）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /funds/premium` | `trade_date`；`type`；`limit≤200` | LOF/ETF 折溢价快照（按 \|premium_rate\| 降序，含申赎状态） | fund_premium_snapshot |
| `GET /funds/arbitrage-signals` | `status∈ACTIVE,EXPIRED,EXECUTED`；`limit≤200` | 溢价 Z-score 套利信号（按 \|z_score\| 降序） | arbitrage_signal |
| `GET /etf/share-size` | `trade_date`；`limit≤500` | ETF 每日规模/份额 | etf_share_size |

## 市场统计（A6，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /option-chain` | `underlying`（默认510050）；`trade_date`；`call_put∈C,P`；`limit≤1000` | ETF 期权链（希腊字母/IV） | option_chain |
| `GET /market/stage-snapshot` | `trade_date`；`stage` | 分时段市场快照（payload 解析后透出） | market_stage_snapshot |

## 复权因子 / 分钟K线 / wolf 透传（B，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/fq-factors` | `code`*；`start/end`；`limit` | 复权因子历史（tushare 按日全市场批量同步） | fq_factors（新表） |
| `GET /stocks/minute` | `code`*；`trade_date`；`period∈5m,15m,30m,60m` | 5 分钟K线（15/30/60m 由 5m SQL 聚合）。**覆盖范围：每日热门池**（cap 300 只，滚动保留 60 交易日） | minute_bars（新表） |
| `GET /stocks/ticks` | `code`*；`trade_date` | 逐笔成交（wolf /wolf/deal 实时透传，不落库；cap 2000 行） | — |
| `GET /stocks/quote5` | `code`* | 买卖五档（wolf /wolf/time/five 透传，不落库） | — |

透传端点 meta 标注 `passthrough: wolf`；wolf 未配置或失败时返回 502 `UPSTREAM_UNAVAILABLE`。分钟线历史回补：`python agent/scripts/backfill_minute_bars.py --date <YYYY-MM-DD> --codes <逗号代码>`。

## 打板专题：异动/竞价/游资/热度（C，2026-08-15 新增）

| 端点 | 参数 | 说明 | 数据表 |
|---|---|---|---|
| `GET /stocks/unusual` | `trade_date`；`type`(1-22)；`code`；`limit≤500` | 盘中个股异动（封板/炸板/火箭发射/大笔买入等，按时间倒序） | unusual_event（新表，盘中5分钟+盘后回补，保留120交易日） |
| `GET /stocks/unusual/types` | — | 22 种异动类型字典 | — |
| `GET /stocks/call-auction` | `code`（单股竞价演变）或 `latest=1`（全市场终态，按竞价金额降序）；`trade_date` | 集合竞价快照（价格/量额/未匹配量/买卖方向） | call_auction_snapshot（新表，9:15-9:30 窗口，wolf 全市场主源/tpdog 热门池降级，保留60交易日） |
| `GET /hot-money/daily` | `trade_date`；`hot_name` 模糊；`limit≤500` | 游资每日榜单（买卖净额/上榜理由，按净额绝对值降序） | hot_money_daily（新表，盘后 01302） |
| `GET /hot-money/list` | — | 游资名录 | hot_money_list（新表，01301） |
| `GET /stocks/hot-history` | `code`*；`days≤250`；`source` | 个股热度历史曲线（rank/hot_value 逐日） | hot_list（已有数据直查） |
