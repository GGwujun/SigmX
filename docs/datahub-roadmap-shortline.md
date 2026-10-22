# Data Hub 短线专题路线图（VA cn_shortline_* 14 端点候选池）

> **状态：2026-10-22 已全部实现**（commits 56c009f / c4c107e + API 提交）。
> 落地形态与本路线图候选一致但更进一步：14 个计算全部从本地已同步表派生
> （`shortline_snapshot` 单表 14 kind，写侧一个 dataset、读侧 14 端点，
> 零新 HTTP 依赖），文档见 docs/datahub-api.md「短线专题」节。下文保留作
> 口径出处与缓存语义讨论记录。
>
> 来源：参考项目 Vibe-AStock（VR 底座 + 短线专题）datasources/registry.json 的
> 14 个 `cn_shortline_*` 计算型端点。本文档是 Data Hub 下一批 dataset 的候选池，
> **本期不实现**；缓存语义照抄 VA registry notes 原文表述。
> VA 的实现模式：计算型端点 = 取数层确定性计算（非 calc DAG），信封
> `extra.result` 完整结构化结果 / `extra.text` 给模型读的文字版 /
> `extra.computation` 记参数供复算。

## 三档缓存语义（VA 原文归纳）

| 档 | VA 表述 | SigmX 对应 |
|---|---|---|
| 已收盘幂等 | 「已收盘的日子结果不变（可）长期缓存；历史靠缓存越积越长」 | 落库为 post_close dataset（per_day），market.db 天然累积——不需要读侧缓存 |
| 盘中 | 「没收盘的那一天一律 partial，取数服务不缓存 partial，免得盘中的数被冻住」 | 盘中不快照（等收盘定稿），或入 intraday 相位随 5 分钟批整体刷新 |
| 快照 | 「缓存最多 15 秒（页面轮询不叠加，隔天也不会读到旧数）」 / 「缓存最多 1 小时」 | 读侧 TTL 缓存与 SigmX 哲学相悖（market.db 即缓存，失效=同步节奏）——live 型改 intraday 相位 dataset |

## 14 端点清单

| id | 含义 | VA 数据源 | VA 缓存语义（notes 原文摘录） | 请求量级 |
|---|---|---|---|---|
| `cn_shortline_emotion` | 当日打板情绪四项读数 | eastmoney+calc | 已收盘幂等长缓存；盘中一律 partial 不缓存 | ~8 次东财，串行限流 10–20s |
| `cn_shortline_cycle` | 情绪周期（连板高度/轮动，lookback 3–30 默认 10 天） | eastmoney+calc | 同上；每交易日 2 次请求 × lookback，全家族最慢所以单独成端点 | ~2×lookback 次 |
| `cn_shortline_daily` | 六项日读数（stats_context 口径，与 emotion/facts 同名证据一致） | eastmoney+calc | 已收盘长期缓存，历史靠缓存越积越长；盘中 partial | ~4 次 |
| `cn_shortline_settled` | 昨日涨停样本统计（backtest 取数；样本只含留在涨停池的票，冲板没封住的不在内；封板时间是最后封板时间非首封） | eastmoney+calc | 已收盘长期缓存；东财池只留最近一个月 | 1 次 |
| `cn_shortline_structure` | 每日结构读数（制度构成按涨跌幅规则年代归类；最高标按连板数、同高按首封时间、最多 5 只；池子为空不标 partial） | eastmoney+calc | 已收盘长期缓存；盘中 partial | ~4 次 |
| `cn_shortline_live` | 实时情绪（只算今天此刻；开盘前/集合竞价/收盘集合竞价/非交易日直接说明没有，不拿上一交易日冒充） | eastmoney+calc | 快照档：cache_max_age_sec=15 | ~5 次 |
| `cn_shortline_ladder` | 昨日梯队（date=盯的那一场，不给=今天；不改用其他日期的名单；涨停池为空不当 0 只） | eastmoney+calc | 样本日已收盘，结果不变、长期缓存 | 1 次 |
| `cn_shortline_turnover_top` | 昨日成交前十（只算沪深京 A 股号段；date 缺省=最近一个盘后包已发布的交易日，当天 17 点后才有） | tdx+calc | 已发布的日子结果不变、长期缓存 | 下载 ~2.7MB、~10s |
| `cn_shortline_bigcaps` | 500 亿大票池（只出名单和总市值，价格涨跌由界面另取；盘中翻页期间排名在变，页边界附近个别票可能漏掉，重复已去掉） | sina | 快照档：cache_max_age_sec=3600 | 500 亿 ≈ 4 页、~20s |
| `cn_shortline_facts` | 打板事实（主板 ST 跌停按 2026-07-06 起的 10% 判，此前 5%） | eastmoney+calc | 已收盘幂等长缓存；盘中 partial 不缓存 | — |
| `cn_shortline_themes` | 涨停题材树（配 IWENCAI_API_KEY 先问问财，出错或没配走同花顺涨停揭秘；取不到原因整棵树不可用，不拿行业分类冒充题材） | eastmoney+ths+calc | 已收盘长期缓存；盘中 partial | top 3–30 |
| `cn_shortline_firstboard` | 首板名单（涨停原因来源同 themes；原因取不到时名单照出、标 partial 不缓存，下次再取） | eastmoney+ths+calc | 已收盘长期缓存；盘中 partial | — |
| `cn_shortline_board_ladder` | 连板天梯（板位按东财连板数，反包票标「N天M板」；晋级=昨天这一档今天还在涨停池；最高标断板那档今天没人也留一行；原因取不到时天梯照出标 partial） | eastmoney+ths+calc | 已收盘长期缓存；盘中 partial | — |
| `cn_shortline_theme_rotation` | 题材轮动（按涨停原因标签归组、滤掉国企改革/破净等属性词、同义不同名分开算；某天池子或原因没取到按缺数 None 处理标 partial，不当 0） | eastmoney+ths+calc | 已收盘长期缓存；盘中 partial；days 3–10 默认 5 | ~2×days 次 |

