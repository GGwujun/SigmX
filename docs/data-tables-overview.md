# SigmX 数据表总览（含字段）

> 更新日期：2026-08-02 | 服务器：阿里云 47.115.144.24 (Data Hub 模式)
> 数据库：SQLite `/home/vibe/.vibe-trading/market.db`
>
> 数据源状态：✅ 可用 | ❌ 不可用/被封 | △ 受限(限频/需积分) | ⚪ 待接入
> PK = 主键 | 🐕 = tpdog 兜底 | 🐺 = 黑狼数据可替代

---

## 核心行情数据

### bars_daily — 个股日K线 (286,760 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 (000001.SZ) |
| **trade_date** PK | TEXT | 交易日期 |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量 |
| total_amt | REAL | 成交额 |
| rise_rate | REAL | 涨跌幅 |
| t_rate | REAL | 换手率 |
| name | TEXT | 股票名称 |
| source | TEXT | 数据来源 |
| quality_status | TEXT | 质量标记 (verified/unverified/partial) |

- **主力源**: tushare `daily` 批量 → **兜底**: tpdog `stock_his/daily` 逐只 🐕 → 🐺wolf `/wolf/time/kline`
- **状态**: ✅ 全月 23/23 天完整，每天 ~5528 只

### stock_daily_basic — 每日估值 (53,430 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| close | REAL | 收盘价 |
| turnover_rate | REAL | 换手率 |
| turnover_rate_f | REAL | 自由流通换手率 |
| volume_ratio | REAL | 量比 |
| pe | REAL | 市盈率(静态) |
| pe_ttm | REAL | 市盈率(TTM) |
| pb | REAL | 市净率 |
| ps | REAL | 市销率 |
| ps_ttm | REAL | 市销率(TTM) |
| dv_ratio | REAL | 股息率 |
| dv_ttm | REAL | 股息率(TTM) |
| total_share | REAL | 总股本 |
| float_share | REAL | 流通股本 |
| free_share | REAL | 自由流通股本 |
| total_mv | REAL | 总市值 |
| circ_mv | REAL | 流通市值 |

- **主力源**: tushare `daily_basic` (5次/天限频) → **兜底**: tpdog `stock/info`+`stock/daily` 🐕
- **状态**: △ tushare 限频，tpdog ~5200 行/天（缺 ps/dv/total_share 等字段）

### index_daily — 指数日K线 (39,614 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 指数代码 (000001.SH) |
| **trade_date** PK | TEXT | 交易日期 |
| open/high/low/close | REAL | OHLC |
| pre_close | REAL | 前收盘价 |
| change | REAL | 涨跌额 |
| pct_chg | REAL | 涨跌幅 |
| volume | REAL | 成交量 |
| total_amt | REAL | 成交额 |

- **主力源**: tushare `index_daily` (5次/天) → **兜底**: tpdog `stock/daily` + akshare + 新浪 🐕 → 🐺wolf `/wolf/time/kline?symbol=index`
- **状态**: ✅ 全月完整，8 个指数/天

### etf_daily — ETF日K线 (36,072 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | ETF代码 |
| **trade_date** PK | TEXT | 交易日期 |
| open/high/low/close | REAL | OHLC |
| volume | REAL | 成交量 |
| total_amt | REAL | 成交额 |
| rise | REAL | 涨跌幅 |
| name | TEXT | 名称 |

- **主力源**: tushare `fund_daily` (无权限) → **兜底**: tpdog `etf_his/daily` 逐只 🐕 → 🐺wolf `/wolf/time/kline?symbol=etf`
- **状态**: ✅ 全月完整 (tpdog 覆盖)

### fund_daily — 基金日K线 (36,072 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 基金代码 |
| **trade_date** PK | TEXT | 交易日期 |
| open/high/low/close | REAL | OHLC |
| volume | REAL | 成交量 |
| total_amt | REAL | 成交额 |
| rise | REAL | 涨跌幅 |
| rise_rate | REAL | 涨幅 |
| nav | REAL | 净值 |
| iopv | REAL | 参考净值 |

- **主力源**: 镜像自 etf_daily
- **状态**: ✅ 跟随 etf_daily

### realtime_quote_snapshot — 实时盘口 (26,692 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| snapshot_at | TEXT | 快照时间 |
| name | TEXT | 名称 |
| price | REAL | 最新价 |
| pre_close | REAL | 前收盘 |
| open/high/low | REAL | OHLC |
| volume | REAL | 成交量 |
| total_amt | REAL | 成交额 |
| rise/rise_rate | REAL | 涨跌额/涨跌幅 |
| turnover_rate | REAL | 换手率 |
| source | TEXT | 来源 |

