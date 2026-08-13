# SigmX 数据源计划（v5 完整版）

> 生成于 2026-07-19，更新于 2026-08-02。基于：tpdog 90 接口文档 + 黑狼数据 17 接口文档（`docs/wolf-api-official.md`）+ a-stock-data SKILL.md（V3.4.0，43 端点）+ 服务器（阿里云 47.115.144.24）数据源实测 + 代码盘点（`market_sync.py`/`astock_client.py`）。
>
> 目的：为每张数据集表设计完整降级链，让链终止于**服务器可用的源**；tpdog 作为行情/基本面类的终极兜底；黑狼数据(wolf) 作为涨停/行情/资金流的补充源。

## 设计原则

1. **服务器可用源优先**：tushare(部分)✅、腾讯✅、新浪✅、mootdx/tdx协议✅、东财datacenter✅、HKEX✅、金十✅、同花顺F10/K线端点✅
2. **tpdog 作终极兜底**（标 🐕）：覆盖 30 张行情/基本面表，切付费即用
3. **黑狼数据(wolf) 作补充源**（标 🐺）：涨停/跌停/炸板/强势/次新/实时行情/K线/资金流/五档，API 文档见 `docs/wolf-api-official.md`
4. **每张表 ≥2 个独立风控面的源**：避免单源/单风控面被封即空
5. **避开已知坏点**：mootdx 库已停更（2024）→ 用 `tdx_client()` 协议直连；同花顺 `zx/basic` 子域服务器 403 → 但 `d.10jqka`/`basic.10jqka/api` 可用；东财 `push2`(实时行情)被封 → 用 `datacenter`(数据中心，可用)

## 图例

- ✅ 服务器实测可用 ｜ ❌ 服务器不可用 ｜ △ 受限/需调参/已知问题 ｜ ⚪ 未测 ｜ 🐕 tpdog 终极兜底 ｜ 🆕 本次核查新补的源

---

## 数据源计划总表

