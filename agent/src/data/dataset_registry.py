"""Central registry for canonical market datasets — 写侧唯一事实源.

每个 dataset 一条 :class:`DatasetSpec`：表名 / 主数据源 / 同步相位 / 层级 /
失效策略 / 行数契约。worker 与 market_sync 的数据集集合、表名映射、prune
保留天数全部从这里派生（``post_close_datasets()`` / ``intraday_datasets()``
/ ``table_for()`` / ``keep_days_for()``），消灭"同一清单手抄多处"的漂移。

source 词表（主源，多级兜底见各 sync 函数）：tushare / tpdog / eastmoney /
wolf / akshare / ths / sina / tencent / yfinance / mootdx / cninfo / cls /
derived（由其他 dataset 派生，无独立外部源）。

行数语义之外的行级校验仍在 :mod:`dataset_contracts`；本注册表只决定一个
降级的数据集阻断整个快照、还是作为 unavailable 发布。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetContract:
    minimum_rows: int = 1
    blocking: bool = False
    recommendation_input: bool = False
    # When True, a dataset that *fetched* rows but every row failed semantic
    # validation (valid_rows == 0 with received_rows > 0) still blocks
    # publication.  This distinguishes "data is corrupt" from "provider was
    # rate-limited / coverage incomplete" — the former must never ship even for
    # an advisory dataset, the latter degrades gracefully.
    hard_fail_on_zero_valid: bool = False


@dataclass(frozen=True)
class DatasetSpec:
    """写侧单个 dataset 的全部声明式元数据。"""

    id: str
    # 落库表名；None = 无 row-count 回退表（走语义校验，如 realtime）。
    table: str | None
    source: str
    # 同步相位集合；空集 = 随宿主 dataset 写入或按自有节奏跑（见 notes）。
    phases: frozenset[str]
    # 1 = 当日核心快照（先验证先发布，_POST_CLOSE_CORE）；2 = 增强。
    tier: int = 2
    # per_day = 每交易日快照、历史只增；cumulative = 全量累积、不 prune；
    # rolling_days = 只保留 keep_days 天。
    invalidation: str = "per_day"
    keep_days: int | None = None
    minimum_rows: int = 1
    blocking: bool = False
    recommendation_input: bool = False
    hard_fail_on_zero_valid: bool = False
    notes: str = ""


# 相位缩写：58 条 spec 里高频出现的组合。
_PC = frozenset({"post_close"})
_PM = frozenset({"premarket", "post_close"})
_ID = frozenset({"intraday"})
_IDC = frozenset({"intraday", "post_close"})
_ALL = frozenset({"premarket", "intraday", "post_close"})
_NONE = frozenset()


# ---------------------------------------------------------------------------
# 核心五件套（tier 1）：日核心宇宙。calendar/master/index 阻断发布；
# daily_basic/daily 降级不阻断（daily_basic 是 tushare 单源、限速 ~1次/分，
# 设 blocking 会让一次限速冻结整个核心发布——刻意 advisory）。
# ---------------------------------------------------------------------------
_SPECS: dict[str, DatasetSpec] = {spec.id: spec for spec in [
    DatasetSpec(
        id="calendar", table="trade_calendar", source="tpdog", phases=_PC, tier=1,
        minimum_rows=1, blocking=True,
        notes="交易日历；akshare 兜底。缺它=快照结构不可用，阻断。",
    ),
    DatasetSpec(
        id="master", table="security_master", source="tushare", phases=_PC, tier=1,
        minimum_rows=3000, blocking=True, hard_fail_on_zero_valid=True,
        notes="证券主档；tpdog 兜底。语义校验集成员。",
    ),
    DatasetSpec(
        id="daily_basic", table="stock_daily_basic", source="tushare", phases=_PC, tier=1,
        minimum_rows=1000,
        notes="每日指标；tpdog 按期兜底。tushare 单源限速，刻意 advisory。",
    ),
    DatasetSpec(
        id="index", table="index_daily", source="tushare", phases=_PC, tier=1,
        minimum_rows=4, blocking=True,
        notes="指数日线；tpdog→akshare→tencent→sina 多级链。",
    ),
    DatasetSpec(
        id="daily", table="bars_daily", source="tushare", phases=_PC, tier=1,
        recommendation_input=True,
        notes="个股日线；有独立的 reference 完整性检查。",
    ),

    # -----------------------------------------------------------------------
    # 主数据 / 参照表（post_close 刷新一次）
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="index_master", table="index_master", source="tpdog", phases=_PC,
        notes="指数主档。",
    ),
    DatasetSpec(
        id="board_master", table="board_master", source="tpdog", phases=_PC,
        notes="板块主档。",
    ),
    DatasetSpec(
        id="board_members", table="board_members", source="tpdog", phases=_PC,
        minimum_rows=3000, hard_fail_on_zero_valid=True,
        notes="板块成分股；语义校验集成员。",
    ),
    DatasetSpec(
        id="etf_master", table="etf_master", source="tushare", phases=_PC,
        notes="ETF 主档；tpdog 兜底。",
    ),
    DatasetSpec(
        id="fund_master", table="fund_master", source="eastmoney", phases=_PC,
        notes="基金主档；ETF 名录来自 etf_master，LOF 简称来自东财 openfund。",
    ),
    DatasetSpec(
        id="etf_size", table="etf_share_size", source="tushare", phases=_PC,
        notes="ETF 份额规模；akshare 兜底。",
    ),

    # -----------------------------------------------------------------------
    # 行情 / 池子
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="etf", table="etf_daily", source="tushare", phases=_PC,
        notes="ETF 日线。",
    ),
    DatasetSpec(
        id="fund_daily", table="fund_daily", source="derived", phases=_PC,
        notes="基金日线，由 etf_daily 派生落库。",
    ),
    DatasetSpec(
        id="board", table="board_daily", source="tpdog", phases=_PC,
        notes="板块日线。",
    ),
    DatasetSpec(
        id="dragon", table="dragon_tiger", source="tpdog", phases=_PC,
        notes="龙虎榜（board/bill）。",
    ),
    DatasetSpec(
        id="pool", table="stock_pool", source="tpdog", phases=_IDC,
        notes="涨跌停池主入口；akshare 兜底。zb/dt/yzt_pool 随本入口写入。",
    ),
    DatasetSpec(
        id="zt_pool", table="zt_pool", source="tpdog", phases=_IDC,
        minimum_rows=1, recommendation_input=True,
        notes="涨停池（推荐输入）。",
    ),
    DatasetSpec(
        id="zb_pool", table="zb_pool", source="tpdog", phases=_NONE,
        notes="炸板池；随 pool 同步写入，不单列相位。",
    ),
    DatasetSpec(
        id="dt_pool", table="dt_pool", source="tpdog", phases=_NONE,
        notes="跌停池；随 pool 同步写入。",
    ),
    DatasetSpec(
        id="yzt_pool", table="yzt_pool", source="tpdog", phases=_NONE,
        notes="昨日涨停池；随 pool 同步写入。",
    ),
    DatasetSpec(
        id="realtime", table=None, source="tpdog", phases=_ID,
        minimum_rows=3000, recommendation_input=True,
        hard_fail_on_zero_valid=True,
        notes="盘中实时快照；akshare 兜底。无 row-count 表，走语义校验。",
    ),
    DatasetSpec(
        id="call_auction", table="call_auction_snapshot", source="wolf", phases=_NONE,
        invalidation="rolling_days", keep_days=60,
        notes="集合竞价；wolf 全市场主源、tpdog 热门池降级。自有节奏"
              "（09:25/14:57），不入五分钟盘中批。env 覆盖："
              "MARKET_SYNC_CALL_AUCTION_KEEP_DAYS。",
    ),

    # -----------------------------------------------------------------------
    # 资金流
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="capital", table="stock_capital_flow", source="tushare", phases=_PC,
        notes="个股资金流；tpdog→akshare(ths) 链。",
    ),
    DatasetSpec(
        id="capital_rank", table="stock_capital_rank", source="akshare", phases=_IDC,
        minimum_rows=20, recommendation_input=True,
        hard_fail_on_zero_valid=True,
        notes="资金流排名；tushare→eastmoney→ths 链。语义校验集成员。",
    ),
    DatasetSpec(
        id="sector_capital", table="sector_capital_flow", source="akshare", phases=_IDC,
        minimum_rows=10, recommendation_input=True, hard_fail_on_zero_valid=True,
        notes="板块资金流；eastmoney→ths→tpdog 链。语义校验集成员。",
    ),
    DatasetSpec(
        id="fund_flow_daily", table="fund_flow_daily", source="sina", phases=_PC,
        recommendation_input=True,
        notes="个股日级资金流备胎（新浪）；tpdog fund/stock 终极兜底。",
    ),
    DatasetSpec(
        id="fund_flow_120d", table="fund_flow_daily", source="eastmoney", phases=_PC,
        notes="120 日资金流回补，与 fund_flow_daily 同表。",
    ),
    DatasetSpec(
        id="northbound", table="northbound_flow", source="ths", phases=_IDC,
        recommendation_input=True,
        notes="北向分钟流向。2024 后净买额披露全网收紧，单源（不接假降级）；"
              "盘中批次中唯一不阻断的成员。",
    ),

    # -----------------------------------------------------------------------
    # 板块 / 市场面
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="sector_snapshot", table="sector_snapshot", source="akshare", phases=_IDC,
        minimum_rows=10, recommendation_input=True,
        notes="板块快照；eastmoney→ths→tpdog→tushare 链。industry/concept 分表随写。",
    ),
    DatasetSpec(
        id="sector_snapshot_industry", table="sector_snapshot_industry", source="derived",
        phases=_NONE, minimum_rows=10,
        notes="行业板块快照；sector_snapshot 的行业分表。",
    ),
    DatasetSpec(
        id="sector_snapshot_concept", table="sector_snapshot_concept", source="derived",
        phases=_NONE, minimum_rows=10,
        notes="概念板块快照；sector_snapshot 的概念分表。",
    ),
    DatasetSpec(
        id="market_breadth", table="market_breadth_snapshot", source="akshare",
        phases=_IDC, minimum_rows=1, recommendation_input=True,
        hard_fail_on_zero_valid=True,
        notes="市场宽度；eastmoney clist 兜底。语义校验集成员。",
    ),
    DatasetSpec(
        id="stage_snapshot", table="market_stage_snapshot", source="derived", phases=_ALL,
        minimum_rows=1, recommendation_input=True,
        notes="盘面阶段快照；由 pool/capital/sector 快照计算，无独立外部源。",
    ),
    DatasetSpec(
        id="global_indices", table="global_market_index_daily", source="yfinance",
        phases=_PM,
        notes="全球指数；HSTECH 走 akshare（新浪源）。",
    ),
    DatasetSpec(
        id="us_theme", table="us_theme_snapshot", source="yfinance", phases=_PM,
        notes="美股主题（proxy symbol 映射）。",
    ),
    DatasetSpec(
        id="us_transmission", table="us_a_share_transmission", source="derived",
        phases=_PM,
        notes="美股→A股传导；由 us_theme 快照派生映射。",
    ),
    DatasetSpec(
        id="premium", table="fund_premium_snapshot", source="akshare", phases=_PC,
        notes="基金溢价快照（ETF+LOF 全市场 ~1900 只）；东财 spot 端点。",
    ),

    # -----------------------------------------------------------------------
    # 情绪 / 新闻 / 公告
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="premarket_news", table="premarket_news", source="akshare", phases=_PM,
        notes="盘前新闻；akshare 为主 + news_feed 多源补充。",
    ),
    DatasetSpec(
        id="ths_hot", table="ths_limit_up", source="ths", phases=_IDC,
        minimum_rows=5, recommendation_input=True,
        notes="同花顺热榜。",
    ),
    DatasetSpec(
        id="hot_list", table="hot_list", source="ths", phases=_IDC,
        minimum_rows=20, recommendation_input=True,
        notes="同花顺热榜 + 东财人气榜；tpdog 01903 兜底。",
    ),
    DatasetSpec(
        id="cls_telegraph", table="cls_telegraph", source="cls", phases=_IDC,
        minimum_rows=5, recommendation_input=True,
        notes="财联社电报；新浪 7×24 作独立风控面降级。",
    ),
    DatasetSpec(
        id="stock_news", table="stock_news", source="eastmoney", phases=_PC,
        recommendation_input=True,
        notes="个股新闻；新浪 7×24 全市场流兜底。",
    ),
    DatasetSpec(
        id="announcements", table="announcements", source="cninfo", phases=_PC,
        notes="巨潮公告；官方备胎降级。",
    ),
    DatasetSpec(
        id="irm_qa", table="irm_qa", source="cninfo", phases=_PC,
        notes="互动易问答（巨潮官方，不封 IP）。",
    ),

    # -----------------------------------------------------------------------
    # 基本面 / 专题扩展
    # -----------------------------------------------------------------------
    DatasetSpec(
        id="eps_forecast", table="eps_forecast", source="ths", phases=_PC,
        notes="一致预期 EPS；同花顺 worth 页为主，东财研报层降级。",
    ),
    DatasetSpec(
        id="financial_snapshot", table="financial_snapshot", source="mootdx",
        phases=_PC,
        notes="财务快照；mootdx 为主，tpdog 01401 终极兜底。",
    ),
    DatasetSpec(
        id="financial_statement", table="financial_statement", source="sina",
        phases=_PC,
        notes="财报三表；新浪为主，同花顺 F10 / tpdog 降级。",
    ),
    DatasetSpec(
        id="margin_trading", table="margin_trading", source="eastmoney", phases=_PC,
        notes="融资融券；东财 datacenter 为主，tpdog 02101/02102 兜底。",
    ),
    DatasetSpec(
        id="block_trade", table="block_trade", source="eastmoney", phases=_PC,
        notes="大宗交易；东财→tpdog→tushare 三级兜底。",
    ),
    DatasetSpec(
        id="holder_num", table="holder_num", source="eastmoney", phases=_PC,
        notes="股东户数；东财为主，tpdog 01802 兜底。",
    ),
    DatasetSpec(
        id="dividend_history", table="dividend_history", source="eastmoney",
        phases=_PC,
        notes="分红送转历史。",
    ),
    DatasetSpec(
        id="option_chain", table="option_chain", source="sina", phases=_PC,
        notes="ETF 期权合约（50ETF/300ETF/科创50ETF）。",
    ),
    DatasetSpec(
        id="lockup_expiry", table="lockup_expiry", source="eastmoney", phases=_PC,
        notes="限售解禁日历。",
    ),
    DatasetSpec(
        id="fq_factors", table="fq_factors", source="tushare", phases=_PC,
        minimum_rows=3000, invalidation="cumulative",
        notes="复权因子（adj_factor 按日全市场一次）；全量累积不 prune。"
              "tushare 失败日降级 PARTIAL。",
    ),
    DatasetSpec(
        id="minute_bars", table="minute_bars", source="tpdog", phases=_PC,
        minimum_rows=100, invalidation="rolling_days", keep_days=60,
        notes="5 分钟K线，只拉当日热门池（cap 300 只）；100 行 ≈ 2 只代码。"
              "env 覆盖：MARKET_SYNC_MINUTE_BARS_KEEP_DAYS。",
    ),
    DatasetSpec(
        id="unusual", table="unusual_event", source="tpdog", phases=_PC,
        minimum_rows=5, invalidation="rolling_days", keep_days=120,
        notes="个股异动；盘中 00902 实时 / 盘后 00903 回补。清淡日合法地少。"
              "env 覆盖：MARKET_SYNC_UNUSUAL_KEEP_DAYS。",
    ),
    DatasetSpec(
        id="hot_money", table="hot_money_daily", source="tpdog", phases=_PC,
        minimum_rows=10,
        notes="游资每日榜单（01302，收盘后全量）。",
    ),
    DatasetSpec(
        id="hot_money_list", table="hot_money_list", source="tpdog", phases=_PC,
        notes="游资名录（01301 静态小表，每日刷新）。",
    ),
]}


# prune 保留天数的 env 覆盖项（未设置时用 spec.keep_days 注册表默认值）。
_KEEP_DAYS_ENV = {
    "minute_bars": "MARKET_SYNC_MINUTE_BARS_KEEP_DAYS",
    "unusual": "MARKET_SYNC_UNUSUAL_KEEP_DAYS",
    "call_auction": "MARKET_SYNC_CALL_AUCTION_KEEP_DAYS",
}


# ---------------------------------------------------------------------------
# 派生视图（worker / market_sync 的常量从这里导出，不再各自手抄）
# ---------------------------------------------------------------------------

def post_close_datasets() -> frozenset[str]:
    return frozenset(d for d, s in _SPECS.items() if "post_close" in s.phases)


def post_close_core() -> frozenset[str]:
    """tier-1 核心集：先验证先发布，慢增强集未完成时活库也有可用宇宙。"""
    return frozenset(d for d, s in _SPECS.items() if s.tier == 1)


def intraday_datasets() -> frozenset[str]:
    return frozenset(d for d, s in _SPECS.items() if "intraday" in s.phases)


def premarket_datasets() -> frozenset[str]:
    return frozenset(d for d, s in _SPECS.items() if "premarket" in s.phases)


def table_map() -> dict[str, str]:
    """dataset → DB 表名（row-count 回退用）；无表的（realtime）不在其中。"""
    return {d: s.table for d, s in _SPECS.items() if s.table}


def table_for(dataset: str) -> str | None:
    spec = _SPECS.get(dataset)
    return spec.table if spec else None


def keep_days_for(dataset: str) -> int | None:
    """prune 保留天数：注册表默认值，env 覆盖项优先。

    env 值非法时沿用 ``int()`` 的抛错语义，由消费方既有的 try/except
    跳过本次 prune（保留更多数据，与迁移前行为一致）。
    """
    spec = _SPECS.get(dataset)
    if spec is None or spec.keep_days is None:
        return None
    env_name = _KEEP_DAYS_ENV.get(dataset)
    if env_name:
        return int(os.getenv(env_name) or spec.keep_days)
    return spec.keep_days


def spec_for(dataset: str) -> DatasetSpec | None:
    return _SPECS.get(dataset)


def contract_for(dataset: str) -> DatasetContract:
    spec = _SPECS.get(dataset)
    if spec is None:
        # 未注册 id（如 *_eastmoney/*_ths 组合面、测试桩）一律默认契约：
        # 最低 1 行、不阻断、可降级。
        return DatasetContract()
    return DatasetContract(
        minimum_rows=spec.minimum_rows,
        blocking=spec.blocking,
        recommendation_input=spec.recommendation_input,
        hard_fail_on_zero_valid=spec.hard_fail_on_zero_valid,
    )