- **主力源**: tpdog `current/funds` 🐕 → 腾讯 `qt.gtimg.cn` → 🐺wolf `/wolf/time`
- **状态**: ✅ 正常

---

## 基础信息

### security_master — 股票基础信息 (5,535 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| symbol | TEXT | 简称 |
| name | TEXT | 全称 |
| area | TEXT | 地区 |
| industry | TEXT | 行业 |
| market | TEXT | 市场 (主板/创业板等) |
| exchange | TEXT | 交易所 |
| list_status | TEXT | 上市状态 (L/D) |
| list_date | TEXT | 上市日期 |
| delist_date | TEXT | 退市日期 |
| is_hs | TEXT | 沪深港通 |
| is_st | INTEGER | 是否ST |
| is_delisting | INTEGER | 是否退市 |
| is_bj | INTEGER | 是否北交所 |
| is_active | INTEGER | 是否活跃 |

- **主力源**: tushare `stock_basic` → **兜底**: tpdog `stock/list` 🐕 → 🐺wolf `/wolf/list`
- **状态**: ✅ 正常

### trade_calendar — 交易日历 (13,514 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 日期 |
| is_trading | INTEGER | 是否交易日 |
| market | TEXT | 市场 (CN) |

- **主力源**: akshare → **兜底**: tpdog `trade_dates` 🐕 + 周末规则
- **状态**: ✅ 正常

### etf_master — ETF基础信息 (1,584 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | ETF代码 |
| csname | TEXT | 简称 |
| extname | TEXT | 全称 |
| cname | TEXT | 基金公司名称 |
| index_code | TEXT | 跟踪指数代码 |
| index_name | TEXT | 跟踪指数名称 |
| setup_date | TEXT | 成立日期 |
| list_date | TEXT | 上市日期 |
| list_status | TEXT | 上市状态 |
| exchange | TEXT | 交易所 |
| mgr_name | TEXT | 基金经理 |
| custod_name | TEXT | 托管银行 |
| mgt_fee | REAL | 管理费 |
| etf_type | TEXT | ETF类型 |

- **主力源**: tushare `etf_basic` → **兜底**: tpdog `etfs/list` 🐕
- **状态**: ✅ 正常

### fund_master — 基金基础 (1,992 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 基金代码 |
| name | TEXT | 名称 |
| type | TEXT | 类型 |

- **主力源**: tushare `fund_basic` → akshare
- **状态**: ✅ 正常

### index_master — 指数基础 (1,161 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 指数代码 |
| name | TEXT | 名称 |
| type | TEXT | 类型 |
| req_code | TEXT | 请求代码 |

- **主力源**: tpdog `zs_list` 🐕 → 东财 datacenter
- **状态**: ✅ 正常

---

## 板块/行业

### board_master — 板块列表 (1,037 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 板块代码 |
| name | TEXT | 板块名称 |
| board_type | TEXT | 类型 (industry/concept/special) |
| req_code | TEXT | 请求代码 |

- **主力源**: tpdog `bk_list` 🐕 → 东财 datacenter
- **状态**: ✅ 正常

### board_members — 板块成分股 (0 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **board_code** PK | TEXT | 板块代码 |
| **stock_code** PK | TEXT | 股票代码 |
| board_type | TEXT | 板块类型 |
| stock_name | TEXT | 股票名称 |
| stock_exchange | TEXT | 交易所 |

- **主力源**: tpdog `bk_stocks` 🐕 → 🐺wolf `/wolf/sector`
- **状态**: ❌ 空表（tpdog 限频未拉到）

### board_daily — 板块日K线 (1,574 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **board_code** PK | TEXT | 板块代码 |
| **trade_date** PK | TEXT | 交易日期 |
| name | TEXT | 板块名称 |
| board_type | TEXT | 类型 |
| open/high/low/close | REAL | OHLC |
| volume/total_amt | REAL | 成交量/额 |
| rise/rise_rate/turnover_rate | REAL | 涨跌/换手 |

- **主力源**: tpdog `stock/daily` 🐕 → 东财 datacenter
- **状态**: ✅ 正常

---

## 涨停/资金池

