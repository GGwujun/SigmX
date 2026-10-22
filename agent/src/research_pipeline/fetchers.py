# -*- coding: utf-8 -*-
"""取数层（Core）：dataset 名 → 进程内直读 market_store 的取数函数。

全部走 ``get_market_store()`` 供应商内函数，绕开 HTTP 与 Data Hub 计费；
顺序执行不并发（差集归属清楚）。每行分配确定性证据 id ``ev-<dataset>-<i>``，
落盘 ``fetch/<dataset>.json`` 进运行目录。

数据集名是**数据层的表名口径**（bars_daily/stock_daily_basic…），不是阶段知识；
每阶段取哪些数据集由插件声明（见 plugin.StageDatasets）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .fsutil import now_iso, sha256_text, write_json
from .ledger import LedgerEntry


def _latest_trade_date(store: Any, trade_date: "str | None") -> "str | None":
    """没给 trade_date 时从 emotion 快照解析最近一个有数据的交易日。"""
    if trade_date:
        return trade_date
    snap = store.get_shortline_snapshot_fast("emotion")
    if not snap:
        return None
    return snap.get("trade_date") or None


def _df_records(df) -> "list[dict]":
    """DataFrame（date 索引 + OHLCV 列）→ 普通字典行（日期转字符串）。"""
    if df is None or df.empty:
        return []
    out: list[dict] = []
    reset = df.reset_index()
    for _, row in reset.iterrows():
        item: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, float):
                item[str(k)] = round(v, 6)
            elif hasattr(v, "isoformat"):
                item[str(k)] = v.isoformat()[:10]
            else:
                item[str(k)] = v
        out.append(item)
    return out


def _fetch_security_profile(store: Any, code: str, trade_date: "str | None") -> list:
    row = store.get_security_profile(code)
    return [row] if row else []


def _fetch_bars_daily_90d(store: Any, code: str, trade_date: "str | None") -> list:
    return _df_records(store.get_daily_bars(code, days=90))


def _fetch_daily_basic_90d(store: Any, code: str, trade_date: "str | None") -> list:
    return store.get_stock_daily_basic(code, days=90)


def _fetch_capital_flow_20d(store: Any, code: str, trade_date: "str | None") -> list:
    end = _latest_trade_date(store, trade_date) or datetime.now().strftime("%Y-%m-%d")
    start = (datetime.strptime(end, "%Y-%m-%d") - timedelta(days=40)).strftime("%Y-%m-%d")
    return store.get_stock_capital(code, start=start, end=end)


def _pool_fetcher(pool_type: str) -> Callable:
    def _fetch(store: Any, code: str, trade_date: "str | None") -> list:
        td = _latest_trade_date(store, trade_date)
        if not td:
            raise ValueError("pool 类数据集需要 trade_date（且情绪快照缺失时无法自动解析）")
        rows = store.get_pool(pool_type, td)
        # 只留本股与池归属字段，其余当背景噪声不进证据
        hit = [r for r in rows if str(r.get("code", "")).upper() == code.upper()]
        return hit if hit else rows[:30]

    return _fetch


def _snapshot_fetcher(kind: str) -> Callable:
    def _fetch(store: Any, code: str, trade_date: "str | None") -> list:
        snap = store.get_shortline_snapshot_fast(kind, trade_date)
        if not snap:
            return []
        return [{"trade_date": snap.get("trade_date", ""), "kind": kind,
                 "payload": snap.get("payload", {})}]

    return _fetch


def _fetch_announcements_90d(store: Any, code: str, trade_date: "str | None") -> list:
    return store.get_announcements(code, days=90)


FETCHERS: "dict[str, Callable]" = {
    "security_profile": _fetch_security_profile,
    "bars_daily_90d": _fetch_bars_daily_90d,
    "daily_basic_90d": _fetch_daily_basic_90d,
    "capital_flow_20d": _fetch_capital_flow_20d,
    "pool_zt_today": _pool_fetcher("zt"),
    "pool_zb_today": _pool_fetcher("zb"),
    "pool_dt_today": _pool_fetcher("dt"),
    "pool_yzt_today": _pool_fetcher("yzt"),
    "shortline_emotion": _snapshot_fetcher("emotion"),
    "shortline_themes": _snapshot_fetcher("themes"),
    "shortline_ladder": _snapshot_fetcher("ladder"),
    "shortline_firstboard": _snapshot_fetcher("firstboard"),
    "announcements_90d": _fetch_announcements_90d,
}


def fetch_dataset(store: Any, dataset: str, code: str, trade_date: "str | None",
                  *, registry: "dict[str, Callable] | None" = None) -> "tuple[list, str]":
    """执行一个数据集的取数，返回 (rows, error)。error 非空 = status=error。"""
    reg = registry if registry is not None else FETCHERS
    fn = reg.get(dataset)
    if fn is None:
        return [], f"未知数据集: {dataset}（可用: {', '.join(sorted(reg))}）"
    if store is None:
        return [], "market_store 未初始化（本地无数据）"
    try:
        rows = fn(store, code, trade_date)
    except Exception as exc:  # noqa: BLE001 —— 取数错误进信封，是审计痕迹不是崩溃
        return [], f"{type(exc).__name__}: {exc}"
    if not isinstance(rows, list):
        return [], f"数据集 {dataset} 返回了非列表结果"
    return rows, ""


def write_fetch(run_dir: "str | Path", dataset: str, params: dict, rows: "list | None",
                error: str, stage: str) -> LedgerEntry:
    """把取数结果写成 fetch/<dataset>.json 信封并出账本条目。

    status: error（取数炸了）| empty（0 行，如实说没数据）| ok。每行分配确定性
    证据 id，sha256 是证据内容的指纹（对账/防篡改用，进账本）。
    """
    status = "error" if error else ("ok" if rows else "empty")
    evidence: list[dict] = []
    if not error and rows:
        for i, row in enumerate(rows):
            evidence.append({"id": f"ev-{dataset}-{i}", "data": row})
    digest = sha256_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    envelope = {
        "dataset": dataset,
        "params": params,
        "status": status,
        "rows": len(rows) if (rows and not error) else 0,
        "evidence": evidence,
        "error": error,
        "sha256": digest,
        "stage": stage,
        "fetched_at": now_iso(),
    }
    rel = f"fetch/{dataset}.json"
    write_json(Path(run_dir) / rel, envelope)
    return LedgerEntry(dataset=dataset, params=params, status=status, file=rel,
                       sha256=digest, rows=envelope["rows"], stage=stage, error=error)