| # | 表 | 含义 | 现状降级链 | 主力源服务器 | 目标计划降级链(全源) | 目标链可用? | 改动 |
|---|---|---|---|---|---|---|---|
| 1 | bars_daily | 个股日线OHLCV | tushare→tpdog | tushare✅ | tushare→腾讯→百度K线→新浪→同花顺K线→🐺wolf(kline)→🐕tpdog(02203) | ✅✅✅✅✅✅✅ | 补腾讯/百度/新浪/同花顺K线 |
| 2 | index_daily | 指数日线 | tushare→tpdog→akshare→新浪 | tushare✅ | tushare→腾讯指数→🐺wolf(kline/index)→新浪→🐕tpdog(02202) | ✅✅✅✅✅ | 接 tencent_index_quote |
| 3 | stock_daily_basic | 每日估值PE/PB/换手 | 🔴tushare△单源 | tushare△ | tushare→腾讯→东财个股基本面🆕→🐕tpdog(00105) | △✅✅✅ | 接腾讯+eastmoney_stock_info |
| 4 | security_master | 股票基础信息 | tushare→tpdog | tushare✅ | tushare→🐕tpdog(00101)→东财个股基本面🆕 | ✅✅✅ | 补 eastmoney_stock_info |
| 5 | trade_calendar | 交易日历 | akshare→tpdog | akshare❌ | akshare→🐕tpdog(00109)→周末规则 | ❌✅✅ | OK |
| 6 | dragon_tiger | 龙虎榜 | 🔴tpdog❌单源 | tpdog❌ | 沪深交易所官方→东财全市场龙虎榜🆕→东财个股席位🆕→🐕tpdog(00401) | ✅✅✅✅ | 接官方+daily_dragon_tiger+dragon_tiger_board |
| 7 | index_master | 指数基础信息 | 🔴tpdog❌单源 | tpdog❌ | 东财datacenter→腾讯→🐕tpdog(00106) | ✅✅✅ | 补东财/腾讯 |
| 8 | board_master | 板块列表 | 🔴tpdog❌单源 | tpdog❌ | 东财datacenter→🐕tpdog(00107) | ✅✅ | 补东财 |
| 9 | board_members | 板块成分股 | 🔴tpdog❌单源 | tpdog❌ | 东财datacenter→🐕tpdog(00108) | ✅✅ | 补东财 |
| 10 | board_daily | 板块日线 | 🔴tpdog❌单源 | tpdog❌ | 东财datacenter→🐕tpdog(02204) | ✅✅ | 补东财 |
| 11 | stock_pool | 涨跌停/强势/炸板池 | tpdog+akshare并联 | tpdog❌akshare❌ | 东财四池→🐺wolf(zt/dt/zb/qs/cx)→akshare→🐕tpdog(00501-5) | ✅✅✅❌✅ | wolf涨停五接口全覆盖 |
| 12 | realtime_quote | 实时盘口 | tpdog→腾讯→akshare | tpdog❌ | 腾讯→🐺wolf(time/five)→交易所官方五档→tdx协议→新浪→🐕tpdog(02201) | ✅✅✅✅✅✅ | wolf五档毫秒级 |
| 13 | stock_capital_flow | 个股资金流 | tushare→tpdog→akshare→tpdog | tushare✅ | tushare→腾讯→新浪→🐕tpdog(01201) | ✅✅✅✅ | 补腾讯/新浪 |
| 14 | stock_capital_rank | 资金流排名 | akshare→东财→同花顺→tpdog→tushare | akshare❌ | 东财datacenter→东财分钟资金流🆕→tushare→🐕tpdog(01602) | ✅✅✅✅ | 补 eastmoney_fund_flow_minute |
| 15 | sector_capital_flow | 板块资金流 | akshare→东财→同花顺→tpdog→tushare | akshare❌ | 东财datacenter→tushare→🐕tpdog(01603) | ✅✅✅ | push2换datacenter |
| 16 | sector_snapshot | 板块快照 | 5源并联 | 多❌ | 东财datacenter+腾讯+行业排名🆕+🐕tpdog(00209)并联 | ✅✅✅✅ | 补 industry_comparison |
| 17 | market_breadth | 市场宽度 | akshare为主 | akshare❌ | 新浪→本地计算→🐕tpdog(01001/00206) | ✅✅✅ | 补新浪+tpdog |
| 18 | etf_master | ETF基础 | tushare→tpdog | tushare✅ | tushare→🐕tpdog(01501) | ✅✅ | OK |
| 19 | etf_daily | ETF日线 | tushare→tpdog | tushare✅ | tushare→🐕tpdog(01502) | ✅✅ | OK |
| 20 | etf_share_size | ETF规模 | tushare→akshare | tushare✅ | tushare→akshare→🐕tpdog(01501) | ✅❌✅ | 补tpdog |
| 21 | fund_master | 基金基础 | tushare+akshare | tushare✅ | tushare→akshare→🐕tpdog(01501) | ✅❌✅ | 补tpdog |
| 22 | fund_daily | 基金日线 | tushare+akshare | tushare✅ | tushare→akshare→🐕tpdog(01502) | ✅❌✅ | 补tpdog |
| 23 | fund_premium | 基金溢价 | akshare→mootdx→tpdog→sina | mootdx✅sina✅ | akshare→tdx协议(避mootdx库)🆕→sina→🐕tpdog(01505) | ❌✅✅✅ | mootdx换tdx_client |
| 24 | margin_trading | 融资融券 | 🔴东财push2❌单源 | 东财push2❌ | 东财datacenter→🐕tpdog(02101-4) | ✅✅ | 改datacenter+tpdog |
| 25 | block_trade | 大宗交易 | 🔴东财push2❌单源 | 东财push2❌ | 东财datacenter→🐕tpdog(游资近似△) | ✅△ | 改datacenter(tpdog游资近似) |
| 26 | holder_num | 股东户数 | 🔴东财❌单源 | 东财❌ | 东财datacenter→tushare→🐕tpdog(01802) | ✅✅✅ | 三源 |
| 27 | dividend_history | 分红派息 | 🔴东财❌单源 | 东财❌ | 东财datacenter→tushare→🐕tpdog(01801) | ✅✅✅ | 三源 |
| 28 | lockup_expiry | 限售解禁 | 东财(已接) | 东财dc✅ | 东财datacenter→🐕tpdog(01801) | ✅✅ | 补tpdog |
| 29 | stock_news | 个股新闻 | 🔴东财push2❌单源 | 东财push2❌ | 东财datacenter→新浪7×24→(tpdog无) | ✅✅ | 接新浪7×24 |
| 30 | announcement | 公司公告 | 🔴cninfo△单源 | cninfo△ | cninfo→东财公告(沪)/深交所(深)→(tpdog无) | △✅✅ | 接 announcements_backup |
| 31 | cls_telegraph | 财联社电报 | 🔴cls△单源 | cls△ | cls→金十快讯→东财7×24→(tpdog无) | △✅✅ | 接金十+eastmoney_global_news |
| 32 | irm_qa | 互动易问答 | 🔴cninfo单源 | cninfo irm✅ | cninfo irm→(tpdog无,独家) | ✅ | OK(独家,irm可用) |
| 33 | ths_hot_reason | 题材归因 | 🔴同花顺❌单源 | 同花顺❌ | 东财datacenter→东财概念命中🆕→🐕tpdog(01803概念) | ✅✅△ | 接 em_hot_concept+tpdog |
| 34 | hot_list | 热度榜 | 🔴同花顺❌单源 | 同花顺❌ | 东财人气榜→🐕tpdog(01903) | ✅✅ | 接 eastmoney_popularity |
| 35 | eps_forecast | 一致预期EPS | 🔴同花顺❌单源 | 同花顺❌ | 东财研报reportapi🆕(含三年EPS)→同花顺→(tpdog无) | △⚪ | 接 eastmoney_reports 研报层 |
| 36 | northbound_flow | 北向资金 | 🔴同花顺❌(sgt已知坏△) | 同花顺❌ | **无有效降级**（见下） | ❌ | 见下方 #36 说明 |
| 37 | financial_snapshot | 财务快照 | 🔴mootdx✅单源 | mootdx✅(库停更△) | tdx协议🆕→同花顺F10→新浪财报→🐕tpdog(01401) | ✅✅✅✅ | mootdx换tdx+补同花顺F10 |
| 38 | financial_statement | 财报三表 | 🔴新浪✅单源 | 新浪✅ | 新浪→同花顺F10三表→🐕tpdog(01401) | ✅✅✅ | 补同花顺F10 |
| 39 | option_chain | ETF期权 | 🔴新浪✅单源 | 新浪✅ | 新浪→(tpdog无期权,独家) | ✅ | OK(新浪独家可用) |
| 40 | global_market_index | 海外指数 | yfinance→Yahoo代理 | 需代理 | yfinance→overseas_proxy→(tpdog仅境内) | △✅ | OK(代理兜底) |
| 41 | dt_pool/ths_limit_up | 打板池 | 东财四池+同花顺 | 东财push2❌ | 东财datacenter→同花顺→打板情绪🆕→🐕tpdog(00501) | ✅⚪✅✅ | push2换dc+接 limit_up_sentiment |