### zt_pool — 涨停池 (444 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| price | REAL | 价格 |
| pct | REAL | 涨跌幅 |
| amount | REAL | 成交额 |
| float_cap | REAL | 流通市值 |
| turnover | REAL | 换手率 |
| limit_days | INTEGER | 连板数 |
| first_seal | TEXT | 首次封板时间 |
| last_seal | TEXT | 最后封板时间 |
| seal_fund | REAL | 封板资金 |
| break_times | INTEGER | 炸板次数 |
| industry | TEXT | 行业 |
| zt_stat | TEXT | 涨停统计 |
| source | TEXT | 来源 |

- **主力源**: 东财 `push2ex` → tpdog `pool/v1/zt` 🐕 → 🐺wolf `/wolf/zt`
- **状态**: ✅ 正常

### dt_pool — 跌停池 (170 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| price/pct/turnover | REAL | 价格/涨跌/换手 |
| pe | REAL | 市盈率 |
| seal_fund | REAL | 封单资金 |
| board_amount | REAL | 板上成交额 |
| dt_days | INTEGER | 连续跌停数 |
| open_times | INTEGER | 开板次数 |
| industry | TEXT | 行业 |

- **主力源**: 东财 `push2ex` → tpdog `pool/v1/dt` 🐕 → 🐺wolf `/wolf/dt`
- **状态**: ✅ 正常

### yzt_pool — 次新涨停池 (460 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| price/pct/turnover/amplitude/speed | REAL | 行情指标 |
| y_first_seal | TEXT | 首次封板时间 |
| y_limit_days | INTEGER | 连板数 |
| industry | TEXT | 行业 |
| zt_stat | TEXT | 涨停统计 |

- **主力源**: 东财 `push2ex` → tpdog `pool/v1/yzt` 🐕 → 🐺wolf `/wolf/cx`
- **状态**: ✅ 正常

### zb_pool — 炸板池 (184 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| price/limit_price/pct/turnover | REAL | 行情指标 |
| first_seal | TEXT | 首次封板时间 |
| break_times | INTEGER | 炸板次数 |
| amplitude/speed | REAL | 振幅/涨速 |
| industry | TEXT | 行业 |
| zt_stat | TEXT | 涨停统计 |

- **主力源**: 东财 `push2ex` → tpdog `pool/v1/zb` 🐕 → 🐺wolf `/wolf/zb`
- **状态**: ✅ 正常

### stock_pool — 通用股票池 (2,600 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **pool_type** PK | TEXT | 池类型 |
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| extra_json | TEXT | 额外数据(JSON) |

- **主力源**: tpdog `pool/v1/*` 🐕 + akshare
- **状态**: ✅ 正常

### dragon_tiger — 龙虎榜 (2,034 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| name | TEXT | 名称 |
| close | REAL | 收盘价 |
| rise_rate | REAL | 涨跌幅 |
| net_amt | REAL | 净买入额 |
| buy_amt | REAL | 买入额 |
| sell_amt | REAL | 卖出额 |
| extra_json | TEXT | 席位详情(JSON) |

- **主力源**: tpdog `board/bill` 🐕 → 沪深交易所官网 `dragon_tiger_backup`
- **状态**: ✅ 正常

---

## 资金流向

### fund_flow_daily — 个股日级资金流 (693 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| main_net | REAL | 主力净额 |
| small_net | REAL | 小单净额 |
| mid_net | REAL | 中单净额 |
| large_net | REAL | 大单净额 |
| super_net | REAL | 超大单净额 |
| net_amount | REAL | 总净额 |
| turnover | REAL | 换手率 |
| source | TEXT | 来源 |

- **主力源**: 新浪 `fund_flow_backup` → tpdog `fund/stock` 🐕 → 🐺wolf `/wolf/money`
- **状态**: ✅ 正常

### stock_capital_flow — 个股资金流排名 (2,918 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| **period** PK | INTEGER | 周期 (1/3/5/10日) |
| m_in/m_out/m_net | REAL | 主力流入/流出/净额 |
| r_in/r_out/r_net | REAL | 散户流入/流出/净额 |
| extra_json | TEXT | 额外数据 |

- **主力源**: 东财 `push2` clist → tpdog `01602` 🐕 → tushare
- **状态**: ✅ 正常

### stock_capital_rank — 资金流排名 (598 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **rank_type** PK | TEXT | 排名类型 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| main_net | REAL | 主力净额 |
| change_pct | REAL | 涨跌幅 |

