# SigmX 数据表总览

> 更新日期：2026-08-02 | 服务器：阿里云 47.115.144.24 (Data Hub 模式)
>
> 数据源状态：✅ 可用 | ❌ 不可用/被封 | △ 受限(限频/需积分) | ⚪ 待接入

---

## 核心行情数据

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 1 | bars_daily | 个股日K线 OHLCV (5528只) | tushare `daily` 批量 | tpdog `stock_his/daily` 逐只 | ✅ 全月完整 |
| 2 | index_daily | 指数日K线 (8个) | tushare `index_daily` 1次/分 | tpdog `stock/daily` + akshare + 新浪 + 腾讯 | ✅ 全月完整 |
| 3 | stock_daily_basic | 每日估值 PE/PB/市值/换手 | tushare `daily_basic` 5次/天 | tpdog `stock/info`+`stock/daily` 逐只 | △ tushare 限频，tpdog ~5200/天 |
| 4 | etf_daily | ETF 日K线 (1584只) | tushare `fund_daily` 无权限 | tpdog `etf_his/daily` 逐只 | ✅ 全月完整(tpdog) |
| 5 | realtime_quote | 实时盘口/五档 | tpdog `current/funds` | 腾讯 `qt.gtimg.cn` + akshare | ✅ 正常 |

## 涨停/资金池

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 6 | zt_pool | 涨停池 | 东财 `push2ex` | tpdog `pool/v1/zt` | ✅ 正常 |
| 7 | dt_pool | 跌停池 | 东财 `push2ex` | tpdog `pool/v1/dt` | ✅ 正常 |
| 8 | yzt_pool | 次新涨停池 | 东财 `push2ex` | tpdog `pool/v1/yzt` | ✅ 正常 |
| 9 | zb_pool | 炸板池 | 东财 `push2ex` | tpdog `pool/v1/zb` | ✅ 正常 |
| 10 | stock_pool | 涨跌停/强势/炸板/次新 | tpdog `pool/v1/*` | akshare | ✅ 正常 |
| 11 | dragon_tiger | 龙虎榜 | tpdog `board/bill` | 沪深交易所官网 `dragon_tiger_backup` | ✅ 全月完整 |

## 资金流向

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 12 | fund_flow_daily | 个股日级资金流 | 新浪 `fund_flow_backup` | tpdog `fund/stock` | ✅ 正常 |
| 13 | fund_flow_120d | 120日资金流 | 东财 `push2his` | ❌ 无替代 | ❌ 东财被封 |
| 14 | stock_capital_flow | 个股资金流排名 | 东财 `push2` clist | tpdog + tushare | ✅ 正常 |
| 15 | sector_capital_flow | 板块资金流 | 东财 `push2` | tpdog + tushare | ✅ 正常 |
| 16 | northbound_flow | 北向资金 (沪股通净额) | 同花顺 `hsgt_realtime` | ❌ HKEX/东财均缺净额 | △ 单源 |

## 板块/行业

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 17 | board_master | 板块列表 (行业/概念/特色) | tpdog `boards/list` | 东财 datacenter | ✅ 正常 |
| 18 | board_members | 板块成分股 | tpdog `board/members` | 东财 datacenter | △ tpdog 限频 |
| 19 | board_daily | 板块日K线 | tpdog `stock/daily` | 东财 datacenter | ✅ 正常 |
| 20 | sector_snapshot | 板块快照 (行业+概念) | 东财 `push2` + tpdog | 5源并联 | ✅ 正常 |

## 融资融券 / 大宗交易

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 21 | margin_trading | 融资融券明细 | 东财 `datacenter` | tpdog `stock_his/rz`+`rq` | ✅ 正常 (东财datacenter可达) |
| 22 | block_trade | 大宗交易 | 东财 `datacenter` | tpdog(无) + tushare(无权限) | ✅ 正常 (东财datacenter可达) |
| 23 | holder_num | 股东户数 | 东财 `datacenter` | tpdog `f10/holder_num` | ✅ 正常 |

## 财务/基本面

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 24 | financial_snapshot | 财务快照 (EPS/BPS/ROE) | mootdx `finance()` | tpdog `report/sc_get` | ✅ 正常 |
| 25 | financial_statement | 财报三表 (利润/资产/现金流) | 新浪 `financial_report` | tpdog `report/sc_get` | ✅ 正常 |
| 26 | eps_forecast | 一致预期 EPS | 东财 `reportapi` | 同花顺 | △ 需调参 |
| 27 | dividend_history | 分红派息 | 东财 `datacenter` | tushare `dividend` | ✅ 正常 |