---

## 统计

- **tpdog 终极兜底**：30 张表（#1-28 除 #25，加 #33/34/37/38/41）
- **服务器改造后可自给**：~39 张
- **真正边界（a-stock-data + tpdog 均无好方案）**：4 张 —— irm_qa / option_chain / global_market_index / us_theme
- **本次新补的源（11 个）**：同花顺K线、东财个股基本面、东财全市场龙虎榜、东财个股席位、交易所官方五档、东财分钟资金流、行业排名、东财概念命中、东财研报reportapi、tdx协议(替mootdx库)、北向本地CSV缓存、打板情绪

---

## 实施优先级（按 ROI 排序）

### 期 1：接线死代码 + 已写好的备胎（零开发量，立即见效）
1. `dragon_tiger_backup` → 解 #6 dragon 单源（官方零鉴权）
2. `announcements_backup` → 解 #30 announcement 单源
3. `tencent_index_quote` → 解 #2 index_daily 兜底
4. `fund_flow_backup`(已接) 确认 + `eastmoney_popularity`(已接) 接线 → #34 hot_list

### 期 2：服务器可用的新备胎（中等工作量）
5. HKEX 北向 → #36（实测✅）
6. 新浪7×24 → #29 stock_news（实测✅）
7. 东财研报 reportapi → #35 eps_forecast
8. 金十快讯 → #31 cls_telegraph 备胎
9. 同花顺F10 → #37/#38 财务（实测✅）