- **主力源**: 东财 → akshare → tpdog 🐕
- **状态**: ✅ 正常

### sector_capital_flow — 板块资金流 (610 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **sector** PK | TEXT | 板块名称 |
| main_net | REAL | 主力净额 |
| change_pct | REAL | 涨跌幅 |

- **主力源**: 东财 → tpdog `01603` 🐕 → tushare
- **状态**: ✅ 正常

### northbound_flow — 北向资金 (1,572 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **time** PK | TEXT | 时间 (分钟) |
| hgt_yi | REAL | 沪股通净买额(亿) |
| sgt_yi | REAL | 深股通净买额(亿) |

- **主力源**: 同花顺 `hsgt_realtime` → ❌ HKEX/东财均缺净额
- **状态**: △ 单源 (无有效降级)

---

## 融资融券 / 大宗交易

### margin_trading — 融资融券 (881 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| rzye | REAL | 融资余额 |
| rzmre | REAL | 融资买入额 |
| rzche | REAL | 融资偿还额 |
| rqye | REAL | 融券余量 |
| rqmcl | REAL | 融券卖出量 |
| rqchl | REAL | 融券偿还量 |
| rzrqye | REAL | 融资融券余额 |

- **主力源**: 东财 `datacenter` → tpdog `stock_his/rz`+`rq` 🐕
- **状态**: ✅ 正常 (datacenter 可达)

### block_trade — 大宗交易 (283 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| price | REAL | 成交价 |
| close | REAL | 收盘价 |
| premium_pct | REAL | 溢价率 |
| vol | REAL | 成交量 |
| amount | REAL | 成交额 |
| buyer | TEXT | 买方 |
| seller | TEXT | 卖方 |

- **主力源**: 东财 `datacenter` → tpdog → tushare(无权限)
- **状态**: ✅ 正常

### holder_num — 股东户数 (65 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **end_date** PK | TEXT | 截止日期 |
| holder_num | INTEGER | 股东户数 |
| change_num | INTEGER | 变化数量 |
| change_ratio | REAL | 变化比例 |
| avg_shares | REAL | 户均持股 |

- **主力源**: 东财 `datacenter` → tpdog `f10/holder_num` 🐕
- **状态**: ✅ 正常

---

## 财务/基本面

### financial_snapshot — 财务快照 (3,670 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| trade_date | TEXT | 交易日期 |
| liutongguben | REAL | 流通股本 |
| zongguben | REAL | 总股本 |
| eps | REAL | 每股收益 |
| bvps | REAL | 每股净资产 |
| roe | REAL | 净资产收益率 |
| profit | REAL | 净利润 |
| income | REAL | 营业收入 |
| extra_json | TEXT | 额外数据 |

- **主力源**: mootdx `finance()` → tpdog `report/sc_get` 🐕 → 🐺wolf `/wolf/financemetric`
- **状态**: ✅ 正常

### financial_statement — 财报三表 (600 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **report_date** PK | TEXT | 报告期 |
| **report_type** PK | TEXT | 报表类型 (lrb/zcfzb/xjlb) |
| payload_json | TEXT | 完整报表数据(JSON) |

- **主力源**: 新浪 `financial_report` → tpdog `report/sc_get` 🐕
- **状态**: ✅ 正常

### eps_forecast — 一致预期EPS (3,501 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **trade_date** PK | TEXT | 交易日期 |
| **year** PK | TEXT | 预测年份 |
| count | INTEGER | 预测机构数 |
| min_eps/mean_eps/max_eps | REAL | 最低/均值/最高EPS |
| net_profit | REAL | 预测净利润 |
| source | TEXT | 来源 |

- **主力源**: 东财 `reportapi` → 同花顺
- **状态**: △ 需调参

### dividend_history — 分红派息 (572 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **ex_date** PK | TEXT | 除权除息日 |
| bonus_rmb | REAL | 每股红利(元) |
| transfer_ratio | REAL | 转增比例 |
| bonus_ratio | REAL | 送股比例 |
| plan | TEXT | 分配方案 |

- **主力源**: 东财 `datacenter` → tushare `dividend`
- **状态**: ✅ 正常

---

## 新闻/公告/热度

### announcement — 公司公告 (1,719 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **ann_date** PK | TEXT | 公告日期 |
| **title** PK | TEXT | 标题 |
| ann_type | TEXT | 类型 |
| url | TEXT | 链接 |