## 在 _SPECS 里的建议条目形状

12 个复盘型端点映射为 post_close dataset（`market.db 即缓存`，历史由落库
天然累积，恰好解决 VA「东财池只留最近一个月、历史靠读侧缓存越积越长」的
依赖）；live/bigcaps 两个快照型映射为 intraday dataset（用 5 分钟同步相位
替代 VA 的 15s/1h 读侧 TTL）。示例：

```python
# 复盘型（12 个同形状，表名/量级各异）：
DatasetSpec(
    id="shortline_emotion",          # cn_shortline_emotion
    table="shortline_emotion",       # 新表：当日情绪四项，一日一行(JSON payload)
    source="derived",                # 由已同步的 zt/dt/zb_pool + capital 表确定性计算
    phases=frozenset({"post_close"}),
    invalidation="per_day",          # 已收盘幂等 == 每日定稿一次，永不重算
    minimum_rows=1,
    notes="计算型:取数层确定性计算,信封 extra.result/text/computation 三段式;"
          "盘中不算(等收盘定稿),历史靠 market.db 累积(替代 VA 读侧长缓存)。",
),
# live 型（1 个）：
DatasetSpec(
    id="shortline_live",
    table="shortline_live_snapshot",
    source="derived",
    phases=frozenset({"intraday"}),  # 入 5 分钟盘中批 = VA 的 15s TTL 降档为 5min
    invalidation="rolling_days", keep_days=30,
    notes="只算今天此刻;开盘前/集合竞价/非交易日直接写空并说明,不拿上一交易日冒充。",
),
# 快照型（1 个）：
DatasetSpec(
    id="shortline_bigcaps",
    table="shortline_bigcaps",
    source="sina",                   # VA 换源先例:东财 clist 成片失败 → 新浪
    phases=frozenset({"intraday", "post_close"}),
    invalidation="per_day",
    notes="500 亿大票池,只出名单和总市值;翻页期间排名在变,页边界可能漏个别票。",
),
```

前置依赖（实现顺序）：

1. zt/dt/zb/yzt_pool 与 capital 表已在同步（✅ 已有，2026-08 C 批交付）；
2. 涨停原因（themes 家族 5 个端点的公共依赖）：需要接入问财 API（
   IWENCAI_API_KEY）或同花顺涨停揭秘，二者都没有时整棵题材树不可用；
3. turnover_top 需要 tdx 盘后包（mootdx 已在用，17 点后可得）。

计费/分组建议：全部归 `shortline.v1` dataset 组；复盘型 fixed 3（finance.v1
同档），live 型 fixed 5（pro.v1 同档）。实现时同步登记
datahub_catalog._V1 + docs/datahub-api.md（test_datahub_parity 会强制三方一致）。