### 期 3：东财 push2→datacenter 迁移 + tpdog 兜底接线
10. margin/block/holder/dividend/lockup/stock_pool/ths 系：push2 换 datacenter（已知可用）
11. 给 30 张表接线 tpdog 兜底（你后期切付费即用）

#### 期 3 复核（2026-07-19，基于实测重排，非按文档清单盲做）

**Track A（push2→datacenter）实测后大幅缩水**——文档"现状链"多处过时：
- #24/#25/#26/#27/#28（margin/block/holder/dividend/lockup）：**早已迁 datacenter**（`eastmoney_datacenter` helper），且 datacenter ✅ 可用。非"push2单源"。
- #11/#41 涨跌停池：push2ex 当前**可达**（实测返回涨停数据），且 `pool/v1` tpdog 已接（`_sync_pools`）。datacenter **无等价报表**（涨停池报表名全 9501），不做无效迁移。
- #14/#15/#16 资金流排名/板块资金流：push2 clist 当前**可达**，且东财产品划分上实时排名只走 push2（datacenter 无实时资金流排名报表）。这 3 张已有 5 层兜底链（akshare→push2→ths→tpdog→tushare），push2 只是中间层，迁移无等价目标。
- → **Track A 无可做项**（都有合理替代或东财产品设计上无 datacenter 等价物）。

**Track B（tpdog 兜底）已接线（4 张，逻辑对齐契约，未实测真实数据——需配 TPDOG_TOKEN）**：
- #37 financial_snapshot ← tpdog `report/sc_get`(01401 按期财报) 填 eps/bvps/roe/profit/income
- #38 financial_statement ← tpdog `report/sc_get`(01401) 作三表全失败后的 lrb 兜底
- #24 margin_trading ← tpdog `stock_his/rz`+`stock_his/rq`(02101/02102 融资融券)
- #26 holder_num ← tpdog `f10/holder_num`(01802 F10股东数)
- #34 hot_list ← tpdog `current/v1/hot`(01903 个股热榜，ths 失败时兜底)

**Track B 经核实 tpdog 90 接口无对应项（跳过，文档原标注过时）**：
- #25 block_trade / #27 dividend / #28 lockup：tpdog 无大宗交易/分红/解禁接口（01801 是股本≠解禁/分红）
- #20 etf_share_size / #21 fund_master / #22 fund_daily / #23 fund_premium：tpdog 只有 ETF 行情(01502/01503)，无基金规模/份额/溢价
- #33 ths_hot_reason：tpdog 01803 是"静态概念归属"，与"当日强势股归因"语义不同，不接（避免污染）
- #11 stock_pool：tpdog 已接（`pool/v1`，期前就有）

**已接线（期前就有，复核确认）**：#1-10/#11-13/#18/#19 的 tpdog 兜底早已存在。

### 期 4：增强（锦上添花）
12. mootdx 库 → tdx_client 协议直连（#23/#37 避开停更库）
13. em_hot_concept/industry_comparison/daily_dragon_tiger/dragon_tiger_board 等增强函数

#### 期 4 进展（2026-07-19）