- **主力源**: cninfo → 东财公告(沪)+深交所(深)
- **状态**: △ cninfo 受限

### cls_telegraph — 财联社电报 (455 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **title** PK | TEXT | 标题 |
| content | TEXT | 内容 |
| time | TEXT | 时间 |

- **主力源**: CLS API → 金十快讯 → 新浪7×24
- **状态**: △ CLS 受限

### stock_news — 个股新闻 (1,170 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **title** PK | TEXT | 标题 |
| **trade_date** PK | TEXT | 交易日期 |
| url | TEXT | 链接 |
| source | TEXT | 来源 |
| summary | TEXT | 摘要 |
| news_date | TEXT | 发布时间 |

- **主力源**: 东财 `push2his` → 新浪7×24 → 🐺wolf (无新闻接口)
- **状态**: ❌ 东财被封

### hot_list — 热度榜 (202 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| **source** PK | TEXT | 来源 (ths/em) |
| name | TEXT | 名称 |
| rank | INTEGER | 排名 |
| hot_value | REAL | 热度值 |
| change_pct | REAL | 涨跌幅 |
| tags | TEXT | 标签 |

- **主力源**: 同花顺 → 东财人气榜 → tpdog `01903` 🐕
- **状态**: ❌ 同花顺 403

### ths_hot_reason — 题材归因 (475 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| reason | TEXT | 强势原因 |
| change_pct/turnover/amount/close | REAL | 行情指标 |
| market | TEXT | 市场 |

- **主力源**: 同花顺 → 东财概念命中
- **状态**: ❌ 同花顺 403

### ths_limit_up — 同花顺涨停 (441 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 股票代码 |
| name | TEXT | 名称 |
| price/pct | REAL | 价格/涨跌 |
| reason | TEXT | 涨停原因 |
| board_type | TEXT | 板块类型 |
| seal_rate | REAL | 封板率 |
| break_times | INTEGER | 炸板次数 |
| seal_amount | REAL | 封单额 |
| high_days | TEXT | 连板天数 |
| first_time | TEXT | 首封时间 |
| is_again | INTEGER | 是否连板 |

- **主力源**: 同花顺 → 东财
- **状态**: ❌ 同花顺 403

---

## 其他

### sector_snapshot — 板块快照 (2,511 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **board_type** PK | TEXT | 板块类型 |
| **name** PK | TEXT | 板块名称 |
| change_pct | REAL | 涨跌幅 |
| advancers/decliners | INTEGER | 上涨/下跌数 |
| leader | TEXT | 领涨股 |
| extra_json | TEXT | 额外数据 |

- **主力源**: 5源并联 (东财+腾讯+行业排名+tpdog 🐕)
- **状态**: ✅ 正常

### fund_premium_snapshot — LOF溢价 (11,143 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 基金代码 |
| **trade_date** PK | TEXT | 交易日期 |
| name/type | TEXT | 名称/类型 |
| price/nav/iopv | REAL | 价格/净值/参考净值 |
| premium_rate | REAL | 溢价率 |
| amount/change_pct | REAL | 成交额/涨跌 |
| redeem_status | TEXT | 赎回状态 |
| subscribe_status | TEXT | 申购状态 |
| signal | TEXT | 信号 |
| nav_date | TEXT | 净值日期 |
| purchase_status | TEXT | 购买状态 |
| purchase_limit/daily_limit | REAL | 限购额度 |
| fee_rate | REAL | 费率 |

- **主力源**: 东财 `push2his` → 新浪 + mootdx → tpdog 🐕
- **状态**: ❌ 东财被封

### option_chain — ETF期权链 (784 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **underlying** PK | TEXT | 标的代码 |
| **trade_date** PK | TEXT | 交易日期 |
| **code** PK | TEXT | 合约代码 |
| month | TEXT | 月份 |
| call_put | TEXT | 认购/认沽 |
| bid/ask/last | REAL | 买/卖/最新价 |
| strike | REAL | 行权价 |
| open_interest | REAL | 持仓量 |
| volume/amount | REAL | 成交量/额 |
| delta/gamma/theta/vega | REAL | Greeks |
| iv | REAL | 隐含波动率 |
| theory | REAL | 理论价 |

- **主力源**: 新浪 `option_*` (独家)
- **状态**: ✅ 正常

