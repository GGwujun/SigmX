"""SQLite-backed market-data store (``~/.vibe-trading/market.db``).

Persists A-share daily K-lines, ETF daily, fund-premium close snapshots,
dragon-tiger lists, stock capital flow, and stock pools so historical lookups
hit the local DB instead of re-paying tpdog credits on every request. Acts as
the *primary* read source for OHLCV after the first backfill: callers read DB
first, fall back to the live mootdx/tpdog/akshare chain when DB is cold, and
persist what they fetched.

Style mirrors :mod:`src.goal.store`: WAL + ``busy_timeout`` + a single
serialized connection guarded by an RLock, ``@_synchronized`` on public
methods, ``_write_transaction()`` for cross-statement writes, ``INSERT OR
REPLACE`` upserts, ``PRAGMA user_version`` for migrations.

The store is intentionally independent of tpdog_client — it only knows rows
and dates. Fetching/normalizing lives in :mod:`src.data.market_sync`.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import pandas as pd

from src.data.market_quality import DataReadiness, DatasetQualityReport, QualityStatus

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".vibe-trading" / "market.db"
_DB_PATH_ENV = "VIBE_TRADING_MARKET_DB_PATH"
_BATCH = 500  # rows per executemany transaction

F = TypeVar("F", bound=Callable[..., Any])


def _synchronized(method: F) -> F:
    """Serialize access to the shared SQLite connection (GoalStore pattern)."""

    @wraps(method)
    def wrapper(self: "MarketStore", *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def _default_db_path() -> Path:
    """Default DB path, overridable via ``VIBE_TRADING_MARKET_DB_PATH``."""
    env = os.getenv(_DB_PATH_ENV, "").strip()
    return Path(env) if env else _DEFAULT_DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, total_amt REAL, rise_rate REAL, t_rate REAL,
    name TEXT, source TEXT NOT NULL DEFAULT 'unknown',
    sync_run_id TEXT NOT NULL DEFAULT '',
    quality_status TEXT NOT NULL DEFAULT 'unverified',
    ingested_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_bars_daily_date ON bars_daily(trade_date);

CREATE TABLE IF NOT EXISTS security_master (
    code TEXT PRIMARY KEY,
    symbol TEXT,
    name TEXT,
    area TEXT,
    industry TEXT,
    market TEXT,
    exchange TEXT,
    list_status TEXT,
    list_date TEXT,
    delist_date TEXT,
    is_hs TEXT,
    is_st INTEGER NOT NULL DEFAULT 0,
    is_delisting INTEGER NOT NULL DEFAULT 0,
    is_bj INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_master_status ON security_master(list_status);
CREATE INDEX IF NOT EXISTS idx_security_master_flags ON security_master(is_active, is_st, is_delisting, is_bj);

CREATE TABLE IF NOT EXISTS trade_calendar (
    trade_date TEXT PRIMARY KEY,
    is_trading INTEGER NOT NULL,
    market TEXT NOT NULL DEFAULT 'CN',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_daily_basic (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    close REAL, turnover_rate REAL, turnover_rate_f REAL, volume_ratio REAL,
    pe REAL, pe_ttm REAL, pb REAL, ps REAL, ps_ttm REAL,
    dv_ratio REAL, dv_ttm REAL,
    total_share REAL, float_share REAL, free_share REAL,
    total_mv REAL, circ_mv REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_sdb_date ON stock_daily_basic(trade_date);

CREATE TABLE IF NOT EXISTS etf_master (
    code TEXT PRIMARY KEY,
    csname TEXT, extname TEXT, cname TEXT,
    index_code TEXT, index_name TEXT,
    setup_date TEXT, list_date TEXT, list_status TEXT,
    exchange TEXT, mgr_name TEXT, custod_name TEXT,
    mgt_fee REAL, etf_type TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_etf_master_status ON etf_master(list_status);

CREATE TABLE IF NOT EXISTS fund_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, total_amt REAL, rise REAL, rise_rate REAL,
    nav REAL, iopv REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_fund_daily_date ON fund_daily(trade_date);

CREATE TABLE IF NOT EXISTS etf_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, total_amt REAL, rise REAL, name TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_etf_daily_date ON etf_daily(trade_date);

CREATE TABLE IF NOT EXISTS etf_share_size (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    name TEXT, total_share REAL, total_size REAL,
    nav REAL, close REAL, exchange TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_etf_share_size_date ON etf_share_size(trade_date);

CREATE TABLE IF NOT EXISTS index_master (
    code TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    req_code TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, pre_close REAL,
    change REAL, pct_chg REAL, volume REAL, total_amt REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_index_daily_date ON index_daily(trade_date);

CREATE TABLE IF NOT EXISTS board_master (
    code TEXT PRIMARY KEY,
    name TEXT,
    board_type TEXT,
    req_code TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_master_type ON board_master(board_type);

CREATE TABLE IF NOT EXISTS board_members (
    board_code TEXT NOT NULL,
    board_type TEXT,
    stock_code TEXT NOT NULL,
    stock_name TEXT,
    stock_exchange TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (board_code, stock_code)
);
CREATE INDEX IF NOT EXISTS idx_board_members_stock ON board_members(stock_code);

CREATE TABLE IF NOT EXISTS board_daily (
    board_code TEXT NOT NULL, trade_date TEXT NOT NULL,
    name TEXT, board_type TEXT,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, total_amt REAL, rise REAL, rise_rate REAL, turnover_rate REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (board_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_board_daily_date_type ON board_daily(trade_date, board_type);

CREATE TABLE IF NOT EXISTS realtime_quote_snapshot (
    trade_date TEXT NOT NULL,
    code TEXT NOT NULL,
    snapshot_at TEXT,
    name TEXT,
    price REAL,
    pre_close REAL,
    open REAL,
    high REAL,
    low REAL,
    volume REAL,
    total_amt REAL,
    rise REAL,
    rise_rate REAL,
    turnover_rate REAL,
    source TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_realtime_quote_snapshot_at ON realtime_quote_snapshot(snapshot_at);

CREATE TABLE IF NOT EXISTS fund_premium_snapshot (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    name TEXT, type TEXT, price REAL, nav REAL, premium_rate REAL,
    amount REAL, change_pct REAL, redeem_status TEXT, subscribe_status TEXT,
    signal TEXT, iopv REAL, nav_date TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_fp_date ON fund_premium_snapshot(trade_date);

-- Static fund metadata (code/name/type). Refreshed once/day (post_close) by
-- _sync_fund_master — NOT on the 5-min market timer. LOF names have no other
-- daily home (etf_master is ETF-only); this table unifies ETF+LOF names so the
-- scan route can join a single authoritative name source.
CREATE TABLE IF NOT EXISTS fund_master (
    code TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    updated_at TEXT NOT NULL
);

-- Z-score based arbitrage signals detected from premium anomalies.
CREATE TABLE IF NOT EXISTS arbitrage_signal (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    name TEXT, type TEXT,
    signal_type TEXT NOT NULL,      -- PREMIUM / DISCOUNT
    premium_rate REAL, z_score REAL,
    historical_mean REAL, historical_std REAL, n_history INTEGER,
    cost_estimate REAL, net_spread REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / EXPIRED / EXECUTED
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_signal_status ON arbitrage_signal(status);
CREATE INDEX IF NOT EXISTS idx_signal_type ON arbitrage_signal(signal_type);

CREATE TABLE IF NOT EXISTS dragon_tiger (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    name TEXT, close REAL, rise_rate REAL, net_amt REAL, buy_amt REAL, sell_amt REAL,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_dt_date ON dragon_tiger(trade_date);

CREATE TABLE IF NOT EXISTS stock_capital_flow (
    code TEXT NOT NULL, trade_date TEXT NOT NULL, period INTEGER NOT NULL,
    m_in REAL, m_out REAL, m_net REAL, r_in REAL, r_out REAL, r_net REAL,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date, period)
);
CREATE INDEX IF NOT EXISTS idx_scf_code_date ON stock_capital_flow(code, trade_date);

CREATE TABLE IF NOT EXISTS stock_capital_rank (
    trade_date TEXT NOT NULL, rank_type TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, main_net REAL, change_pct REAL,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, rank_type, code)
);
CREATE INDEX IF NOT EXISTS idx_scr_date_type ON stock_capital_rank(trade_date, rank_type);

CREATE TABLE IF NOT EXISTS sector_capital_flow (
    trade_date TEXT NOT NULL, sector TEXT NOT NULL,
    main_net REAL, change_pct REAL,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, sector)
);
CREATE INDEX IF NOT EXISTS idx_scf_sector_date ON sector_capital_flow(trade_date);

CREATE TABLE IF NOT EXISTS sector_snapshot (
    trade_date TEXT NOT NULL, board_type TEXT NOT NULL, name TEXT NOT NULL,
    change_pct REAL, advancers INTEGER, decliners INTEGER, leader TEXT,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, board_type, name)
);
CREATE INDEX IF NOT EXISTS idx_sector_snapshot_date_type ON sector_snapshot(trade_date, board_type);

CREATE TABLE IF NOT EXISTS market_breadth_snapshot (
    trade_date TEXT PRIMARY KEY,
    total INTEGER, advancers INTEGER, decliners INTEGER, unchanged INTEGER,
    limit_up INTEGER, limit_down INTEGER, max_limit_up_height INTEGER,
    turnover_billion REAL, source TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_breadth_snapshot_date ON market_breadth_snapshot(trade_date);

CREATE TABLE IF NOT EXISTS global_market_index_daily (
    trade_date TEXT NOT NULL, symbol TEXT NOT NULL,
    name TEXT, open REAL, high REAL, low REAL, close REAL,
    prev_close REAL, change_pct REAL, currency TEXT, source TEXT,
    history_json TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_global_market_index_date ON global_market_index_daily(trade_date);

CREATE TABLE IF NOT EXISTS us_theme_snapshot (
    trade_date TEXT NOT NULL, theme_id TEXT NOT NULL,
    theme_name TEXT, proxy_symbol TEXT, proxy_name TEXT,
    close REAL, change_pct REAL, a_share_mapping_json TEXT,
    source TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, theme_id)
);
CREATE INDEX IF NOT EXISTS idx_us_theme_snapshot_date ON us_theme_snapshot(trade_date);

CREATE TABLE IF NOT EXISTS us_a_share_transmission (
    trade_date TEXT NOT NULL, theme_id TEXT NOT NULL,
    us_theme TEXT, a_share_themes_json TEXT,
    signal_strength REAL, direction TEXT, reason TEXT,
    source_data_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, theme_id)
);
CREATE INDEX IF NOT EXISTS idx_us_a_share_transmission_date ON us_a_share_transmission(trade_date);

CREATE TABLE IF NOT EXISTS premarket_news (
    trade_date TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
    summary TEXT, url TEXT, source TEXT, published_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, category, title)
);
CREATE INDEX IF NOT EXISTS idx_premarket_news_date_category ON premarket_news(trade_date, category);

CREATE TABLE IF NOT EXISTS market_stage_snapshot (
    trade_date TEXT NOT NULL, stage TEXT NOT NULL,
    payload_json TEXT NOT NULL, source_tables TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, stage)
);
CREATE INDEX IF NOT EXISTS idx_market_stage_snapshot_stage_date ON market_stage_snapshot(stage, trade_date);

CREATE TABLE IF NOT EXISTS position_analysis_snapshot (
    snapshot_key TEXT PRIMARY KEY,
    symbols_json TEXT NOT NULL,
    payload_json TEXT,
    status TEXT NOT NULL DEFAULT 'missing',
    error TEXT,
    refresh_started_at TEXT,
    refresh_finished_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_analysis_status ON position_analysis_snapshot(status, updated_at);

CREATE TABLE IF NOT EXISTS stock_pool (
    pool_type TEXT NOT NULL, trade_date TEXT NOT NULL, code TEXT NOT NULL,
    extra_json TEXT, updated_at TEXT NOT NULL,
    PRIMARY KEY (pool_type, trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_pool_date ON stock_pool(trade_date);

CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_runs (
    run_id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sync_runs_date ON sync_runs(trade_date, started_at DESC);

CREATE TABLE IF NOT EXISTS sync_dataset_runs (
    run_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL,
    expected_rows INTEGER NOT NULL DEFAULT 0,
    received_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    published_rows INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    missing_codes_json TEXT NOT NULL DEFAULT '[]',
    invalid_rows_json TEXT NOT NULL DEFAULT '[]',
    blocking_reasons_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, dataset),
    FOREIGN KEY (run_id) REFERENCES sync_runs(run_id)
);
CREATE INDEX IF NOT EXISTS idx_sync_dataset_readiness
ON sync_dataset_runs(dataset, trade_date, updated_at DESC);

CREATE TABLE IF NOT EXISTS data_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    dataset TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    code TEXT,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_data_quarantine_run ON data_quarantine(run_id, dataset);

-- ── a-stock-data 扩展表 ─────────────────────────────────────────

-- 研报层: 同花顺一致预期 EPS
CREATE TABLE IF NOT EXISTS eps_forecast (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    year TEXT NOT NULL, count INTEGER, min_eps REAL, mean_eps REAL, max_eps REAL,
    net_profit REAL, source TEXT NOT NULL DEFAULT 'ths',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date, year)
);
CREATE INDEX IF NOT EXISTS idx_eps_forecast_code ON eps_forecast(code, trade_date DESC);

-- 信号层: 同花顺热点题材归因
CREATE TABLE IF NOT EXISTS ths_hot_reason (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, reason TEXT, change_pct REAL, turnover REAL,
    amount REAL, close REAL, market TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_ths_hot_date ON ths_hot_reason(trade_date);

-- 信号层: 个股资金流（日级 120 日）
CREATE TABLE IF NOT EXISTS fund_flow_daily (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    main_net REAL, small_net REAL, mid_net REAL, large_net REAL, super_net REAL,
    net_amount REAL, turnover REAL,
    source TEXT NOT NULL DEFAULT 'sina',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_fund_flow_daily_date ON fund_flow_daily(trade_date);

-- 资金面: 融资融券
CREATE TABLE IF NOT EXISTS margin_trading (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    rzye REAL, rzmre REAL, rzche REAL, rqye REAL,
    rqmcl REAL, rqchl REAL, rzrqye REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_margin_date ON margin_trading(trade_date);

-- 资金面: 大宗交易
CREATE TABLE IF NOT EXISTS block_trade (
    code TEXT NOT NULL, trade_date TEXT NOT NULL,
    price REAL, close REAL, premium_pct REAL, vol REAL, amount REAL,
    buyer TEXT, seller TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_block_trade_date ON block_trade(trade_date);

-- 资金面: 股东户数
CREATE TABLE IF NOT EXISTS holder_num (
    code TEXT NOT NULL, end_date TEXT NOT NULL,
    holder_num INTEGER, change_num INTEGER, change_ratio REAL, avg_shares REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, end_date)
);
CREATE INDEX IF NOT EXISTS idx_holder_num_code ON holder_num(code, end_date DESC);

-- 资金面: 分红送转
CREATE TABLE IF NOT EXISTS dividend_history (
    code TEXT NOT NULL, ex_date TEXT NOT NULL,
    bonus_rmb REAL, transfer_ratio REAL, bonus_ratio REAL, plan TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, ex_date)
);
CREATE INDEX IF NOT EXISTS idx_dividend_code ON dividend_history(code, ex_date DESC);

-- 基础数据: 财务快照（mootdx 37 字段）
CREATE TABLE IF NOT EXISTS financial_snapshot (
    code TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    liutongguben REAL, zongguben REAL, eps REAL, bvps REAL, roe REAL,
    profit REAL, income REAL,
    extra_json TEXT,
    updated_at TEXT NOT NULL
);

-- 基础数据: 财报三表（新浪）
CREATE TABLE IF NOT EXISTS financial_statement (
    code TEXT NOT NULL, report_date TEXT NOT NULL, report_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, report_date, report_type)
);
CREATE INDEX IF NOT EXISTS idx_fin_stmt_code ON financial_statement(code, report_date DESC);

-- 公告: 巨潮公告
CREATE TABLE IF NOT EXISTS announcement (
    code TEXT NOT NULL, ann_date TEXT NOT NULL, title TEXT NOT NULL,
    ann_type TEXT, url TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, ann_date, title)
);
CREATE INDEX IF NOT EXISTS idx_announcement_code ON announcement(code, ann_date DESC);

-- 打板: 涨停池
CREATE TABLE IF NOT EXISTS zt_pool (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, price REAL, pct REAL, amount REAL, float_cap REAL,
    turnover REAL, limit_days INTEGER,
    first_seal TEXT, last_seal TEXT, seal_fund REAL, break_times INTEGER,
    industry TEXT, zt_stat TEXT,
    source TEXT NOT NULL DEFAULT 'eastmoney',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_zt_pool_date ON zt_pool(trade_date);

-- 打板: 同花顺涨停揭秘
CREATE TABLE IF NOT EXISTS ths_limit_up (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, price REAL, pct REAL,
    reason TEXT, board_type TEXT, seal_rate REAL, break_times INTEGER,
    seal_amount REAL, high_days TEXT, first_time TEXT, is_again INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_ths_limit_up_date ON ths_limit_up(trade_date);

-- 打板: 炸板池
CREATE TABLE IF NOT EXISTS zb_pool (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, price REAL, limit_price REAL, pct REAL, turnover REAL,
    first_seal TEXT, break_times INTEGER, amplitude REAL, speed REAL,
    industry TEXT, zt_stat TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_zb_pool_date ON zb_pool(trade_date);

-- 打板: 跌停池
CREATE TABLE IF NOT EXISTS dt_pool (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, price REAL, pct REAL, turnover REAL, pe REAL,
    seal_fund REAL, board_amount REAL, dt_days INTEGER, open_times INTEGER,
    industry TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_dt_pool_date ON dt_pool(trade_date);

-- 打板: 昨日涨停池
CREATE TABLE IF NOT EXISTS yzt_pool (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, price REAL, pct REAL, turnover REAL,
    amplitude REAL, speed REAL, y_first_seal TEXT, y_limit_days INTEGER,
    industry TEXT, zt_stat TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_yzt_pool_date ON yzt_pool(trade_date);

-- 期权: ETF 期权合约
CREATE TABLE IF NOT EXISTS option_chain (
    underlying TEXT NOT NULL, trade_date TEXT NOT NULL,
    month TEXT NOT NULL, code TEXT NOT NULL,
    call_put TEXT NOT NULL,
    bid REAL, ask REAL, last REAL, strike REAL,
    open_interest REAL, volume REAL, amount REAL,
    delta REAL, gamma REAL, theta REAL, vega REAL, iv REAL, theory REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (underlying, trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_option_chain_date ON option_chain(underlying, trade_date);

-- 舆情: 同花顺热榜
CREATE TABLE IF NOT EXISTS hot_list (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    name TEXT, rank INTEGER, hot_value REAL, change_pct REAL, tags TEXT,
    source TEXT NOT NULL DEFAULT 'ths',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code, source)
);
CREATE INDEX IF NOT EXISTS idx_hot_list_date ON hot_list(trade_date);

-- 舆情: 东财人气榜
CREATE TABLE IF NOT EXISTS popularity_rank (
    trade_date TEXT NOT NULL, code TEXT NOT NULL,
    market TEXT, rank INTEGER, rank_change INTEGER, history_rank_change INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, code)
);
CREATE INDEX IF NOT EXISTS idx_popularity_date ON popularity_rank(trade_date);

-- 北向资金（同花顺分钟级）
CREATE TABLE IF NOT EXISTS northbound_flow (
    trade_date TEXT NOT NULL, time TEXT NOT NULL,
    hgt_yi REAL, sgt_yi REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, time)
);
CREATE INDEX IF NOT EXISTS idx_northbound_date ON northbound_flow(trade_date);

-- 互动易问答（巨潮）
CREATE TABLE IF NOT EXISTS irm_qa (
    code TEXT NOT NULL, ask_time TEXT NOT NULL, question TEXT NOT NULL,
    company TEXT, answer TEXT, answerer TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, ask_time, question)
);
CREATE INDEX IF NOT EXISTS idx_irm_qa_code ON irm_qa(code, ask_time DESC);

-- 财联社电报
CREATE TABLE IF NOT EXISTS cls_telegraph (
    trade_date TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT, time TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (trade_date, title)
);
CREATE INDEX IF NOT EXISTS idx_cls_telegraph_date ON cls_telegraph(trade_date);

-- 个股新闻（东财+新浪）
CREATE TABLE IF NOT EXISTS stock_news (
    code TEXT NOT NULL, title TEXT NOT NULL, trade_date TEXT NOT NULL,
    url TEXT, source TEXT, summary TEXT, news_date TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, title, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_stock_news_code ON stock_news(code, trade_date DESC);

-- 限售解禁日历
CREATE TABLE IF NOT EXISTS lockup_expiry (
    code TEXT NOT NULL, free_date TEXT NOT NULL,
    free_shares REAL, able_shares REAL, free_ratio REAL, lift_type TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (code, free_date)
);
CREATE INDEX IF NOT EXISTS idx_lockup_code ON lockup_expiry(code, free_date DESC);

-- 市场环境分类（每日一条）
CREATE TABLE IF NOT EXISTS market_regime (
    trade_date TEXT PRIMARY KEY,
    regime TEXT NOT NULL,
    confidence REAL NOT NULL,
    bull_score REAL,
    bear_score REAL,
    strong_trend INTEGER,
    indicators_json TEXT,
    params_json TEXT,
    created_at TEXT NOT NULL
);
"""