**mootdx 整改（#12）已完成，并意外修了一个长期静默 bug**：
- `tdx_client()` 改为复用 `mootdx_helper.pick_server()`（TTL 缓存 + 8 IP 健康探测），消除 astock_client 与 mootdx_helper 维护两套 IP 清单/探测逻辑的分叉。原 `_TDX_SERVERS`（3 IP）已删。
- **bug 修复**：`mootdx_finance()` 之前直接 `return client.finance(symbol=)` 返回 **DataFrame**（mootdx 0.11+ 行为），而调用方 `_sync_financial_snapshot` 用 `if data:` / `or {}` 判断 → 触发 `ValueError: truth value ambiguous` 被外层 except 吞掉 → **financial_snapshot 表的 mootdx 主源长期 100% 失效**，全靠期3 的 tpdog 兜底撑着（无 token 时全空）。现 DataFrame→dict 转换 + 拼音字段映射（jinglirun→profit, zhuyingshoulu→income, meigujingzichan→bvps），主源恢复可用。实测茅台流通股本12.5亿/净利润2724亿入库。

**em_hot_concept 等增强函数（#13）未做**：4 个函数（em_hot_concept/industry_comparison/daily_dragon_tiger/dragon_tiger_board）全未实现，且无下游消费确认（前端/风控未引用），属真·锦上添花，待有明确需求再做。

---

## 服务器数据源实测结果（2026-07-19，阿里云 47.115.144.24）

| 源 | 状态 | 备注 |
|---|---|---|
| tushare | daily✅ daily_basic△(5次/天) dividend✅ holder_num✅ margin/block/top_list❌(无权限) | 积分受限 |
| tpdog | ❌ `api.tpdog.com` DNS 挂 | 子域名问题，`www.tpdog.com` 可解析 |
| 🐺 wolf (黑狼数据) | ⚪ 待接入 | `api.fxyz.site` 17 API，token 认证，详见 `docs/wolf-api-official.md` |
| akshare/东财push2 | ❌ Connection aborted | 阿里云被封 |
| 东财 datacenter | ✅ HTTP 200 | datacenter-web.eastmoney.com 可用 |
| 东财 reportapi(研报) | △ 域名通(400需调参) | reportapi.eastmoney.com |
| 东财公告(沪市 np-anotice) | ✅ | |
| 腾讯 qt.gtimg.cn | ✅ | |
| 百度股市通 | ✅ | |
| 新浪(行情/7×24/财报/期权) | ✅ | |
| mootdx/tdx 协议 | ✅ 23834 rows | TCP 7709 |
| HKEX | ✅ 1.4s | hkex.com.hk |
| 金十 jin10 | ❌ 502/404/SSL EOF（2026-07-19 复测全挂） | flash-api/get_flash_list 502；flash_newest.js SSL EOF；#31 改用新浪7×24 降级 |
| 东财 7×24 np-weblist | ❌ data 空（2026-07-19 复测） | getFastNewsList 返回 data=None；#31 不作 cls 备胎 |
| 新浪 7×24 zhibo feed | ✅ | ext.stocks(JSON串)带个股关联，#29 个股新闻 + #31 cls 降级共用 |
| 同花顺 basic/zx | ❌ 403 | 被封 |
| 同花顺 d.10jqka(K线) | ✅ | |
| 同花顺 basic.10jqka/api(F10) | ✅ 1.7s | |
| cninfo 公告主域 | △ 500(需带参) | |
| cninfo irm 互动易 | ✅ | |

---

## #36 northbound_flow 降级链复核（2026-07-19，结论：当前无有效同形态降级）

`northbound_flow` 表存的是**沪股通净买额 hgt_yi**（同花顺 hexin 分钟序列）。复核目标链三个备胎源：

- **HKEX 官方**：原 `data_tab_daily_*.js` 端点 **404 全挂**（HKEX 改版下线）；Mutual-Market 页数据靠前端异步加载，无简单 JSON 可取。**不可达。**
- **东财 datacenter `RPT_MUTUAL_DEAL_HISTORY`**：接口通、有数据，但 `MUTUAL_TYPE=001`（沪股通）`NET_DEAL_AMT=None` ——**沪股通净额不披露**；仅 `002`（深股通）有净额(1910.48 万元)，`003`（北向合计）净额亦 None。**补不齐 hgt 净额。**
- **本地 CSV 缓存**：仅缓存历史、不产生新数据，非降级源。