### lockup_expiry — 限售解禁 (39 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **code** PK | TEXT | 股票代码 |
| **free_date** PK | TEXT | 解禁日期 |
| free_shares | REAL | 解禁股数 |
| able_shares | REAL | 可流通股数 |
| free_ratio | REAL | 解禁比例 |
| lift_type | TEXT | 解禁类型 |

- **主力源**: 东财 `datacenter`
- **状态**: ✅ 正常

### global_market_index_daily — 海外指数 (42 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| **symbol** PK | TEXT | 指数代码 |
| name | TEXT | 名称 |
| open/high/low/close | REAL | OHLC |
| prev_close | REAL | 前收盘 |
| change_pct | REAL | 涨跌幅 |
| currency | TEXT | 货币 |
| source | TEXT | 来源 |
| history_json | TEXT | 历史数据 |

- **主力源**: yfinance → overseas_proxy
- **状态**: △ 需代理

### market_breadth_snapshot — 市场宽度 (6 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **trade_date** PK | TEXT | 交易日期 |
| total | INTEGER | 总数 |
| advancers/decliners/unchanged | INTEGER | 上涨/下跌/平盘 |
| limit_up/limit_down | INTEGER | 涨停/跌停 |
| max_limit_up_height | INTEGER | 最大连板高度 |
| turnover_billion | REAL | 成交额(亿) |
| source | TEXT | 来源 |

- **主力源**: akshare → 新浪 → tpdog 🐕
- **状态**: ✅ 正常

---

## 系统表

### sync_meta — 同步元数据 (1,270 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **key** PK | TEXT | 键 (daemon:日期, provider_diagnostic:...) |
| value | TEXT | 值 (时间戳/JSON) |

### sync_runs — 同步运行记录 (946 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **run_id** PK | TEXT | 运行ID |
| trade_date | TEXT | 交易日期 |
| worker_id | TEXT | Worker ID |
| status | TEXT | 状态 (pending/verified/published/failed) |
| started_at/finished_at | TEXT | 开始/结束时间 |
| error_summary | TEXT | 错误摘要 |

### sync_dataset_runs — 数据集同步详情 (16,191 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| **run_id** PK | TEXT | 运行ID |
| **dataset** PK | TEXT | 数据集名 |
| trade_date | TEXT | 交易日期 |
| status | TEXT | 状态 |
| expected_rows/received_rows/valid_rows/published_rows | INTEGER | 行数统计 |
| source | TEXT | 数据源 |
| missing_codes_json/invalid_rows_json/blocking_reasons_json | TEXT | 诊断JSON |

---

## 数据源提供商速查

| 提供商 | 状态 | 限制 | 覆盖表数 | 关键接口 |
|---|---|---|---|---|
| **tushare** | △ 受限 | daily_basic 5次/天, index_daily 5次/天, fund_daily 无权限 | ~15 | `daily` `daily_basic` `stock_basic` `etf_basic` |
| **tpdog 🐕** | ✅ 可用 | 积分制, 600s→3600s 预算 | ~30 | `stock_his/daily` `etf_his/daily` `pool/v1/*` `board/bill` |
| **东财 datacenter** | ✅ 可用 | datacenter-web.eastmoney.com | ~8 | `RPT_DATA_BLOCKTRADE` `RPTA_WEB_RZRQ_GGMX` |
| **东财 push2/push2his** | ❌ 被封 | 阿里云 IP 被拒 | 0 | (已迁 datacenter) |
| **新浪** | ✅ 可用 | 行情/7×24/财报/期权 | ~5 | `fund_flow_backup` `financial_report` `option_*` |
| **腾讯** | ✅ 可用 | qt.gtimg.cn | ~3 | `qt.gtimg.cn` 行情 |
| **同花顺** | ❌ 大部分被封 | 403, 仅 d.10jqka 可用 | ~2 | `hsgt_realtime` `d.10jqka` |
| **akshare** | ❌ 被封 | 阿里云依赖东财 push2 | 0 | (全部走东财) |
| **mootdx/tdx** | ✅ 可用 | TCP 7709 协议直连 | ~3 | `finance()` `kline()` |
| **cninfo** | △ 受限 | 部分端点 500 | ~2 | `announcement` `irm_qa` |
| **🐺 wolf** | ⚪ 待接入 | 需 token, 17 API | 可覆盖 ~15 | `/wolf/zt` `/wolf/time/kline` `/wolf/money` |

详细降级链设计见 `docs/data-source-plan.md` (v5) | 黑狼数据 API 文档见 `docs/wolf-api-official.md`