## 基础信息

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 28 | security_master | 股票基础信息 (5535只) | tushare `stock_basic` | tpdog `stock/list` | ✅ 正常 |
| 29 | trade_calendar | 交易日历 | akshare | tpdog `trade_dates` + 周末规则 | ✅ 正常 |
| 30 | etf_master | ETF 基础信息 (1584只) | tushare `etf_basic` | tpdog `etfs/list` | ✅ 正常 |
| 31 | fund_master | 基金基础信息 | tushare `fund_basic` | akshare | ✅ 正常 |
| 32 | fund_daily | 基金日K线 | tushare (无权限) | tpdog `etf_his/daily` | ✅ 正常(tpdog) |
| 33 | fund_premium_snapshot | LOF 溢价率 | 东财 `push2his` | 新浪 + mootdx + tpdog | ❌ 东财被封 |

## 新闻/公告/热度

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 34 | announcement | 公司公告 | cninfo | 东财公告(沪)+深交所(深) | △ cninfo 受限 |
| 35 | cls_telegraph | 财联社电报 | CLS API | 金十快讯 + 新浪7×24 | △ CLS 受限 |
| 36 | stock_news | 个股新闻 | 东财 `push2his` | 新浪7×24 | ❌ 东财被封 |
| 37 | hot_list | 个股热度榜 | 同花顺 | 东财人气榜 + tpdog `01903` | ❌ 同花顺 403 |
| 38 | ths_hot_reason | 题材归因 | 同花顺 | 东财概念命中 + tpdog | ❌ 同花顺 403 |

## 其他

| # | 数据表 | 说明 | 主力源 | 兜底源 | 当前状态 |
|---|---|---|---|---|---|
| 39 | lockup_expiry | 限售解禁 | 东财 `datacenter` | tpdog | ✅ 正常 |
| 40 | option_chain | ETF 期权链 | 新浪 `option_*` | (独家，无替代) | ✅ 正常 |
| 41 | global_market_index | 海外指数 | yfinance | overseas_proxy | △ 需代理 |
| 42 | irm_qa | 互动易问答 | cninfo irm | (独家，无替代) | ✅ 正常 |

---

## 数据源提供商汇总

| 提供商 | 状态 | 限制 | 覆盖表数 |
|---|---|---|---|
| **tushare** | △ 受限 | daily_basic 5次/天, index_daily 5次/天, fund_daily 无权限 | ~15 表 |
| **tpdog (托普量化)** | ✅ 可用 | 积分制, daily_basic 预算 600s (~1150只/天) | ~30 表 (终极兜底) |
| **东财 datacenter** | ✅ 可用 | datacenter-web.eastmoney.com | ~8 表 |
| **东财 push2/push2his** | ❌ 被封 | 阿里云 IP 被拒 | 0 (已迁 datacenter) |
| **新浪** | ✅ 可用 | 行情/7×24/财报/期权 | ~5 表 |
| **腾讯** | ✅ 可用 | qt.gtimg.cn | ~3 表 |
| **同花顺** | ❌ 大部分被封 | 403, 仅 d.10jqka/basic.10jqka 可用 | ~2 表 |
| **akshare** | ❌ 被封 | 阿里云依赖东财 push2 | 0 |
| **mootdx/tdx** | ✅ 可用 | TCP 7709 协议直连 | ~3 表 |
| **cninfo** | △ 受限 | 部分端点 500 | ~2 表 |
| **🐺 黑狼数据(wolf)** | ⚪ 待接入 | 需 token, 17 API, 无 daily_basic 批量 | 可覆盖 ~15 表 |

---

## 已知问题 (2026-08-02)

1. **daily_basic 覆盖率不足**：tushare 5次/天限频 + tpdog 预算 600s 仅覆盖 ~1150/5535 只 → 已加大 tpdog 预算到 3600s (~5200只/天)
2. **东财 push2his 被封**：fund_flow_120d/stock_news/fund_premium 受影响 → 迁移到 datacenter 或新浪
3. **同花顺 403**：hot_list/ths_hot_reason 受影响 → 迁移到东财/tpdog
4. **tushare fund_daily 无权限**：ETF 日线改用 tpdog 全量覆盖
5. **wolf 待接入**：需申请 token，可替代涨停五接口+K线+资金流