根因：2024 后北向**净买额**披露全网收紧（hgt/sgt），同花顺 hexin 是少数还能给 hgt 分钟净额的源；HKEX/东财/新浪在 hgt **净额**上均缺。强接只会写空 `hgt_yi` 的无意义行。

→ `hsgt_realtime` 维持单源（已是协议层最稳的取数点）。若要补**成交额/额度/深股通净额/十大活跃股**（东财有），需给 `northbound_flow` 表加列（schema 变更）——列为后续待办，不在本次降级范围内。

---

## 附：黑狼数据 (wolf) 接口 → 数据集映射

> API 文档：`docs/wolf-api-official.md` | Base URL: `http://api.fxyz.site` | 认证: `token` 参数
>
> 接入状态：⚪ 待接入（需申请 token）

| wolf 端点 | 映射 Dataset | 替代能力 | 备注 |
|---|---|---|---|
| `/wolf/time/kline?period=1d` | bars_daily | 个股日K线 OHLCV | 支持前/后复权，包年版支持 `code=all` 全市场 |
| `/wolf/time/kline?symbol=index` | index_daily | 指数日K线 | symbol=index |
| `/wolf/time/kline?symbol=etf` | etf_daily | ETF 日K线 | symbol=etf |
| `/wolf/time?code=all` | realtime_quote | 全市场实时行情快照 | 包年版，含 PE/PB/市值/ROE/换手率 |
| `/wolf/time?code=000001` | realtime_quote | 单股实时行情 | 含五档/涨跌停价/5-60日涨幅 |
| `/wolf/time/five` | realtime_quote | 买卖五档 | 毫秒级更新 |
| `/wolf/time/day?code=all` | realtime_quote | 日线快照 | 盘后 OHLCV |
| `/wolf/zt` | zt_pool | 涨停板 | 含封板资金/连板数/炸板次数 |
| `/wolf/dt` | dt_pool | 跌停板 | 含连续跌停/开板次数 |
| `/wolf/zb` | stock_pool(炸板) | 炸板股 | 含振幅/涨速/涨停价 |
| `/wolf/qs` | stock_pool(强势) | 强势股 | 含入选理由(60日新高/多次涨停) |
| `/wolf/cx` | stock_pool(次新) | 次新股 | 含开板日期/开板几日 |
| `/wolf/money` | fund_flow_daily | 资金流向 | 主买/主卖/特大/大/中/小单 |
| `/wolf/deal` | — | 逐笔交易 | 历史盘后6:00更新 |
| `/wolf/price` | — | 分价数据 | 历史盘后6:00更新 |
| `/wolf/sector` | board_members | 板块成分股 | hy/gn/ts 行业/概念/特色 |
| `/wolf/financemetric` | financial_snapshot | 财务核心指标 | ROE/EPS/BPS/毛利率等 22 项 |
| `/wolf/list` | security_master | 股票列表 | 按类型筛选(ETF/ST/指数等) |
| `/wolf/fq` | adj_factor | 复权变更 | 除权除息历史 |

### wolf vs tpdog 覆盖对比

| 能力 | wolf 🐺 | tpdog 🐕 |
|---|---|---|
| 涨停/跌停/炸板/强势/次新 | ✅ 5 接口全覆盖 | ✅ 5 接口 (00501-5) |
| 日K线 (个股/ETF/指数) | ✅ kline 多周期 | ✅ 24 K线接口 |
| 实时行情 + 五档 | ✅ time + five | ✅ 02201 盘口 |
| 资金流向 | ✅ money 大/中/小单 | ✅ 01201 个股 |
| 财务指标 | ✅ financemetric 22 项 | ✅ 01401 按期财报 |
| PE/PB/市值 批量 | ✅ `time?code=all` 全推 | ✅ 00105 逐只 |
| 板块成分 | ✅ sector | ✅ 00107/00108 |
| **daily_basic 替代** | **⚠️ 仅单股 `time`，无批量估值接口** | ⚠️ 同，逐只 00105 |
| 龙虎榜 | ❌ 无 | ✅ 00401/00402 |
| 融资融券 | ❌ 无 | ✅ 02101-02104 |
| 股东户数 | ❌ 无 | ✅ 01802 |
| ETF 规模/份额 | ❌ 无 | ✅ 01501 |