# Tables that carry a per-(date) market-wide snapshot.
_DATE_KEYED_TABLES = {
    "trade_calendar": ("trade_date",),
    "dragon_tiger": ("trade_date",),
    "stock_pool": ("trade_date",),
    "fund_daily": ("trade_date",),
    "fund_premium_snapshot": ("trade_date",),
    "board_daily": ("trade_date",),
    "realtime_quote_snapshot": ("trade_date",),
    "stock_capital_rank": ("trade_date",),
    "sector_capital_flow": ("trade_date",),
    "sector_snapshot": ("trade_date",),
    "market_breadth_snapshot": ("trade_date",),
    "global_market_index_daily": ("trade_date",),
    "us_theme_snapshot": ("trade_date",),
    "us_a_share_transmission": ("trade_date",),
    "premarket_news": ("trade_date",),
    "market_stage_snapshot": ("trade_date",),
    "market_regime": ("trade_date",),
}


class MarketStore:
    """Thread-safe SQLite store for market data tables."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else _default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # busy_timeout 必须在 journal_mode 切换之前设置：切换 journal_mode 需要
        # 排他锁，若此时还没 busy_timeout，多进程并发会立刻 database is locked
        # 而非等待重试（market-sync/data-sync/vibe-trading 三进程共写同一 db）。
        self._conn.execute("PRAGMA busy_timeout=5000")
        # 用 DELETE 模式替代 WAL：避免 Windows bind mount 下 -wal/-shm 文件权限问题。
        # 切换需排他锁，并发下可能拿不到 —— 已是 DELETE 模式时无需切换，失败时
        # 退化为默认 journal 模式，不让构造崩溃（market-sync worker tick 的致命点）。
        try:
            self._conn.execute("PRAGMA journal_mode=DELETE")
        except sqlite3.OperationalError:
            pass
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.RLock()
        self._init_db()

    def _readonly_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=1000")
        return conn

    def _ensure_column(self, table: str, column: str, decl: str) -> None:
        """Add a column to an existing table if absent (additive migration).

        SQLite ``CREATE TABLE IF NOT EXISTS`` won't add columns to an existing
        table, and this project has no version-gated migration path. This helper
        introspects ``PRAGMA table_info`` and runs ``ALTER TABLE ... ADD COLUMN``
        when the column is missing. Idempotent; safe to call every startup.
        """
        cols = {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            if self._conn.execute("PRAGMA user_version").fetchone()[0] < 1:
                self._conn.execute("PRAGMA user_version=1")
            # Additive column migrations for pre-existing tables.
            self._ensure_column("fund_premium_snapshot", "nav_date", "TEXT")
            self._ensure_column("fund_premium_snapshot", "iopv", "REAL")
            self._ensure_column("fund_premium_snapshot", "purchase_status", "TEXT DEFAULT ''")
            self._ensure_column("fund_premium_snapshot", "purchase_limit", "REAL DEFAULT 0")
            self._ensure_column("fund_premium_snapshot", "daily_limit", "REAL DEFAULT 0")
            self._ensure_column("fund_premium_snapshot", "fee_rate", "REAL DEFAULT 0")
            self._ensure_column("bars_daily", "source", "TEXT NOT NULL DEFAULT 'unknown'")
            self._ensure_column("bars_daily", "sync_run_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column("bars_daily", "quality_status", "TEXT NOT NULL DEFAULT 'unverified'")
            self._ensure_column("bars_daily", "ingested_at", "TEXT")
            self._ensure_column("fund_flow_daily", "net_amount", "REAL")
            self._ensure_column("fund_flow_daily", "turnover", "REAL")
            self._ensure_column("lockup_expiry", "able_shares", "REAL")
            self._conn.commit()

    @contextmanager
    def _write_transaction(self):
        """Open an immediate write transaction (GoalStore pattern)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _executemany_chunked(self, sql: str, rows: list[tuple]) -> int:
        """Run executemany in ≤_BATCH-row transactions; return rows written."""
        written = 0
        for i in range(0, len(rows), _BATCH):
            chunk = rows[i : i + _BATCH]
            with self._write_transaction():
                self._conn.executemany(sql, chunk)
                written += len(chunk)
        return written

    @staticmethod
    def _rows_to_ohlcv_df(rows: list[sqlite3.Row]) -> Optional[pd.DataFrame]:
        """Build the canonical OHLCV DataFrame (index=date, 5 fixed cols).

        Mirrors the canonical OHLCV DataFrame shape so
        alpha_signals / position_routes / opportunity_routes see no difference.
        """
        if not rows:
            return None
        df = pd.DataFrame(
            [
                {
                    "date": r["trade_date"],
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"],
                }
                for r in rows
            ]
        )
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    # ------------------------------------------------------------------
    # Daily K-lines (bars_daily)
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_daily_bars(
        self,
        code: str,
        rows: list[dict],
        *,
        source: str,
        sync_run_id: str,
        quality_status: str = "unverified",
    ) -> int:
        """Upsert daily-K rows for one code. Each row needs a ``date`` key."""
        if not rows:
            return 0
        payload = []
        ingested_at = _now_iso()
        for r in rows:
            payload.append(
                (
                    code,
                    r.get("date") or r.get("trade_date"),
                    _f(r.get("open")),
                    _f(r.get("high")),
                    _f(r.get("low")),
                    _f(r.get("close")),
                    _f(r.get("volume")),
                    _f(r.get("total_amt")),
                    _f(r.get("rise_rate")),
                    _f(r.get("t_rate")),
                    r.get("name"),
                    source,
                    sync_run_id,
                    quality_status,
                    ingested_at,
                    ingested_at,
                )
            )
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO bars_daily "
            "(code, trade_date, open, high, low, close, volume, total_amt, "
            "rise_rate, t_rate, name, source, sync_run_id, quality_status, ingested_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_daily_bars(
        self,
        code: str,
        *,
        days: int | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> Optional[pd.DataFrame]:
        """Return OHLCV for a code, optionally clipped by days / [start, end].

        Returns ``None`` when no rows match. Result columns are fixed to
        ``[open, high, low, close, volume]`` with a datetime ``date`` index.
        """
        clauses = ["code = ?"]
        params: list[Any] = [code]
        if start:
            clauses.append("trade_date >= ?")
            params.append(start)
        if end:
            clauses.append("trade_date <= ?")
            params.append(end)
        order = "trade_date ASC" if (start or end) else "trade_date DESC"
        sql = (
            f"SELECT trade_date, open, high, low, close, volume FROM bars_daily "
            f"WHERE {' AND '.join(clauses)} ORDER BY {order}"
        )
        if days is not None and not (start or end):
            sql += f" LIMIT {int(days)}"
        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return None
        df = self._rows_to_ohlcv_df(rows if (start or end or days) else list(reversed(rows)))
        if df is None:
            return None
        if days is not None:
            df = df.tail(days)
        return df

    @_synchronized
    def get_index_daily_bars(self, code: str, days: int | None = None) -> pd.DataFrame | None:
        """Return index OHLCV DataFrame from index_daily table.

        Mirrors ``get_daily_bars`` but queries the ``index_daily`` table where
        index data (e.g. 000001.SH) is stored.
        """
        sql = (
            "SELECT trade_date, open, high, low, close, volume FROM index_daily "
            "WHERE code = ? ORDER BY trade_date DESC"
        )
        if days is not None:
            sql += f" LIMIT {int(days)}"
        rows = self._conn.execute(sql, (code,)).fetchall()
        if not rows:
            return None
        df = self._rows_to_ohlcv_df(list(reversed(rows)))
        if df is None:
            return None
        if days is not None:
            df = df.tail(days)
        return df

    @_synchronized
    def get_recommendation_history_coverage(self, min_bars: int = 60) -> dict[str, float | int]:
        """Measure usable daily-history coverage across the active stock universe."""
        row = self._conn.execute(
            "WITH active AS ("
            " SELECT code FROM security_master WHERE is_active = 1 AND is_st = 0"
            " AND is_delisting = 0 AND is_bj = 0"
            "), covered AS ("
            " SELECT code FROM bars_daily WHERE code IN (SELECT code FROM active)"
            " GROUP BY code HAVING COUNT(*) >= ?"
            ") SELECT (SELECT COUNT(*) FROM active) AS active_codes,"
            " (SELECT COUNT(*) FROM covered) AS covered_codes",
            (int(min_bars),),
        ).fetchone()
        active = int(row["active_codes"] or 0)
        covered = int(row["covered_codes"] or 0)
        return {
            "active_codes": active,
            "covered_codes": covered,
            "coverage": covered / active if active else 0.0,
        }

    @_synchronized
    def last_daily_date(self, code: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT MAX(trade_date) AS d FROM bars_daily WHERE code = ?", (code,)
        ).fetchone()
        return row["d"] if row and row["d"] else None

    @_synchronized
    def codes_with_data(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT code FROM bars_daily ORDER BY code"
        ).fetchall()
        return [r["code"] for r in rows]

    @_synchronized
    def daily_rows_for_run(self, trade_date: str, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT code, trade_date, open, high, low, close, volume, total_amt, "
            "rise_rate, t_rate, name, source, sync_run_id, quality_status, ingested_at "
            "FROM bars_daily WHERE trade_date = ? AND sync_run_id = ? ORDER BY code",
            (trade_date, run_id),
        ).fetchall()
        return [dict(row) for row in rows]

    @_synchronized
    def daily_codes_for_run(self, trade_date: str, run_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT code FROM bars_daily WHERE trade_date = ? AND sync_run_id = ? ORDER BY code",
            (trade_date, run_id),
        ).fetchall()
        return [str(row["code"]) for row in rows]

    @_synchronized
    def quarantine_data(
        self,
        run_id: str,
        dataset: str,
        trade_date: str,
        code: str,
        reason: str,
        payload: dict[str, Any],
    ) -> None:
        with self._write_transaction():
            self._conn.execute(
                "INSERT INTO data_quarantine "
                "(run_id, dataset, trade_date, code, reason, payload_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    dataset,
                    trade_date,
                    code,
                    reason,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    _now_iso(),
                ),
            )

    @_synchronized
    def set_daily_run_quality(self, run_id: str, status: QualityStatus | str) -> None:
        normalized = QualityStatus(status)
        with self._write_transaction():
            self._conn.execute(
                "UPDATE bars_daily SET quality_status = ?, updated_at = ? WHERE sync_run_id = ?",
                (normalized.value, _now_iso(), run_id),
            )

    # ------------------------------------------------------------------
    # Security master / universes
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_security_master(self, rows: list[dict]) -> int:
        """Upsert normalized A-share metadata rows."""
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("ts_code") or "").upper()
            if not code:
                continue
            payload.append(
                (
                    code,
                    r.get("symbol"),
                    r.get("name"),
                    r.get("area"),
                    r.get("industry"),
                    r.get("market"),
                    r.get("exchange"),
                    r.get("list_status"),
                    r.get("list_date"),
                    r.get("delist_date"),
                    r.get("is_hs"),
                    1 if r.get("is_st") else 0,
                    1 if r.get("is_delisting") else 0,
                    1 if r.get("is_bj") else 0,
                    1 if r.get("is_active", True) else 0,
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO security_master "
            "(code, symbol, name, area, industry, market, exchange, list_status, "
            "list_date, delist_date, is_hs, is_st, is_delisting, is_bj, is_active, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def security_master_count(self, *, default_only: bool = False) -> int:
        sql = "SELECT COUNT(*) AS c FROM security_master"
        if default_only:
            sql += " WHERE is_active = 1 AND is_st = 0 AND is_delisting = 0 AND is_bj = 0"
        row = self._conn.execute(sql).fetchone()
        return int(row["c"]) if row else 0

    @_synchronized
    def list_security_master(self, *, default_only: bool = False) -> list[dict]:
        sql = (
            "SELECT code, symbol, name, area, industry, market, exchange, "
            "list_status, list_date, delist_date, is_hs, is_st, is_delisting, is_bj, is_active "
            "FROM security_master"
        )
        if default_only:
            sql += " WHERE is_active = 1 AND is_st = 0 AND is_delisting = 0 AND is_bj = 0"
        sql += " ORDER BY code"
        return [dict(r) for r in self._conn.execute(sql).fetchall()]

    @_synchronized
    def default_strategy_codes(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT code FROM security_master "
            "WHERE is_active = 1 AND is_st = 0 AND is_delisting = 0 AND is_bj = 0 "
            "ORDER BY code"
        ).fetchall()
        return [r["code"] for r in rows]

    # ------------------------------------------------------------------
    # Trading calendar
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_trade_calendar(self, rows: list[dict], *, market: str = "CN") -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            trade_date = r.get("trade_date") or r.get("date")
            if not trade_date:
                continue
            payload.append(
                (
                    trade_date,
                    1 if r.get("is_trading") else 0,
                    r.get("market") or market,
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO trade_calendar "
            "(trade_date, is_trading, market, updated_at) VALUES (?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def is_calendar_trading_day(self, trade_date: str, *, market: str = "CN") -> bool | None:
        row = self._conn.execute(
            "SELECT is_trading FROM trade_calendar WHERE trade_date = ? AND market = ?",
            (trade_date, market),
        ).fetchone()
        if row is None:
            return None
        return bool(row["is_trading"])

    @_synchronized
    def trade_calendar_range(self, *, market: str = "CN") -> tuple[Optional[str], Optional[str]]:
        row = self._conn.execute(
            "SELECT MIN(trade_date) AS lo, MAX(trade_date) AS hi "
            "FROM trade_calendar WHERE market = ?",
            (market,),
        ).fetchone()
        if not row or not row["lo"]:
            return (None, None)
        return (row["lo"], row["hi"])

    # ------------------------------------------------------------------
    # Realtime quote snapshots (intraday)
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_realtime_quotes(
        self, trade_date: str, rows: list[dict], *, snapshot_at: str | None = None
    ) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("symbol") or "").upper()
            if not code:
                continue
            payload.append(
                (
                    r.get("trade_date") or trade_date,
                    code,
                    r.get("snapshot_at") or snapshot_at or _now_iso(),
                    r.get("name"),
                    _f(r.get("price") or r.get("close")),
                    _f(r.get("pre_close") or r.get("yt_close")),
                    _f(r.get("open")),
                    _f(r.get("high")),
                    _f(r.get("low")),
                    _f(r.get("volume")),
                    _f(r.get("total_amt") or r.get("amount")),
                    _f(r.get("rise") or r.get("change")),
                    _f(r.get("rise_rate") or r.get("change_pct") or r.get("pct_chg")),
                    _f(r.get("turnover_rate") or r.get("t_rate")),
                    r.get("source"),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO realtime_quote_snapshot "
            "(trade_date, code, snapshot_at, name, price, pre_close, open, high, low, "
            "volume, total_amt, rise, rise_rate, turnover_rate, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_realtime_quotes(self, trade_date: str, limit: int = 5000) -> list[dict]:
        rows = self._conn.execute(
            "SELECT trade_date, code, snapshot_at, name, price, pre_close, open, high, low, "
            "volume, total_amt, rise, rise_rate, turnover_rate, source, updated_at "
            "FROM realtime_quote_snapshot WHERE trade_date = ? ORDER BY code LIMIT ?",
            (trade_date, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def get_latest_realtime_quote(self, code: str, trade_date: str | None = None) -> dict | None:
        project_code = str(code or "").upper().strip()
        if not project_code:
            return None
        params: list[Any] = [project_code]
        where = "code = ?"
        if trade_date:
            where += " AND trade_date = ?"
            params.append(trade_date)
        row = self._conn.execute(
            "SELECT trade_date, code, snapshot_at, name, price, pre_close, open, high, low, "
            "volume, total_amt, rise, rise_rate, turnover_rate, source, updated_at "
            f"FROM realtime_quote_snapshot WHERE {where} "
            "ORDER BY trade_date DESC, snapshot_at DESC, updated_at DESC LIMIT 1",
            params,
        ).fetchone()
        return dict(row) if row else None

    @_synchronized
    def market_coverage(self) -> dict[str, Any]:
        """Return high-level local-data coverage for operator/status views."""
        scalar_sql = {
            "security_total": "SELECT COUNT(*) FROM security_master",
            "security_active": "SELECT COUNT(*) FROM security_master WHERE is_active = 1",
            "security_default": (
                "SELECT COUNT(*) FROM security_master "
                "WHERE is_active = 1 AND is_st = 0 AND is_delisting = 0 AND is_bj = 0"
            ),
            "security_st_active": (
                "SELECT COUNT(*) FROM security_master WHERE is_active = 1 AND is_st = 1"
            ),
            "security_bj_active": (
                "SELECT COUNT(*) FROM security_master WHERE is_active = 1 AND is_bj = 1"
            ),
            "security_delisting": "SELECT COUNT(*) FROM security_master WHERE is_delisting = 1",
            "daily_rows": "SELECT COUNT(*) FROM bars_daily",
            "daily_codes": "SELECT COUNT(DISTINCT code) FROM bars_daily",
            "daily_default_codes": (
                "SELECT COUNT(DISTINCT b.code) FROM bars_daily b "
                "JOIN security_master s ON s.code = b.code "
                "WHERE s.is_active = 1 AND s.is_st = 0 AND s.is_delisting = 0 AND s.is_bj = 0"
            ),
            "stock_daily_basic_rows": "SELECT COUNT(*) FROM stock_daily_basic",
            "stock_daily_basic_codes": "SELECT COUNT(DISTINCT code) FROM stock_daily_basic",
            "trade_calendar_rows": "SELECT COUNT(*) FROM trade_calendar",
            "realtime_quote_rows": "SELECT COUNT(*) FROM realtime_quote_snapshot",
            "realtime_quote_codes": "SELECT COUNT(DISTINCT code) FROM realtime_quote_snapshot",
            "etf_master_rows": "SELECT COUNT(*) FROM etf_master",
            "fund_master_rows": "SELECT COUNT(*) FROM fund_master",
            "fund_daily_rows": "SELECT COUNT(*) FROM fund_daily",
            "fund_daily_codes": "SELECT COUNT(DISTINCT code) FROM fund_daily",
            "fund_premium_rows": "SELECT COUNT(*) FROM fund_premium_snapshot",
            "fund_premium_codes": "SELECT COUNT(DISTINCT code) FROM fund_premium_snapshot",
            "etf_daily_rows": "SELECT COUNT(*) FROM etf_daily",
            "etf_daily_codes": "SELECT COUNT(DISTINCT code) FROM etf_daily",
            "etf_share_size_rows": "SELECT COUNT(*) FROM etf_share_size",
            "etf_share_size_codes": "SELECT COUNT(DISTINCT code) FROM etf_share_size",
            "index_master_rows": "SELECT COUNT(*) FROM index_master",
            "index_daily_rows": "SELECT COUNT(*) FROM index_daily",
            "index_daily_codes": "SELECT COUNT(DISTINCT code) FROM index_daily",
            "board_master_rows": "SELECT COUNT(*) FROM board_master",
            "board_members_rows": "SELECT COUNT(*) FROM board_members",
            "board_daily_rows": "SELECT COUNT(*) FROM board_daily",
            "board_daily_codes": "SELECT COUNT(DISTINCT board_code) FROM board_daily",
            "dragon_tiger_rows": "SELECT COUNT(*) FROM dragon_tiger",
            "stock_capital_flow_rows": "SELECT COUNT(*) FROM stock_capital_flow",
            "stock_capital_rank_rows": "SELECT COUNT(*) FROM stock_capital_rank",
            "sector_capital_flow_rows": "SELECT COUNT(*) FROM sector_capital_flow",
            "sector_snapshot_rows": "SELECT COUNT(*) FROM sector_snapshot",
            "global_market_index_daily_rows": "SELECT COUNT(*) FROM global_market_index_daily",
            "us_theme_snapshot_rows": "SELECT COUNT(*) FROM us_theme_snapshot",
            "us_a_share_transmission_rows": "SELECT COUNT(*) FROM us_a_share_transmission",
            "premarket_news_rows": "SELECT COUNT(*) FROM premarket_news",
            "market_stage_snapshot_rows": "SELECT COUNT(*) FROM market_stage_snapshot",
            "stock_pool_rows": "SELECT COUNT(*) FROM stock_pool",
        }
        out: dict[str, Any] = {}
        for key, sql in scalar_sql.items():
            row = self._conn.execute(sql).fetchone()
            out[key] = int(row[0]) if row and row[0] is not None else 0
        out["daily_default_missing_codes"] = max(
            0, out["security_default"] - out["daily_default_codes"]
        )
        ranges: dict[str, list[str | None]] = {}
        for table in (
            "trade_calendar",
            "security_master",
            "bars_daily",
            "stock_daily_basic",
            "etf_master",
            "fund_master",
            "fund_daily",
            "etf_daily",
            "etf_share_size",
            "index_master",
            "index_daily",
            "board_master",
            "board_members",
            "board_daily",
            "realtime_quote_snapshot",
            "fund_premium_snapshot",
            "dragon_tiger",
            "stock_capital_flow",
            "stock_capital_rank",
            "sector_capital_flow",
            "sector_snapshot",
            "global_market_index_daily",
            "us_theme_snapshot",
            "us_a_share_transmission",
            "premarket_news",
            "market_stage_snapshot",
            "stock_pool",
        ):
            ranges[table] = list(self.date_range(table))
        out["date_ranges"] = ranges
        return out

    @_synchronized
    def missing_daily_codes(self, *, default_only: bool = True, limit: int = 100) -> list[str]:
        """Return strategy/universe codes that have no local daily bars yet."""
        where = ""
        if default_only:
            where = "WHERE s.is_active = 1 AND s.is_st = 0 AND s.is_delisting = 0 AND s.is_bj = 0"
        rows = self._conn.execute(
            "SELECT s.code FROM security_master s "
            "LEFT JOIN bars_daily b ON b.code = s.code "
            f"{where} "
            "GROUP BY s.code "
            "HAVING COUNT(b.trade_date) = 0 "
            "ORDER BY s.code "
            "LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [r["code"] for r in rows]

    @_synchronized
    def security_names(self, codes: list[str]) -> dict[str, str]:
        """Return name lookup keyed by both project code and bare 6-digit code."""
        normalized: set[str] = set()
        for code in codes:
            raw = str(code or "").upper()
            if not raw:
                continue
            bare = raw.split(".", 1)[0]
            normalized.add(raw)
            if len(bare) == 6 and bare.isdigit():
                normalized.add(bare)
                if bare.startswith(("5", "6", "9")):
                    normalized.add(f"{bare}.SH")
                elif bare.startswith(("4", "8")):
                    normalized.add(f"{bare}.BJ")
                else:
                    normalized.add(f"{bare}.SZ")
        if not normalized:
            return {}
        out: dict[str, str] = {}
        values = sorted(normalized)
        for i in range(0, len(values), _BATCH):
            chunk = values[i : i + _BATCH]
            placeholders = ", ".join("?" for _ in chunk)
            rows = self._conn.execute(
                f"SELECT code, name FROM security_master WHERE code IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                code = str(row["code"] or "").upper()
                name = str(row["name"] or "")
                if not code or not name:
                    continue
                out[code] = name
                out[code.split(".", 1)[0]] = name
        return out

    @_synchronized
    def etf_names(self, codes: list[str]) -> dict[str, str]:
        """Return ETF name lookup keyed by both project code and bare 6-digit code."""
        normalized: set[str] = set()
        for code in codes:
            raw = str(code or "").upper()
            if not raw:
                continue
            bare = raw.split(".", 1)[0]
            normalized.add(raw)
            if len(bare) == 6 and bare.isdigit():
                normalized.add(bare)
                normalized.add(f"{bare}.SH" if bare.startswith("5") else f"{bare}.SZ")
        if not normalized:
            return {}
        out: dict[str, str] = {}
        values = sorted(normalized)
        for i in range(0, len(values), _BATCH):
            chunk = values[i : i + _BATCH]
            placeholders = ", ".join("?" for _ in chunk)
            rows = self._conn.execute(
                f"SELECT code, COALESCE(cname, extname, csname, code) AS name FROM etf_master WHERE code IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                code = str(row["code"] or "").upper()
                name = str(row["name"] or "")
                if not code or not name:
                    continue
                out[code] = name
                out[code.split(".", 1)[0]] = name
        return out

    # ------------------------------------------------------------------
    # ETF daily (etf_daily)
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_stock_daily_basic(self, rows: list[dict]) -> int:
        """Upsert per-stock daily valuation/turnover indicators."""
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("ts_code") or "").upper()
            trade_date = r.get("date") or r.get("trade_date")
            if not code or not trade_date:
                continue
            payload.append(
                (
                    code,
                    trade_date,
                    _f(r.get("close")),
                    _f(r.get("turnover_rate")),
                    _f(r.get("turnover_rate_f")),
                    _f(r.get("volume_ratio")),
                    _f(r.get("pe")),
                    _f(r.get("pe_ttm")),
                    _f(r.get("pb")),
                    _f(r.get("ps")),
                    _f(r.get("ps_ttm")),
                    _f(r.get("dv_ratio")),
                    _f(r.get("dv_ttm")),
                    _f(r.get("total_share")),
                    _f(r.get("float_share")),
                    _f(r.get("free_share")),
                    _f(r.get("total_mv")),
                    _f(r.get("circ_mv")),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO stock_daily_basic "
            "(code, trade_date, close, turnover_rate, turnover_rate_f, volume_ratio, "
            "pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm, total_share, float_share, "
            "free_share, total_mv, circ_mv, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def upsert_etf_master(self, rows: list[dict]) -> int:
        """Upsert ETF metadata from Tushare etf_basic."""
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("ts_code") or "").upper()
            if not code:
                continue
            payload.append(
                (
                    code,
                    r.get("csname"),
                    r.get("extname"),
                    r.get("cname"),
                    r.get("index_code"),
                    r.get("index_name"),
                    r.get("setup_date"),
                    r.get("list_date"),
                    r.get("list_status"),
                    r.get("exchange"),
                    r.get("mgr_name"),
                    r.get("custod_name"),
                    _f(r.get("mgt_fee")),
                    r.get("etf_type"),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO etf_master "
            "(code, csname, extname, cname, index_code, index_name, setup_date, "
            "list_date, list_status, exchange, mgr_name, custod_name, mgt_fee, etf_type, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def upsert_fund_daily(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            trade_date = r.get("date") or r.get("trade_date")
            if not trade_date:
                continue
            payload.append(
                (
                    code,
                    trade_date,
                    _f(r.get("open")),
                    _f(r.get("high")),
                    _f(r.get("low")),
                    _f(r.get("close") or r.get("price")),
                    _f(r.get("volume")),
                    _f(r.get("total_amt") or r.get("amount")),
                    _f(r.get("rise") or r.get("change")),
                    _f(r.get("rise_rate") or r.get("change_pct") or r.get("pct_chg")),
                    _f(r.get("nav")),
                    _f(r.get("iopv")),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO fund_daily "
            "(code, trade_date, open, high, low, close, volume, total_amt, rise, rise_rate, nav, iopv, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_fund_daily(self, code: str, *, start: str | None = None, end: str | None = None) -> list[dict]:
        clauses = ["code = ?"]
        params: list[Any] = [code]
        if start:
            clauses.append("trade_date >= ?")
            params.append(start)
        if end:
            clauses.append("trade_date <= ?")
            params.append(end)
        rows = self._conn.execute(
            "SELECT code, trade_date, open, high, low, close, volume, total_amt, rise, rise_rate, nav, iopv "
            f"FROM fund_daily WHERE {' AND '.join(clauses)} ORDER BY trade_date",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def upsert_etf_daily(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = [
            (
                code,
                r.get("date") or r.get("trade_date"),
                _f(r.get("open")),
                _f(r.get("high")),
                _f(r.get("low")),
                _f(r.get("close")),
                _f(r.get("volume")),
                _f(r.get("total_amt")),
                _f(r.get("rise")),
                r.get("name"),
                _now_iso(),
            )
            for r in rows
        ]
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO etf_daily "
            "(code, trade_date, open, high, low, close, volume, total_amt, rise, name, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_etf_daily(
        self, code: str, *, start: str | None = None, end: str | None = None
    ) -> Optional[pd.DataFrame]:
        clauses = ["code = ?"]
        params: list[Any] = [code]
        if start:
            clauses.append("trade_date >= ?")
            params.append(start)
        if end:
            clauses.append("trade_date <= ?")
            params.append(end)
        rows = self._conn.execute(
            f"SELECT trade_date AS date, open, high, low, close, volume, total_amt, rise "
            f"FROM etf_daily WHERE {' AND '.join(clauses)} ORDER BY trade_date",
            params,
        ).fetchall()
        if not rows:
            return None
        df = pd.DataFrame([dict(r) for r in rows])
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    @_synchronized
    def has_etf_daily(self, code: str, trade_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM etf_daily WHERE code = ? AND trade_date = ? LIMIT 1",
            (code, trade_date),
        ).fetchone()
        return row is not None

    @_synchronized
    def has_index_daily(self, code: str, trade_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM index_daily WHERE code = ? AND trade_date = ? LIMIT 1",
            (code, trade_date),
        ).fetchone()
        return row is not None

    @_synchronized
    def count_index_daily(self, code: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM index_daily WHERE code = ?", (code,)
        ).fetchone()[0]

    # ------------------------------------------------------------------
    # Data-integrity query helpers
    # ------------------------------------------------------------------

    def count_codes_with_date(self, trade_date: str) -> int:
        """Count distinct codes with bars_daily data on *trade_date*."""
        return self._conn.execute(
            "SELECT COUNT(DISTINCT code) FROM bars_daily WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()[0]

    def count_active_codes(self) -> int:
        """Count active codes in security_master."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM security_master WHERE is_active = 1"
        ).fetchone()[0]

    def count_codes_with_min_bars(self, min_bars: int) -> int:
        """Count codes that have at least *min_bars* rows in bars_daily."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM (SELECT code FROM bars_daily GROUP BY code HAVING COUNT(*) >= ?)",
            (min_bars,),
        ).fetchone()[0]

    def count_stale_pending_runs(self, minutes: int = 30) -> int:
        """Count sync_runs still 'pending' for more than *minutes*."""
        return self._conn.execute(
            """SELECT COUNT(*) FROM sync_runs
               WHERE status = 'pending'
                 AND started_at < datetime('now', ? || ' minutes')""",
            (f"-{minutes}",),
        ).fetchone()[0]

    def fail_stale_pending_runs(self, minutes: int = 30) -> int:
        """Mark long-pending sync_runs as 'failed'."""
        return self._conn.execute(
            """UPDATE sync_runs
               SET status = 'failed',
                   error_summary = 'stale pending (auto-failed by integrity check)',
                   finished_at = datetime('now')
               WHERE status = 'pending'
                 AND started_at < datetime('now', ? || ' minutes')""",
            (f"-{minutes}",),
        ).rowcount

    # ------------------------------------------------------------------
    # Index and board master / board daily
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_index_master(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("req_code") or "").upper()
            if not code:
                continue
            payload.append(
                (
                    code,
                    r.get("name"),
                    r.get("type"),
                    r.get("req_code"),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO index_master (code, name, type, req_code, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def list_index_master(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT code, name, type, req_code, updated_at FROM index_master ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def upsert_board_master(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("req_code") or "").strip()
            if not code:
                continue
            board_type = r.get("board_type") or r.get("type")
            req_code = r.get("req_code") or (
                f"{board_type}.{code}" if board_type and "." not in code else code
            )
            payload.append((code, r.get("name"), board_type, req_code, _now_iso()))
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO board_master (code, name, board_type, req_code, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def list_board_master(self, board_type: str | None = None) -> list[dict]:
        sql = "SELECT code, name, board_type, req_code, updated_at FROM board_master"
        params: list[Any] = []
        if board_type:
            sql += " WHERE board_type = ?"
            params.append(board_type)
        sql += " ORDER BY board_type, code"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    @_synchronized
    def upsert_board_members(self, board_code: str, board_type: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            stock_code = str(r.get("code") or r.get("stock_code") or r.get("req_code") or "").upper()
            if not stock_code:
                continue
            payload.append(
                (
                    board_code,
                    board_type,
                    stock_code,
                    r.get("name") or r.get("stock_name"),
                    r.get("type") or r.get("stock_exchange"),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM board_members WHERE board_code = ?", (board_code,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO board_members "
                    "(board_code, board_type, stock_code, stock_name, stock_exchange, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_board_members(self, board_code: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT board_code, board_type, stock_code, stock_name, stock_exchange "
            "FROM board_members WHERE board_code = ? ORDER BY stock_code",
            (board_code,),
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def upsert_board_daily(self, board_code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            trade_date = r.get("date") or r.get("trade_date")
            if not trade_date:
                continue
            payload.append(
                (
                    board_code,
                    trade_date,
                    r.get("name"),
                    r.get("board_type") or r.get("type"),
                    _f(r.get("open")),
                    _f(r.get("high")),
                    _f(r.get("low")),
                    _f(r.get("close") or r.get("price")),
                    _f(r.get("volume")),
                    _f(r.get("total_amt") or r.get("amount")),
                    _f(r.get("rise") or r.get("change")),
                    _f(r.get("rise_rate") or r.get("change_pct") or r.get("pct_chg")),
                    _f(r.get("turnover_rate") or r.get("t_rate")),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO board_daily "
            "(board_code, trade_date, name, board_type, open, high, low, close, volume, "
            "total_amt, rise, rise_rate, turnover_rate, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def upsert_etf_share_size(self, rows: list[dict]) -> int:
        """Upsert ETF share/size snapshots."""
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("ts_code") or "").upper()
            trade_date = r.get("date") or r.get("trade_date")
            if not code or not trade_date:
                continue
            payload.append(
                (
                    code,
                    trade_date,
                    r.get("name"),
                    _f(r.get("total_share")),
                    _f(r.get("total_size")),
                    _f(r.get("nav")),
                    _f(r.get("close")),
                    r.get("exchange"),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO etf_share_size "
            "(code, trade_date, name, total_share, total_size, nav, close, exchange, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def upsert_index_daily(self, code: str, rows: list[dict]) -> int:
        """Upsert index OHLCV rows for one index code."""
        if not rows:
            return 0
        payload = []
        for r in rows:
            row_code = str(r.get("code") or r.get("ts_code") or code).upper()
            trade_date = r.get("date") or r.get("trade_date")
            if not row_code or not trade_date:
                continue
            payload.append(
                (
                    row_code,
                    trade_date,
                    _f(r.get("open")),
                    _f(r.get("high")),
                    _f(r.get("low")),
                    _f(r.get("close")),
                    _f(r.get("pre_close")),
                    _f(r.get("change")),
                    _f(r.get("pct_chg")),
                    _f(r.get("volume")),
                    _f(r.get("total_amt")),
                    _now_iso(),
                )
            )
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO index_daily "
            "(code, trade_date, open, high, low, close, pre_close, change, pct_chg, "
            "volume, total_amt, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    # ------------------------------------------------------------------
    # Dragon-tiger list
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_dragon_tiger(self, trade_date: str, rows: list[dict]) -> int:
        return _upsert_market_wide(
            self,
            "dragon_tiger",
            trade_date,
            rows,
            pk_cols=("code", "trade_date"),
            value_cols=("name", "close", "rise_rate", "net_amt", "buy_amt", "sell_amt"),
        )

    @_synchronized
    def get_dragon_tiger(self, trade_date: str) -> list[dict]:
        return _get_market_wide(self, "dragon_tiger", trade_date)

    @_synchronized
    def has_dragon_tiger(self, trade_date: str) -> bool:
        return _has_market_wide(self, "dragon_tiger", trade_date)

    # ------------------------------------------------------------------
    # Stock capital flow
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_stock_capital(
        self, code: str, trade_date: str, period: int, rows: list[dict]
    ) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            extra = {k: v for k, v in r.items()
                     if k not in {"code", "date", "trade_date", "period",
                                  "m_in", "m_out", "m_net", "r_in", "r_out", "r_net", "name"}}
            payload.append(
                (
                    code,
                    r.get("date") or trade_date,
                    int(period),
                    _f(r.get("m_in")),
                    _f(r.get("m_out")),
                    _f(r.get("m_net")),
                    _f(r.get("r_in")),
                    _f(r.get("r_out")),
                    _f(r.get("r_net")),
                    json.dumps(extra, ensure_ascii=False) if extra else None,
                    _now_iso(),
                )
            )
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO stock_capital_flow "
            "(code, trade_date, period, m_in, m_out, m_net, r_in, r_out, r_net, extra_json, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_stock_capital(
        self, code: str, *, start: str, end: str, period: int = 1
    ) -> list[dict]:
        rows = self._conn.execute(
            "SELECT trade_date, m_in, m_out, m_net, r_in, r_out, r_net, extra_json "
            "FROM stock_capital_flow WHERE code = ? AND period = ? "
            "AND trade_date >= ? AND trade_date <= ? ORDER BY trade_date",
            (code, int(period), start, end),
        ).fetchall()
        return _rows_with_extra(rows)

    @_synchronized
    def upsert_stock_capital_rank(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            code = str(r.get("code") or r.get("symbol") or "").upper()
            rank_type = str(r.get("rank_type") or "").strip()
            if not code or not rank_type:
                continue
            extra = {
                k: v for k, v in r.items()
                if k not in {"code", "symbol", "trade_date", "date", "rank_type", "name", "main_net", "change_pct"}
            }
            payload.append((
                trade_date,
                rank_type,
                code,
                r.get("name"),
                _f(r.get("main_net")),
                _f(r.get("change_pct")),
                json.dumps(extra, ensure_ascii=False) if extra else None,
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            rank_types = sorted({row[1] for row in payload})
            for rank_type in rank_types:
                self._conn.execute(
                    "DELETE FROM stock_capital_rank WHERE trade_date = ? AND rank_type = ?",
                    (trade_date, rank_type),
                )
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO stock_capital_rank "
                    "(trade_date, rank_type, code, name, main_net, change_pct, extra_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_stock_capital_rank(self, trade_date: str, rank_type: str, limit: int = 20) -> list[dict]:
        order = "ASC" if rank_type == "outflow" else "DESC"
        rows = self._conn.execute(
            "SELECT code, name, main_net, change_pct, extra_json "
            "FROM stock_capital_rank WHERE trade_date = ? AND rank_type = ? "
            f"ORDER BY main_net {order} LIMIT ?",
            (trade_date, rank_type, int(limit)),
        ).fetchall()
        out = _rows_with_extra(rows)
        for row in out:
            row["symbol"] = row.pop("code", "")
        return out

    @_synchronized
    def upsert_sector_capital(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            sector = str(r.get("sector") or r.get("name") or "").strip()
            if not sector:
                continue
            extra = {
                k: v for k, v in r.items()
                if k not in {"sector", "name", "trade_date", "date", "main_net", "change_pct"}
            }
            payload.append((
                trade_date,
                sector,
                _f(r.get("main_net")),
                _f(r.get("change_pct")),
                json.dumps(extra, ensure_ascii=False) if extra else None,
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM sector_capital_flow WHERE trade_date = ?", (trade_date,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO sector_capital_flow "
                    "(trade_date, sector, main_net, change_pct, extra_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_sector_capital(self, trade_date: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT sector, main_net, change_pct, extra_json "
            "FROM sector_capital_flow WHERE trade_date = ? "
            "ORDER BY main_net DESC LIMIT ?",
            (trade_date, int(limit)),
        ).fetchall()
        return _rows_with_extra(rows)

    @_synchronized
    def upsert_sector_snapshot(self, trade_date: str, board_type: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            name = str(r.get("name") or r.get("sector") or "").strip()
            if not name:
                continue
            extra = {
                k: v for k, v in r.items()
                if k not in {"trade_date", "date", "board_type", "name", "sector", "change_pct", "advancers", "decliners", "leader"}
            }
            chg = _f(r.get("change_pct"))
            payload.append((
                trade_date,
                board_type,
                name,
                round(chg, 2) if chg is not None else None,
                int(_f(r.get("advancers")) or 0),
                int(_f(r.get("decliners")) or 0),
                r.get("leader"),
                json.dumps(extra, ensure_ascii=False) if extra else None,
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute(
                "DELETE FROM sector_snapshot WHERE trade_date = ? AND board_type = ?",
                (trade_date, board_type),
            )
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO sector_snapshot "
                    "(trade_date, board_type, name, change_pct, advancers, decliners, leader, extra_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_sector_snapshot(
        self, trade_date: str, board_type: str, limit: int = 40, *, order_by: str = "change_pct_desc"
    ) -> list[dict]:
        # order_by: change_pct_desc(默认,涨幅TOP) | abs(按|涨跌幅|,大涨大跌都靠前,适合热力图) | name
        order = {
            "change_pct_desc": "change_pct DESC",
            "abs": "ABS(change_pct) DESC",
            "name": "name",
        }.get(order_by, "change_pct DESC")
        rows = self._conn.execute(
            f"SELECT name, change_pct, advancers, decliners, leader, extra_json "
            f"FROM sector_snapshot WHERE trade_date = ? AND board_type = ? "
            f"ORDER BY {order} LIMIT ?",
            (trade_date, board_type, int(limit)),
        ).fetchall()
        return _rows_with_extra(rows)

    @_synchronized
    def upsert_market_breadth_snapshot(self, trade_date: str, row: dict) -> int:
        if not row:
            return 0
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO market_breadth_snapshot "
                "(trade_date, total, advancers, decliners, unchanged, limit_up, limit_down, "
                "max_limit_up_height, turnover_billion, source, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trade_date,
                    int(_f(row.get("total")) or 0),
                    int(_f(row.get("advancers")) or 0),
                    int(_f(row.get("decliners")) or 0),
                    int(_f(row.get("unchanged")) or 0),
                    int(_f(row.get("limit_up")) or 0),
                    int(_f(row.get("limit_down")) or 0),
                    int(_f(row.get("max_limit_up_height")) or 0),
                    _f(row.get("turnover_billion")),
                    row.get("source"),
                    _now_iso(),
                ),
            )
        return 1

    @_synchronized
    def get_market_breadth_snapshot(self, trade_date: str) -> dict | None:
        row = self._conn.execute(
            "SELECT trade_date, total, advancers, decliners, unchanged, limit_up, limit_down, "
            "max_limit_up_height, turnover_billion, source, updated_at "
            "FROM market_breadth_snapshot WHERE trade_date = ?",
            (trade_date,),
        ).fetchone()
        return dict(row) if row else None

    @_synchronized
    def delete_market_breadth_snapshot(self, trade_date: str) -> int:
        with self._write_transaction():
            cur = self._conn.execute("DELETE FROM market_breadth_snapshot WHERE trade_date = ?", (trade_date,))
        return int(cur.rowcount or 0)

    @_synchronized
    def upsert_global_market_indices(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            symbol = str(r.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            payload.append((
                r.get("trade_date") or trade_date,
                symbol,
                r.get("name"),
                _f(r.get("open")),
                _f(r.get("high")),
                _f(r.get("low")),
                _f(r.get("close")),
                _f(r.get("prev_close")),
                _f(r.get("change_pct")),
                r.get("currency") or "USD",
                r.get("source"),
                json.dumps(r.get("history") or [], ensure_ascii=False),
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM global_market_index_daily WHERE trade_date = ?", (trade_date,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO global_market_index_daily "
                    "(trade_date, symbol, name, open, high, low, close, prev_close, change_pct, currency, source, history_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_global_market_indices(self, trade_date: str | None = None, limit: int = 40) -> list[dict]:
        if trade_date:
            rows = self._conn.execute(
                "SELECT trade_date, symbol, name, open, high, low, close, prev_close, change_pct, currency, source, history_json "
                "FROM global_market_index_daily WHERE trade_date = ? ORDER BY symbol LIMIT ?",
                (trade_date, int(limit)),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT trade_date, symbol, name, open, high, low, close, prev_close, change_pct, currency, source, history_json "
                "FROM global_market_index_daily "
                "WHERE trade_date = (SELECT MAX(trade_date) FROM global_market_index_daily) "
                "ORDER BY symbol LIMIT ?",
                (int(limit),),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["history"] = json.loads(item.pop("history_json") or "[]")
            except (TypeError, ValueError):
                item["history"] = []
            out.append(item)
        return out

    @_synchronized
    def upsert_us_theme_snapshot(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            theme_id = str(r.get("theme_id") or "").strip()
            if not theme_id:
                continue
            mapping = r.get("a_share_mapping") or r.get("a_share_mapping_json") or []
            payload.append((
                trade_date,
                theme_id,
                r.get("theme_name"),
                str(r.get("proxy_symbol") or "").upper(),
                r.get("proxy_name"),
                _f(r.get("close")),
                _f(r.get("change_pct")),
                json.dumps(mapping, ensure_ascii=False),
                r.get("source"),
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM us_theme_snapshot WHERE trade_date = ?", (trade_date,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO us_theme_snapshot "
                    "(trade_date, theme_id, theme_name, proxy_symbol, proxy_name, close, change_pct, "
                    "a_share_mapping_json, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_us_theme_snapshot(self, trade_date: str, limit: int = 40) -> list[dict]:
        rows = self._conn.execute(
            "SELECT trade_date, theme_id, theme_name, proxy_symbol, proxy_name, close, change_pct, "
            "a_share_mapping_json, source FROM us_theme_snapshot WHERE trade_date = ? "
            "ORDER BY change_pct DESC LIMIT ?",
            (trade_date, int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["a_share_mapping"] = json.loads(item.pop("a_share_mapping_json") or "[]")
            except (TypeError, ValueError):
                item["a_share_mapping"] = []
            out.append(item)
        return out

    @_synchronized
    def upsert_us_a_share_transmission(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            theme_id = str(r.get("theme_id") or "").strip()
            if not theme_id:
                continue
            payload.append((
                trade_date,
                theme_id,
                r.get("us_theme"),
                json.dumps(r.get("a_share_themes") or [], ensure_ascii=False),
                _f(r.get("signal_strength")),
                r.get("direction"),
                r.get("reason"),
                json.dumps(r.get("source_data") or {}, ensure_ascii=False),
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM us_a_share_transmission WHERE trade_date = ?", (trade_date,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO us_a_share_transmission "
                    "(trade_date, theme_id, us_theme, a_share_themes_json, signal_strength, direction, reason, "
                    "source_data_json, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_us_a_share_transmission(self, trade_date: str, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT trade_date, theme_id, us_theme, a_share_themes_json, signal_strength, direction, reason, "
            "source_data_json FROM us_a_share_transmission WHERE trade_date = ? "
            "ORDER BY ABS(signal_strength) DESC LIMIT ?",
            (trade_date, int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["a_share_themes"] = json.loads(item.pop("a_share_themes_json") or "[]")
            except (TypeError, ValueError):
                item["a_share_themes"] = []
            try:
                item["source_data"] = json.loads(item.pop("source_data_json") or "{}")
            except (TypeError, ValueError):
                item["source_data"] = {}
            out.append(item)
        return out

    @_synchronized
    def upsert_premarket_news(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = []
        for r in rows:
            category = str(r.get("category") or "").strip()
            title = str(r.get("title") or "").strip()
            if not category or not title:
                continue
            payload.append((
                trade_date,
                category,
                title,
                r.get("summary") or r.get("snippet") or r.get("description"),
                r.get("url") or r.get("link"),
                r.get("source"),
                r.get("published_at") or r.get("published") or r.get("pub_date"),
                _now_iso(),
            ))
        if not payload:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM premarket_news WHERE trade_date = ?", (trade_date,))
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO premarket_news "
                    "(trade_date, category, title, summary, url, source, published_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_premarket_news(self, trade_date: str, limit: int = 40) -> list[dict]:
        rows = self._conn.execute(
            "SELECT trade_date, category, title, summary, url, source, published_at "
            "FROM premarket_news WHERE trade_date = ? ORDER BY category, published_at DESC LIMIT ?",
            (trade_date, int(limit)),
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def latest_date(self, table: str) -> Optional[str]:
        lo, hi = self.date_range(table)
        return hi

    @_synchronized
    def upsert_market_stage_snapshot(
        self,
        trade_date: str,
        stage: str,
        payload: dict[str, Any],
        *,
        source_tables: list[str] | None = None,
    ) -> int:
        if not trade_date or not stage:
            return 0
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO market_stage_snapshot "
                "(trade_date, stage, payload_json, source_tables, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    trade_date,
                    stage,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(source_tables or [], ensure_ascii=False),
                    _now_iso(),
                ),
            )
        return 1

    @_synchronized
    def get_market_stage_snapshot(self, stage: str, trade_date: str | None = None) -> dict | None:
        if trade_date:
            row = self._conn.execute(
                "SELECT trade_date, stage, payload_json, source_tables, updated_at "
                "FROM market_stage_snapshot WHERE stage = ? AND trade_date = ?",
                (stage, trade_date),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT trade_date, stage, payload_json, source_tables, updated_at "
                "FROM market_stage_snapshot WHERE stage = ? ORDER BY trade_date DESC LIMIT 1",
                (stage,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            payload = {}
        try:
            source_tables = json.loads(row["source_tables"] or "[]")
        except (TypeError, ValueError):
            source_tables = []
        return {
            "trade_date": row["trade_date"],
            "stage": row["stage"],
            "payload": payload,
            "source_tables": source_tables,
            "updated_at": row["updated_at"],
        }

    def get_market_stage_snapshot_fast(self, stage: str, trade_date: str | None = None) -> dict | None:
        """Read a stage snapshot through a short-lived read-only connection.

        Stage pages are latency-sensitive and should not wait behind the shared
        sync connection's Python lock while background jobs fetch/write data.
        WAL lets this read the last committed snapshot concurrently.
        """
        try:
            with self._readonly_conn() as conn:
                if trade_date:
                    row = conn.execute(
                        "SELECT trade_date, stage, payload_json, source_tables, updated_at "
                        "FROM market_stage_snapshot WHERE stage = ? AND trade_date = ?",
                        (stage, trade_date),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT trade_date, stage, payload_json, source_tables, updated_at "
                        "FROM market_stage_snapshot WHERE stage = ? ORDER BY trade_date DESC LIMIT 1",
                        (stage,),
                    ).fetchone()
        except sqlite3.Error as exc:
            logger.debug("fast stage snapshot read failed, falling back: %s", exc)
            return self.get_market_stage_snapshot(stage, trade_date)
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            payload = {}
        try:
            source_tables = json.loads(row["source_tables"] or "[]")
        except (TypeError, ValueError):
            source_tables = []
        return {
            "trade_date": row["trade_date"],
            "stage": row["stage"],
            "payload": payload,
            "source_tables": source_tables,
            "updated_at": row["updated_at"],
        }

    # ------------------------------------------------------------------
    # Position analysis snapshots (tracking dashboard)
    # ------------------------------------------------------------------

    @staticmethod
    def position_analysis_key(symbols: list[str]) -> str:
        return ",".join(sorted({str(symbol or "").strip().upper() for symbol in symbols if symbol}))

    def _position_analysis_row_to_snapshot(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        try:
            symbols = json.loads(row["symbols_json"] or "[]")
        except (TypeError, ValueError):
            symbols = []
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        return {
            "key": row["snapshot_key"],
            "symbols": symbols if isinstance(symbols, list) else [],
            "payload": payload if isinstance(payload, dict) else {},
            "status": row["status"],
            "error": row["error"],
            "refresh_started_at": row["refresh_started_at"],
            "refresh_finished_at": row["refresh_finished_at"],
            "updated_at": row["updated_at"],
        }

    @_synchronized
    def get_position_analysis_snapshot(self, symbols: list[str]) -> dict[str, Any] | None:
        key = self.position_analysis_key(symbols)
        row = self._conn.execute(
            "SELECT snapshot_key, symbols_json, payload_json, status, error, "
            "refresh_started_at, refresh_finished_at, updated_at "
            "FROM position_analysis_snapshot WHERE snapshot_key = ?",
            (key,),
        ).fetchone()
        return self._position_analysis_row_to_snapshot(row)

    @_synchronized
    def mark_position_analysis_refreshing(self, symbols: list[str]) -> bool:
        key = self.position_analysis_key(symbols)
        normalized = sorted({str(symbol or "").strip().upper() for symbol in symbols if symbol})
        now = _now_iso()
        with self._write_transaction():
            row = self._conn.execute(
                "SELECT status FROM position_analysis_snapshot WHERE snapshot_key = ?",
                (key,),
            ).fetchone()
            if row and row["status"] == "refreshing":
                return False
            if row:
                self._conn.execute(
                    "UPDATE position_analysis_snapshot "
                    "SET symbols_json = ?, status = 'refreshing', error = NULL, "
                    "refresh_started_at = ?, updated_at = ? WHERE snapshot_key = ?",
                    (json.dumps(normalized, ensure_ascii=False), now, now, key),
                )
            else:
                self._conn.execute(
                    "INSERT INTO position_analysis_snapshot "
                    "(snapshot_key, symbols_json, payload_json, status, error, "
                    "refresh_started_at, refresh_finished_at, updated_at) "
                    "VALUES (?, ?, NULL, 'refreshing', NULL, ?, NULL, ?)",
                    (key, json.dumps(normalized, ensure_ascii=False), now, now),
                )
        return True

    @_synchronized
    def upsert_position_analysis_snapshot(
        self,
        symbols: list[str],
        payload: dict[str, Any],
        *,
        status: str = "ready",
        error: str | None = None,
    ) -> dict[str, Any]:
        key = self.position_analysis_key(symbols)
        normalized = sorted({str(symbol or "").strip().upper() for symbol in symbols if symbol})
        now = _now_iso()
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO position_analysis_snapshot "
                "(snapshot_key, symbols_json, payload_json, status, error, "
                "refresh_started_at, refresh_finished_at, updated_at) "
                "VALUES ("
                "?, ?, ?, ?, ?, "
                "COALESCE((SELECT refresh_started_at FROM position_analysis_snapshot WHERE snapshot_key = ?), ?), "
                "?, ?"
                ")",
                (
                    key,
                    json.dumps(normalized, ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False),
                    status,
                    error,
                    key,
                    now,
                    now,
                    now,
                ),
            )
        snapshot = self.get_position_analysis_snapshot(symbols)
        return snapshot or {
            "key": key,
            "symbols": normalized,
            "payload": payload,
            "status": status,
            "error": error,
            "refresh_started_at": now,
            "refresh_finished_at": now,
            "updated_at": now,
        }

    @_synchronized
    def mark_position_analysis_error(self, symbols: list[str], error: str) -> dict[str, Any] | None:
        key = self.position_analysis_key(symbols)
        now = _now_iso()
        with self._write_transaction():
            self._conn.execute(
                "UPDATE position_analysis_snapshot "
                "SET status = 'error', error = ?, refresh_finished_at = ?, updated_at = ? "
                "WHERE snapshot_key = ?",
                (error, now, now, key),
            )
        return self.get_position_analysis_snapshot(symbols)

    # ------------------------------------------------------------------
    # Stock pool (limit-up / limit-down / strong / fire / new)
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_pool(self, pool_type: str, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        # Delete existing codes for this (pool_type, date) then insert — a pool
        # membership changes intraday until close, so a full replace per date is
        # the correct semantics (not individual-row upsert).
        payload = []
        for r in rows:
            extra = {k: v for k, v in r.items() if k not in {"code", "date", "trade_date"}}
            payload.append(
                (pool_type, r.get("date") or trade_date, r.get("code"),
                 json.dumps(extra, ensure_ascii=False) if extra else None, _now_iso())
            )
        with self._write_transaction():
            self._conn.execute(
                "DELETE FROM stock_pool WHERE pool_type = ? AND trade_date = ?",
                (pool_type, trade_date),
            )
            for i in range(0, len(payload), _BATCH):
                self._conn.executemany(
                    "INSERT OR REPLACE INTO stock_pool "
                    "(pool_type, trade_date, code, extra_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    payload[i : i + _BATCH],
                )
        return len(payload)

    @_synchronized
    def get_pool(self, pool_type: str, trade_date: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT code, extra_json FROM stock_pool "
            "WHERE pool_type = ? AND trade_date = ?",
            (pool_type, trade_date),
        ).fetchall()
        return _rows_with_extra(rows, extra_key="extra_json", base_cols=("code",))

    @_synchronized
    def has_pool(self, pool_type: str, trade_date: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM stock_pool WHERE pool_type = ? AND trade_date = ? LIMIT 1",
            (pool_type, trade_date),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Fund premium close snapshot
    # ------------------------------------------------------------------

    @_synchronized
    def upsert_fund_premium(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        payload = [
            (
                r.get("code"),
                r.get("trade_date") or trade_date,
                r.get("name"),
                r.get("type"),
                _f(r.get("price")),
                _f(r.get("nav")),
                _f(r.get("premium_rate")),
                _f(r.get("amount")),
                _f(r.get("change_pct")),
                r.get("redeem_status"),
                r.get("subscribe_status"),
                r.get("signal"),
                _f(r.get("iopv")) or None,
                r.get("nav_date") or r.get("trade_date") or "",
                _now_iso(),
                r.get("purchase_status") or "",
                _f(r.get("purchase_limit")),
                _f(r.get("daily_limit")),
                _f(r.get("fee_rate")),
            )
            for r in rows
        ]
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO fund_premium_snapshot "
            "(code, trade_date, name, type, price, nav, premium_rate, amount, "
            "change_pct, redeem_status, subscribe_status, signal, iopv, nav_date, updated_at, "
            "purchase_status, purchase_limit, daily_limit, fee_rate) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_fund_premium(self, trade_date: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT code, name, type, price, nav, premium_rate, amount, change_pct, "
            "redeem_status, subscribe_status, signal, iopv, nav_date, updated_at, "
            "purchase_status, purchase_limit, daily_limit, fee_rate "
            "FROM fund_premium_snapshot WHERE trade_date = ?",
            (trade_date,),
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def get_fund_premium_history(self, code: str, days: int = 30) -> list[dict]:
        """Recent snapshots for one code, for percentile computation.

        Returns rows (trade_date, premium_rate, amount) ordered by trade_date
        ascending. Caller decides if there's enough history to compute a
        percentile (see MIN_HISTORY_DAYS in the route).
        """
        rows = self._conn.execute(
            "SELECT trade_date, premium_rate, amount "
            "FROM fund_premium_snapshot WHERE code = ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (code, int(days)),
        ).fetchall()
        return [dict(r) for r in rows]

    # --- arbitrage_signal: Z-score based anomaly detection ---

    @_synchronized
    def upsert_signals(self, signals: list[dict]) -> int:
        """Insert or replace arbitrage signals for today."""
        if not signals:
            return 0
        payload = [
            (
                s.get("code"), s.get("trade_date"),
                s.get("name"), s.get("type"),
                s.get("signal_type"), _f(s.get("premium_rate")),
                _f(s.get("z_score")), _f(s.get("historical_mean")),
                _f(s.get("historical_std")), int(s.get("n_history") or 0),
                _f(s.get("cost_estimate")), _f(s.get("net_spread")),
                s.get("status", "ACTIVE"), _now_iso(),
            )
            for s in signals
        ]
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO arbitrage_signal "
            "(code, trade_date, name, type, signal_type, premium_rate, z_score, "
            "historical_mean, historical_std, n_history, cost_estimate, net_spread, "
            "status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_active_signals(self) -> list[dict]:
        """Get all ACTIVE signals, ordered by net_spread desc."""
        rows = self._conn.execute(
            "SELECT code, name, type, trade_date, signal_type, premium_rate, "
            "z_score, historical_mean, historical_std, n_history, "
            "cost_estimate, net_spread, status, updated_at "
            "FROM arbitrage_signal WHERE status = 'ACTIVE' "
            "ORDER BY net_spread DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def get_signal_history(self, days: int = 30) -> list[dict]:
        """Get recent signals (all statuses) ordered by date desc."""
        rows = self._conn.execute(
            "SELECT code, name, type, trade_date, signal_type, premium_rate, "
            "z_score, net_spread, status "
            "FROM arbitrage_signal "
            "ORDER BY trade_date DESC LIMIT ?",
            (int(days) * 50,),  # ~50 signals per day max
        ).fetchall()
        return [dict(r) for r in rows]

    @_synchronized
    def get_signal_stats(self) -> dict:
        """Aggregate signal counts."""
        active = self._conn.execute(
            "SELECT COUNT(*) FROM arbitrage_signal WHERE status = 'ACTIVE'"
        ).fetchone()[0]
        today = self._conn.execute(
            "SELECT COUNT(*) FROM arbitrage_signal WHERE trade_date = "
            "(SELECT MAX(trade_date) FROM arbitrage_signal)"
        ).fetchone()[0]
        return {"active": active, "latest_count": today}

    # --- fund_master: daily-refreshed static metadata (name/type) ---

    @_synchronized
    def upsert_fund_master(self, rows: list[dict]) -> int:
        """Upsert static fund metadata (code/name/type). Refreshed once/day."""
        if not rows:
            return 0
        payload = [
            (r.get("code"), r.get("name"), r.get("type"), _now_iso())
            for r in rows
            if r.get("code")
        ]
        if not payload:
            return 0
        return self._executemany_chunked(
            "INSERT OR REPLACE INTO fund_master (code, name, type, updated_at) "
            "VALUES (?, ?, ?, ?)",
            payload,
        )

    @_synchronized
    def get_fund_master_names(self, codes: list[str]) -> dict[str, str]:
        """Return {code: name} for the given codes from fund_master. Skips blanks."""
        codes = [c for c in (str(c).strip() for c in codes) if c]
        if not codes:
            return {}
        out: dict[str, str] = {}
        for i in range(0, len(codes), _BATCH):
            chunk = codes[i:i + _BATCH]
            placeholders = ", ".join("?" for _ in chunk)
            rows = self._conn.execute(
                f"SELECT code, name FROM fund_master WHERE code IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                name = str(row["name"] or "").strip()
                if name:
                    out[str(row["code"])] = name
        return out

    @_synchronized
    def fund_master_updated_at(self) -> str | None:
        """Last time fund_master was refreshed (for the UI's 'basic info updated at')."""
        row = self._conn.execute("SELECT MAX(updated_at) FROM fund_master").fetchone()
        return row[0] if row else None

    @_synchronized
    def fund_snapshot_codes(self, *, fund_type: str | None = None) -> list[str]:
        sql = "SELECT DISTINCT code FROM fund_premium_snapshot"
        params: list[Any] = []
        if fund_type:
            sql += " WHERE UPPER(type) = ?"
            params.append(fund_type.upper())
        sql += " ORDER BY code"
        rows = self._conn.execute(sql, params).fetchall()
        return [r["code"] for r in rows if r["code"]]

    @_synchronized
    def missing_etf_daily_codes(self, trade_date: str, *, limit: int | None = None) -> list[str]:
        sql = (
            "SELECT DISTINCT f.code FROM fund_premium_snapshot f "
            "LEFT JOIN etf_daily e ON e.code = f.code AND e.trade_date = ? "
            "WHERE UPPER(f.type) = 'ETF' AND e.code IS NULL "
            "ORDER BY f.code"
        )
        params: list[Any] = [trade_date]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [r["code"] for r in rows if r["code"]]

    # ------------------------------------------------------------------
    # Strict sync lifecycle and data readiness
    # ------------------------------------------------------------------

    @_synchronized
    def create_sync_run(self, trade_date: str, *, worker_id: str) -> str:
        """Create a durable sync attempt and return its opaque run ID."""
        run_id = str(uuid.uuid4())
        with self._write_transaction():
            self._conn.execute(
                "INSERT INTO sync_runs "
                "(run_id, trade_date, worker_id, status, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, trade_date, worker_id, QualityStatus.PENDING.value, _now_iso()),
            )
        return run_id

    @_synchronized
    def finish_sync_run(
        self,
        run_id: str,
        status: QualityStatus | str,
        *,
        error_summary: str = "",
    ) -> None:
        """Finish a sync attempt without turning failures into success markers."""
        normalized = QualityStatus(status)
        now = _now_iso()
        with self._write_transaction():
            cursor = self._conn.execute(
                "UPDATE sync_runs SET status = ?, finished_at = ?, error_summary = ? "
                "WHERE run_id = ?",
                (normalized.value, now, error_summary, run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown sync run: {run_id}")
            if normalized is QualityStatus.PUBLISHED:
                self._conn.execute(
                    "UPDATE sync_dataset_runs SET status = ?, published_rows = valid_rows, updated_at = ? "
                    "WHERE run_id = ? AND status = ?",
                    (
                        QualityStatus.PUBLISHED.value,
                        now,
                        run_id,
                        QualityStatus.VERIFIED.value,
                    ),
                )
                self._conn.execute(
                    "UPDATE bars_daily SET quality_status = ?, updated_at = ? WHERE sync_run_id = ?",
                    (QualityStatus.PUBLISHED.value, now, run_id),
                )

    @_synchronized
    def record_dataset_result(self, run_id: str, report: DatasetQualityReport) -> None:
        """Persist the complete quality report for one run and dataset."""
        with self._write_transaction():
            exists = self._conn.execute(
                "SELECT 1 FROM sync_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(f"unknown sync run: {run_id}")
            self._conn.execute(
                "INSERT OR REPLACE INTO sync_dataset_runs "
                "(run_id, dataset, trade_date, status, expected_rows, received_rows, "
                "valid_rows, published_rows, source, missing_codes_json, invalid_rows_json, "
                "blocking_reasons_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    report.dataset,
                    report.trade_date,
                    QualityStatus(report.status).value,
                    report.expected_rows,
                    report.received_rows,
                    report.valid_rows,
                    report.published_rows,
                    report.source,
                    json.dumps(report.missing_codes, ensure_ascii=False),
                    json.dumps(report.invalid_rows, ensure_ascii=False, default=str),
                    json.dumps(report.blocking_reasons, ensure_ascii=False),
                    _now_iso(),
                ),
            )

    @_synchronized
    def get_data_readiness(self, dataset: str, as_of: str) -> DataReadiness:
        """Return the latest exact-date dataset result; stale dates never qualify."""
        row = self._conn.execute(
            "SELECT run_id, status, expected_rows, valid_rows, published_rows, source, "
            "blocking_reasons_json FROM sync_dataset_runs "
            "WHERE dataset = ? AND trade_date = ? ORDER BY updated_at DESC LIMIT 1",
            (dataset, as_of),
        ).fetchone()
        if row is None:
            # 没有质量记录时，检查数据是否实际存在
            try:
                count = self._conn.execute(
                    f"SELECT COUNT(*) AS c FROM {dataset} WHERE trade_date = ?",
                    (as_of,),
                ).fetchone()
                actual = int(count["c"]) if count else 0
            except Exception:
                actual = 0
            if actual > 0:
                # Rows exist but there is NO quality-record for this exact date
                # (e.g. intraday/backfill wrote directly). Be honest: this is
                # NOT verified — return PARTIAL so consumers know the data is
                # present but unvalidated, rather than falsely claiming VERIFIED
                # (which let bypass writes fake "ready" status).
                return DataReadiness(
                    dataset=dataset,
                    as_of=as_of,
                    status=QualityStatus.PARTIAL,
                    expected_rows=actual,
                    valid_rows=actual,
                    published_rows=actual,
                    source="data_exists_unvalidated",
                    run_id="",
                    blocking_reasons=["no_quality_result_for_exact_date"],
                )
            return DataReadiness(
                dataset=dataset,
                as_of=as_of,
                status=QualityStatus.FAILED,
                expected_rows=0,
                valid_rows=0,
                published_rows=0,
                source="",
                run_id="",
                blocking_reasons=["no_quality_result_for_exact_date"],
            )
        return DataReadiness(
            dataset=dataset,
            as_of=as_of,
            status=QualityStatus(row["status"]),
            expected_rows=int(row["expected_rows"]),
            valid_rows=int(row["valid_rows"]),
            published_rows=int(row["published_rows"]),
            source=str(row["source"] or ""),
            run_id=str(row["run_id"]),
            blocking_reasons=list(json.loads(row["blocking_reasons_json"] or "[]")),
        )

    # ------------------------------------------------------------------
    # sync_meta
    # ------------------------------------------------------------------

    @_synchronized
    def get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM sync_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    @_synchronized
    def set_meta(self, key: str, value: str) -> None:
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO sync_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, _now_iso()),
            )

    def list_sync_errors(self, dataset: str | None = None) -> list[dict]:
        """Return persisted provider failure records written by _set_sync_error.

        Each ``sync_error:{dataset}:{source}`` meta key is one failure.  An
        empty-message entry (written by _clear_sync_error) signals recovery and
        is excluded so the caller sees only active failures.
        """
        prefix = "sync_error:" + (f"{dataset}:" if dataset else "")
        rows = self._conn.execute(
            "SELECT key, value, updated_at FROM sync_meta "
            "WHERE key LIKE ? ORDER BY updated_at DESC",
            (prefix + "%",),
        ).fetchall()
        errors: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row["value"] or "{}")
            except (TypeError, ValueError):
                continue
            if payload.get("ok") or not payload.get("message"):
                continue
            errors.append(
                {
                    "dataset": payload.get("dataset") or str(row["key"]).split(":", 2)[1],
                    "source": payload.get("source") or str(row["key"]).split(":", 2)[2],
                    "message": payload.get("message"),
                    "at": row["updated_at"],
                }
            )
        return errors

    @_synchronized
    def next_dataset_codes(
        self,
        dataset: str,
        codes: list[str],
        *,
        limit: int,
    ) -> list[str]:
        """Return a stable rotating slice and persist its cursor atomically.

        Dataset jobs are deliberately bounded, but repeatedly processing the
        first N securities permanently starves the rest of the universe.  The
        cursor is keyed by dataset so every bounded job eventually covers all
        eligible securities, including a wrap-around batch.
        """
        ordered = sorted({str(code).strip() for code in codes if str(code).strip()})
        take = min(max(int(limit), 0), len(ordered))
        if take == 0:
            return []

        key = f"dataset_cursor:{dataset}"
        row = self._conn.execute(
            "SELECT value FROM sync_meta WHERE key = ?", (key,)
        ).fetchone()
        last_code = str(row["value"]) if row else ""
        start = 0
        if last_code:
            start = next(
                (index for index, code in enumerate(ordered) if code > last_code),
                0,
            )
        selected = [ordered[(start + offset) % len(ordered)] for offset in range(take)]
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO sync_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, selected[-1], _now_iso()),
            )
        return selected

    # ------------------------------------------------------------------
    # Stats for status API
    # ------------------------------------------------------------------

    @_synchronized
    def table_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for t in (
            "trade_calendar",
            "security_master",
            "bars_daily",
            "stock_daily_basic",
            "etf_master",
            "fund_master",
            "fund_daily",
            "etf_daily",
            "etf_share_size",
            "index_master",
            "index_daily",
            "board_master",
            "board_members",
            "board_daily",
            "realtime_quote_snapshot",
            "fund_premium_snapshot",
            "dragon_tiger",
            "stock_capital_flow",
            "stock_capital_rank",
            "sector_capital_flow",
            "sector_snapshot",
            "global_market_index_daily",
            "us_theme_snapshot",
            "us_a_share_transmission",
            "premarket_news",
            "market_stage_snapshot",
            "stock_pool",
            # a-stock-data 扩展表
            "eps_forecast",
            "ths_hot_reason",
            "fund_flow_daily",
            "financial_snapshot",
            "financial_statement",
            "announcement",
            "zt_pool",
            "ths_limit_up",
            "zb_pool",
            "dt_pool",
            "yzt_pool",
            "option_chain",
            "hot_list",
            "popularity_rank",
            "margin_trading",
            "block_trade",
            "holder_num",
            "dividend_history",
            "northbound_flow",
            "cls_telegraph",
            "irm_qa",
            "stock_news",
            "lockup_expiry",
        ):
            row = self._conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
            out[t] = int(row["c"]) if row else 0
        return out

    @_synchronized
    def date_range(self, table: str) -> tuple[Optional[str], Optional[str]]:
        if table not in {
            "trade_calendar",
            "security_master",
            "bars_daily",
            "stock_daily_basic",
            "etf_master",
            "fund_master",
            "fund_daily",
            "etf_daily",
            "etf_share_size",
            "index_master",
            "index_daily",
            "board_master",
            "board_members",
            "board_daily",
            "realtime_quote_snapshot",
            "fund_premium_snapshot",
            "dragon_tiger",
            "stock_capital_flow",
            "stock_capital_rank",
            "sector_capital_flow",
            "sector_snapshot",
            "global_market_index_daily",
            "us_theme_snapshot",
            "us_a_share_transmission",
            "premarket_news",
            "market_stage_snapshot",
            "stock_pool",
        }:
            raise ValueError(f"unknown table: {table}")
        if table in {"security_master", "etf_master"}:
            date_col = "list_date"
            if table == "etf_master":
                date_col = "list_date"
            row = self._conn.execute(
                f"SELECT MIN({date_col}) AS lo, MAX({date_col}) AS hi FROM {table}"
            ).fetchone()
            if not row or not row["lo"]:
                return (None, None)
            return (row["lo"], row["hi"])
        if table in {"fund_master", "index_master", "board_master", "board_members"}:
            row = self._conn.execute(
                f"SELECT MIN(updated_at) AS lo, MAX(updated_at) AS hi FROM {table}"
            ).fetchone()
            if not row or not row["lo"]:
                return (None, None)
            return (row["lo"], row["hi"])
        row = self._conn.execute(
            f"SELECT MIN(trade_date) AS lo, MAX(trade_date) AS hi FROM {table}"
        ).fetchone()
        if not row or not row["lo"]:
            return (None, None)
        return (row["lo"], row["hi"])

    # ── a-stock-data 扩展 upsert 方法 ─────────────────────────────

    @_synchronized
    def upsert_eps_forecast(self, code: str, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO eps_forecast "
                    "(code, trade_date, year, count, min_eps, mean_eps, max_eps, net_profit, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, trade_date, str(r.get("year", "")),
                     int(_f(r.get("count")) or 0),
                     _f(r.get("min_eps")), _f(r.get("mean_eps")), _f(r.get("max_eps")),
                     _f(r.get("net_profit")), r.get("source", "ths"), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_ths_hot_reason(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM ths_hot_reason WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO ths_hot_reason "
                    "(trade_date, code, name, reason, change_pct, turnover, amount, close, market, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("name", ""), r.get("reason", ""),
                     _f(r.get("change_pct")), _f(r.get("turnover")), _f(r.get("amount")),
                     _f(r.get("close")), r.get("market", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_fund_flow_daily(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO fund_flow_daily "
                    "(code, trade_date, main_net, small_net, mid_net, large_net, super_net, "
                    "net_amount, turnover, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), _f(r.get("main_net")), _f(r.get("small_net")),
                     _f(r.get("mid_net")), _f(r.get("large_net")), _f(r.get("super_net")),
                     _f(r.get("net_amount")), _f(r.get("turnover")),
                     r.get("source", "sina"), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_financial_snapshot(self, code: str, data: dict) -> int:
        if not data:
            return 0
        import json as _json
        extra = {k: v for k, v in data.items()
                 if k not in ("liutongguben", "zongguben", "eps", "bvps", "roe", "profit", "income")}
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO financial_snapshot "
                "(code, trade_date, liutongguben, zongguben, eps, bvps, roe, profit, income, extra_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (code, _now_iso()[:10],
                 _f(data.get("liutongguben")), _f(data.get("zongguben")),
                 _f(data.get("eps")), _f(data.get("bvps")), _f(data.get("roe")),
                 _f(data.get("profit")), _f(data.get("income")),
                 _json.dumps(extra, ensure_ascii=False) if extra else None,
                 _now_iso()),
            )
        return 1

    @_synchronized
    def upsert_financial_statement(self, code: str, report_type: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        import json as _json
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO financial_statement "
                    "(code, report_date, report_type, payload_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (code, r.get("报告期", ""), report_type,
                     _json.dumps(r, ensure_ascii=False), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_announcements(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO announcement "
                    "(code, ann_date, title, ann_type, url, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), r.get("title", ""),
                     r.get("type", ""), r.get("url", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_zt_pool(self, trade_date: str, rows: list[dict], *, source: str = "eastmoney") -> int:
        if not rows:
            return 0
        table = "zt_pool" if source == "eastmoney" else "ths_limit_up"
        with self._write_transaction():
            self._conn.execute(f"DELETE FROM {table} WHERE trade_date = ?", (trade_date,))
            for r in rows:
                if table == "zt_pool":
                    self._conn.execute(
                        "INSERT INTO zt_pool "
                        "(trade_date, code, name, price, pct, amount, float_cap, turnover, "
                        "limit_days, first_seal, last_seal, seal_fund, break_times, industry, zt_stat, source, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (trade_date, r.get("code", ""), r.get("name", ""),
                         _f(r.get("price")), _f(r.get("pct")), _f(r.get("amount")),
                         _f(r.get("float_cap")), _f(r.get("turnover")),
                         int(_f(r.get("limit_days")) or 0),
                         r.get("first_seal", ""), r.get("last_seal", ""),
                         _f(r.get("seal_fund")), int(_f(r.get("break_times")) or 0),
                         r.get("industry", ""), r.get("zt_stat", ""), source, _now_iso()),
                    )
                else:
                    self._conn.execute(
                        "INSERT INTO ths_limit_up "
                        "(trade_date, code, name, price, pct, reason, board_type, seal_rate, "
                        "break_times, seal_amount, high_days, first_time, is_again, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (trade_date, r.get("code", ""), r.get("name", ""),
                         _f(r.get("price")), _f(r.get("pct")),
                         r.get("reason", ""), r.get("board_type", ""),
                         _f(r.get("seal_rate")), int(_f(r.get("break_times")) or 0),
                         _f(r.get("seal_amount")), r.get("high_days", ""),
                         r.get("first_time", ""), int(_f(r.get("is_again")) or 0), _now_iso()),
                    )
        return len(rows)

    @_synchronized
    def upsert_zb_pool(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM zb_pool WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO zb_pool "
                    "(trade_date, code, name, price, limit_price, pct, turnover, "
                    "first_seal, break_times, amplitude, speed, industry, zt_stat, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("name", ""),
                     _f(r.get("price")), _f(r.get("limit_price")), _f(r.get("pct")),
                     _f(r.get("turnover")), r.get("first_seal", ""),
                     int(_f(r.get("break_times")) or 0),
                     _f(r.get("amplitude")), _f(r.get("speed")),
                     r.get("industry", ""), r.get("zt_stat", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_dt_pool(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM dt_pool WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO dt_pool "
                    "(trade_date, code, name, price, pct, turnover, pe, seal_fund, "
                    "board_amount, dt_days, open_times, industry, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("name", ""),
                     _f(r.get("price")), _f(r.get("pct")), _f(r.get("turnover")),
                     _f(r.get("pe")), _f(r.get("seal_fund")), _f(r.get("board_amount")),
                     int(_f(r.get("dt_days")) or 0), int(_f(r.get("open_times")) or 0),
                     r.get("industry", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_yzt_pool(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM yzt_pool WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO yzt_pool "
                    "(trade_date, code, name, price, pct, turnover, amplitude, speed, "
                    "y_first_seal, y_limit_days, industry, zt_stat, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("name", ""),
                     _f(r.get("price")), _f(r.get("pct")), _f(r.get("turnover")),
                     _f(r.get("amplitude")), _f(r.get("speed")),
                     r.get("y_first_seal", ""), int(_f(r.get("y_limit_days")) or 0),
                     r.get("industry", ""), r.get("zt_stat", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_hot_list(self, trade_date: str, rows: list[dict], *, source: str = "ths") -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM hot_list WHERE trade_date = ? AND source = ?",
                               (trade_date, source))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO hot_list "
                    "(trade_date, code, name, rank, hot_value, change_pct, tags, source, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("name", ""),
                     int(_f(r.get("rank")) or 0), _f(r.get("hot_value")),
                     _f(r.get("change_pct")), r.get("tags", ""), source, _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_popularity_rank(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM popularity_rank WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO popularity_rank "
                    "(trade_date, code, market, rank, rank_change, history_rank_change, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (trade_date, r.get("code", ""), r.get("market", ""),
                     int(_f(r.get("rank")) or 0), int(_f(r.get("rank_change")) or 0),
                     int(_f(r.get("history_rank_change")) or 0), _now_iso()),
                )
        return len(rows)

    def _write_option_chain_rows(
        self,
        underlying: str,
        trade_date: str,
        rows: list[dict],
    ) -> None:
        for r in rows:
            self._conn.execute(
                "INSERT OR REPLACE INTO option_chain "
                "(underlying, trade_date, month, code, call_put, bid, ask, last, strike, "
                "open_interest, volume, amount, delta, gamma, theta, vega, iv, theory, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (underlying, trade_date, r.get("month", ""), r.get("code", ""),
                 r.get("call_put", ""), _f(r.get("bid")), _f(r.get("ask")),
                 _f(r.get("last")), _f(r.get("strike")),
                 _f(r.get("open_interest")), _f(r.get("volume")), _f(r.get("amount")),
                 _f(r.get("delta")), _f(r.get("gamma")), _f(r.get("theta")),
                 _f(r.get("vega")), _f(r.get("iv")), _f(r.get("theory")), _now_iso()),
            )

    @_synchronized
    def upsert_option_chain(self, underlying: str, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._write_option_chain_rows(underlying, trade_date, rows)
        return len(rows)

    @_synchronized
    def replace_option_chain(self, underlying: str, trade_date: str, rows: list[dict]) -> int:
        with self._write_transaction():
            self._conn.execute(
                "DELETE FROM option_chain WHERE underlying = ? AND trade_date = ?",
                (underlying, trade_date),
            )
            self._write_option_chain_rows(underlying, trade_date, rows)
        return len(rows)

    @_synchronized
    def upsert_margin_trading(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO margin_trading "
                    "(code, trade_date, rzye, rzmre, rzche, rqye, rqmcl, rqchl, rzrqye, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), _f(r.get("rzye")), _f(r.get("rzmre")),
                     _f(r.get("rzche")), _f(r.get("rqye")), _f(r.get("rqmcl")),
                     _f(r.get("rqchl")), _f(r.get("rzrqye")), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_block_trade(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO block_trade "
                    "(code, trade_date, price, close, premium_pct, vol, amount, buyer, seller, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), _f(r.get("price")), _f(r.get("close")),
                     _f(r.get("premium_pct")), _f(r.get("vol")), _f(r.get("amount")),
                     r.get("buyer", ""), r.get("seller", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_holder_num(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO holder_num "
                    "(code, end_date, holder_num, change_num, change_ratio, avg_shares, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), int(_f(r.get("holder_num")) or 0),
                     int(_f(r.get("change_num")) or 0),
                     _f(r.get("change_ratio")), _f(r.get("avg_shares")), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_dividend_history(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO dividend_history "
                    "(code, ex_date, bonus_rmb, transfer_ratio, bonus_ratio, plan, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), _f(r.get("bonus_rmb")),
                     _f(r.get("transfer_ratio")), _f(r.get("bonus_ratio")),
                     r.get("plan", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_northbound_flow(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM northbound_flow WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO northbound_flow "
                    "(trade_date, time, hgt_yi, sgt_yi, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (trade_date, r.get("time", ""), _f(r.get("hgt_yi")),
                     _f(r.get("sgt_yi")), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_irm_qa(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO irm_qa "
                    "(code, ask_time, question, company, answer, answerer, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("ask_time", ""), r.get("question", ""),
                     r.get("company", ""), r.get("answer"),
                     r.get("answerer", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_cls_telegraph(self, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            self._conn.execute("DELETE FROM cls_telegraph WHERE trade_date = ?", (trade_date,))
            for r in rows:
                self._conn.execute(
                    "INSERT INTO cls_telegraph "
                    "(trade_date, title, content, time, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (trade_date, r.get("title", ""), r.get("content", ""),
                     r.get("time", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_stock_news(self, code: str, trade_date: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO stock_news "
                    "(code, title, trade_date, url, source, summary, news_date, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("title", ""), trade_date,
                     r.get("url", ""), r.get("source", ""),
                     r.get("summary", ""), r.get("date", ""), _now_iso()),
                )
        return len(rows)

    @_synchronized
    def upsert_lockup_expiry(self, code: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._write_transaction():
            for r in rows:
                self._conn.execute(
                    "INSERT OR REPLACE INTO lockup_expiry "
                    "(code, free_date, free_shares, able_shares, free_ratio, lift_type, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (code, r.get("date", ""), _f(r.get("shares")),
                     _f(r.get("able_shares")), _f(r.get("ratio")),
                     r.get("type", ""), _now_iso()),
                )
        return len(rows)

    # ── market_regime ───────────────────────────────────────────────────

    @_synchronized
    def save_regime_result(self, result: dict) -> None:
        """保存市场环境分类结果。

        result 格式（来自 RegimeResult.to_dict()）::

            {trade_date, regime, confidence, bull_score, bear_score,
             strong_trend, technical_indicators, parameters}
        """
        with self._write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO market_regime "
                "(trade_date, regime, confidence, bull_score, bear_score, "
                "strong_trend, indicators_json, params_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result["trade_date"],
                    result["regime"],
                    result["confidence"],
                    result.get("bull_score"),
                    result.get("bear_score"),
                    1 if result.get("strong_trend") else 0,
                    json.dumps(result.get("technical_indicators", {}), ensure_ascii=False),
                    json.dumps(result.get("parameters", {}), ensure_ascii=False),
                    _now_iso(),
                ),
            )

    @_synchronized
    def get_latest_regime(self) -> dict | None:
        """返回最近一条市场环境分类结果。"""
        row = self._conn.execute(
            "SELECT * FROM market_regime ORDER BY trade_date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("indicators_json", "params_json"):
            raw = d.pop(key, None)
            if raw:
                try:
                    d[key.replace("_json", "")] = json.loads(raw)
                except (TypeError, ValueError):
                    pass
        d["strong_trend"] = bool(d.get("strong_trend"))
        return d

    @_synchronized
    def get_regime_history(self, days: int = 30) -> list[dict]:
        """返回近 N 天的市场环境分类历史。"""
        rows = self._conn.execute(
            "SELECT * FROM market_regime ORDER BY trade_date DESC LIMIT ?",
            (days,),
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            d = dict(r)
            for key in ("indicators_json", "params_json"):
                raw = d.pop(key, None)
                if raw:
                    try:
                        d[key.replace("_json", "")] = json.loads(raw)
                    except (TypeError, ValueError):
                        pass
            d["strong_trend"] = bool(d.get("strong_trend"))
            out.append(d)
        return out


# ----------------------------------------------------------------------
# Module-level helpers (free functions used by the store + sync layer)
# ----------------------------------------------------------------------


def _f(v: Any) -> Optional[float]:
    """Best-effort float coercion; None on failure."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rows_with_extra(
    rows: list[sqlite3.Row],
    *,
    extra_key: str = "extra_json",
    base_cols: tuple[str, ...] = (),
) -> list[dict]:
    """Expand rows: base columns + decoded extra_json keys."""
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        extra_raw = d.pop(extra_key, None)
        if extra_raw:
            try:
                d.update(json.loads(extra_raw))
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


def _upsert_market_wide(
    store: "MarketStore",
    table: str,
    trade_date: str,
    rows: list[dict],
    *,
    pk_cols: tuple[str, ...],
    value_cols: tuple[str, ...],
) -> int:
    """Upsert a market-wide (per-date) table: delete-then-insert for the date.

    ``code`` (when in pk_cols) comes from the row; ``trade_date`` is always the
    passed argument (rows may omit it). Text cols (name/code) are passed
    through; numeric value_cols are coerced via :func:`_f`.
    """
    if not rows:
        return 0
    cols = pk_cols + value_cols
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    text_cols = {"code", "trade_date", "name", "type", "signal",
                 "redeem_status", "subscribe_status",
                 # push 路径新增的文本型标识符列（按原值透传，不做 float 转换）
                 "sector", "rank_type", "theme_id", "board_type", "category",
                 "title", "pool_type", "currency", "symbol", "direction",
                 "source", "url", "published_at", "theme_name", "proxy_symbol",
                 "proxy_name", "us_theme"}
    payload = []
    for r in rows:
        vals = []
        for c in cols:
            if c == "trade_date":
                vals.append(r.get("trade_date") or trade_date)
            elif c in text_cols:
                vals.append(r.get(c))
            else:
                vals.append(_f(r.get(c)))
        vals.append(_now_iso())
        payload.append(tuple(vals))
    with store._write_transaction():
        store._conn.execute(
            f"DELETE FROM {table} WHERE trade_date = ?", (trade_date,)
        )
        for i in range(0, len(payload), _BATCH):
            store._conn.executemany(
                f"INSERT OR REPLACE INTO {table} ({col_list}, updated_at) "
                f"VALUES ({placeholders}, ?)",
                payload[i : i + _BATCH],
            )
    return len(payload)


def _get_market_wide(store: "MarketStore", table: str, trade_date: str) -> list[dict]:
    rows = store._conn.execute(
        f"SELECT * FROM {table} WHERE trade_date = ?", (trade_date,)
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        extra_raw = d.pop("extra_json", None)
        if extra_raw:
            try:
                d.update(json.loads(extra_raw))
            except (TypeError, ValueError):
                pass
        out.append(d)
    return out


def _has_market_wide(store: "MarketStore", table: str, trade_date: str) -> bool:
    row = store._conn.execute(
        f"SELECT 1 FROM {table} WHERE trade_date = ? LIMIT 1", (trade_date,)
    ).fetchone()
    return row is not None


# ----------------------------------------------------------------------
# Module-level singleton accessor (read-path safe)
# ----------------------------------------------------------------------

_store_singleton: Optional[MarketStore] = None
_store_lock = threading.Lock()


def get_market_store() -> Optional[MarketStore]:
    """Return the process-wide MarketStore singleton, or None on any failure.

    Callers in read paths (market_data_service, routes) MUST tolerate ``None`` and fall
    back to the live data chain — a DB init failure must never break reads.
    """
    global _store_singleton
    if _store_singleton is not None:
        return _store_singleton
    with _store_lock:
        if _store_singleton is None:
            try:
                _store_singleton = MarketStore()
            except Exception:
                logger.debug("MarketStore init failed; reads will bypass DB", exc_info=True)
                return None
    return _store_singleton


def db_read_enabled() -> bool:
    """True when the DB-read feature flag is on (default on)."""
    return os.getenv("VIBE_TRADING_MARKET_DB_READ", "1").strip() not in ("0", "false", "False")