### wolf 接入优先级

1. **期 1（立即可做）**：`/wolf/zt` `/wolf/dt` `/wolf/zb` `/wolf/qs` `/wolf/cx` → 涨停池 5 接口替代 tpdog，解决 tpdog 单源问题
2. **期 2（中等价值）**：`/wolf/time/kline` → bars_daily / etf_daily / index_daily 补充源
3. **期 3（锦上添花）**：`/wolf/money` → fund_flow_daily；`/wolf/financemetric` → financial_snapshot

**关键短板**：wolf 无批量 daily_basic 接口（PE/PB/市值全市场），`/wolf/time?code=all` 仅包年版用户可用。对于非包年用户，daily_basic 仍需依赖 tushare 或 tpdog 逐只调用。



## 附：tpdog 90 接口分类速查（完整目录见 `agent/src/data/tpdog_doc.json`）

| 分类 | 接口数 | 代表接口 |
|---|---|---|
| 基础数据 | 7 | 00101股票列表/00106指数/00107版块/00109交易日/00105个股信息 |
| 个股F10 | 5 | 01801股本/01802股东数/01803核心概念/01804概念龙头 |
| 基金ETF | 7 | 01501列表/01502日K/01505秒级实时 |
| 全量扫描 | 5 | 01602个股资金流/01603版块资金流/00209版块筛选 |
| 批量实时 | 7 | 02201盘口/02202主指日K/02203股票日K/02204版块日K |
| 融资融券 | 4 | 02101-02104 |
| TOP榜单 | 5 | 01903个股热榜/01904飙升/01905概念热榜 |
| 龙虎榜单 | 2 | 00401龙虎榜/00402个股历史 |
| 股池数据 | 5 | 00501涨停/00502跌停/00503强势/00504炸板/00505次新 |
| K线历史/实时/周期 | 24 | 日/周/月/季/半年/年 + 1F-120F |
| 个股异动 | 4 | 00901-00904 |
| 资金流向 | 4 | 01201个股/01202行业/01203概念/01204地域 |
| 游资榜单 | 3 | 01301-01303 |
| 市场情绪 | 1 | 01001情绪监控 |
| 财报数据 | 1 | 01401按期财报 |
| 基础说明 | 3 | 09901-09999 |

---

## 附：a-stock-data 函数 → astock_client 接线状态

**已接线（已用）**：tencent_quote, ths_hot_reason, hsgt_realtime, lockup_expiry, margin_trading, block_trade, holder_num_change, dividend_history, stock_fund_flow_120d, eastmoney_stock_news, cls_telegraph, mootdx_finance, sina_financial_report, cninfo_announcements, em_zt/zb/dt/yzt_pool, ths_limit_up_pool, sina_option_*, cninfo_irm, ths_hot_list, eastmoney_popularity, fund_flow_backup

**已实现未接线（死代码，期1接线）**：baidu_kline_with_ma, eastmoney_concept_blocks, eastmoney_fund_flow_minute, eastmoney_global_news, mootdx_f10, limit_up_sentiment
> 复核（2026-08-14）：原 8 个里 `dragon_tiger_backup`、`tencent_index_quote` 实际**已接线**（market_sync.py 已调用，移出此列）。剩余 6 个仍为死代码——接线需要真实数据源联网验证返回值正确，避免脏数据污染降级链。这 6 个现已补解析单测覆盖（`agent/tests/test_astock_dead_code.py`，mock 网络验证解析 + 失败优雅降级），将来接线风险已降低。

**未实现（期2补）**：eastmoney_reports, eastmoney_industry_reports, download_pdf, iwencai_search/query, industry_comparison, daily_dragon_tiger, dragon_tiger_board, em_hot_concept, eastmoney_stock_info, announcements_backup
