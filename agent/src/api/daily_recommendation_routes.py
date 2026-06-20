"""Daily recommendation routes.

This module adds a recommendation workflow without changing the existing
market-intelligence pages. A generated pick is persisted as a timestamped
record, then later enriched with T+0/T+1/T+3/T+5 performance from OHLCV data.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

_CST = timezone(timedelta(hours=8))
_STORE_PATH = Path.home() / ".vibe-trading" / "daily_recommendations.json"
_DB_PATH = Path.home() / ".vibe-trading" / "daily_recommendations.db"
_STORE_LOCK = threading.Lock()
_MAX_GENERATED = 5
logger = logging.getLogger(__name__)


class GenerateRecommendationsRequest(BaseModel):
    slot: str = Field(..., description="morning, afternoon, or manual")
    limit: int = Field(default=5, ge=1, le=10)


def _now_cst() -> datetime:
    return datetime.now(_CST)


def _today_cst() -> str:
    return _now_cst().strftime("%Y-%m-%d")


def _normalize_slot(slot: str) -> str:
    value = slot.strip().lower()
    if value in {"morning", "am", "0927", "09:27"}:
        return "morning"
    if value in {"afternoon", "pm", "1430", "14:30"}:
        return "afternoon"
    if value in {"manual", "now"}:
        return "manual"
    raise HTTPException(status_code=400, detail="slot must be morning, afternoon, or manual")


def _slot_label(slot: str) -> str:
    return {"morning": "9:27", "afternoon": "14:30", "manual": "手动生成"}.get(slot, slot)


def _load_records() -> list[dict[str, Any]]:
    _ensure_db()
    try:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(
                "select payload from recommendations order by created_at desc, rank asc"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
    except Exception:
        logger.exception("failed to load daily recommendations from sqlite")
        return []


def _load_legacy_json_records() -> list[dict[str, Any]]:
    if not _STORE_PATH.exists():
        return []
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_records(records: list[dict[str, Any]]) -> None:
    _ensure_db()
    with sqlite3.connect(_DB_PATH) as conn:
        conn.executemany(
            """
            insert into recommendations (
                id, date, slot, symbol, rank, name, price_at_pick,
                score, strategy, created_at, payload
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                date=excluded.date,
                slot=excluded.slot,
                symbol=excluded.symbol,
                rank=excluded.rank,
                name=excluded.name,
                price_at_pick=excluded.price_at_pick,
                score=excluded.score,
                strategy=excluded.strategy,
                created_at=excluded.created_at,
                payload=excluded.payload
            """,
            [
                (
                    r.get("id"),
                    r.get("date"),
                    r.get("slot"),
                    r.get("symbol"),
                    int(r.get("rank", 0) or 0),
                    r.get("name"),
                    float(r.get("price_at_pick", 0) or 0),
                    float(r.get("score", 0) or 0),
                    r.get("strategy"),
                    r.get("created_at"),
                    json.dumps(r, ensure_ascii=False),
                )
                for r in records
            ],
        )


def _ensure_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_DB_PATH) as conn:
        conn.execute(
            """
            create table if not exists recommendations (
                id text primary key,
                date text not null,
                slot text not null,
                symbol text not null,
                rank integer not null,
                name text not null,
                price_at_pick real not null,
                score real not null,
                strategy text not null,
                created_at text not null,
                payload text not null
            )
            """
        )
        conn.execute("create index if not exists idx_recs_date_slot on recommendations(date, slot)")
        conn.execute("create index if not exists idx_recs_symbol on recommendations(symbol)")
        count = conn.execute("select count(*) from recommendations").fetchone()[0]
    if count == 0:
        legacy = _load_legacy_json_records()
        if legacy:
            with sqlite3.connect(_DB_PATH) as conn:
                conn.executemany(
                    """
                    insert or replace into recommendations (
                        id, date, slot, symbol, rank, name, price_at_pick,
                        score, strategy, created_at, payload
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            r.get("id"),
                            r.get("date"),
                            r.get("slot"),
                            r.get("symbol"),
                            int(r.get("rank", 0) or 0),
                            r.get("name"),
                            float(r.get("price_at_pick", 0) or 0),
                            float(r.get("score", 0) or 0),
                            r.get("strategy"),
                            r.get("created_at"),
                            json.dumps(r, ensure_ascii=False),
                        )
                        for r in legacy
                    ],
                )


def _record_key(date: str, slot: str, symbol: str) -> str:
    return f"{date}:{slot}:{symbol}"


def _strategy_label(category_id: str) -> str:
    return {
        "breakout": "突破",
        "trend": "趋势",
        "oversold": "低吸",
        "event": "事件催化",
    }.get(category_id, category_id)


def _slot_adjusted_score(item: dict[str, Any], slot: str) -> float:
    score = float(item.get("confidence", 0) or 0)
    cat = item.get("category_id", "")
    change = float(item.get("change_pct", 0) or 0)
    if slot == "morning":
        if cat in {"breakout", "event"}:
            score += 0.05
        if change > 6:
            score -= 0.04
    elif slot == "afternoon":
        if cat in {"trend", "breakout"}:
            score += 0.05
        if change < 0:
            score -= 0.05
    return max(0.01, min(0.99, score))


def _candidate_pool(slot: str) -> list[dict[str, Any]]:
    from src.api.opportunity_routes import _build_opportunities

    payload = _build_opportunities()
    if payload.get("error"):
        raise HTTPException(status_code=503, detail=str(payload["error"]))

    items: list[dict[str, Any]] = []
    for category in payload.get("categories", []):
        category_id = category.get("id", "")
        category_label = category.get("label", category_id)
        for raw in category.get("opportunities", []):
            item = dict(raw)
            item["category_id"] = category_id
            item["category_label"] = category_label
            item["score"] = round(_slot_adjusted_score(item, slot), 3)
            items.append(item)

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda x: x.get("score", 0), reverse=True):
        symbol = str(item.get("symbol", "")).upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        unique.append(item)
    return unique


def _make_record(item: dict[str, Any], slot: str, rank: int) -> dict[str, Any]:
    now = _now_cst()
    symbol = str(item["symbol"]).upper()
    date = now.strftime("%Y-%m-%d")
    return {
        "id": _record_key(date, slot, symbol),
        "date": date,
        "slot": slot,
        "slot_label": _slot_label(slot),
        "rank": rank,
        "symbol": symbol,
        "name": item.get("name", symbol),
        "price_at_pick": float(item.get("price", 0) or 0),
        "change_pct_at_pick": float(item.get("change_pct", 0) or 0),
        "score": float(item.get("score", item.get("confidence", 0)) or 0),
        "strategy": _strategy_label(str(item.get("category_id", ""))),
        "category": item.get("category_id", ""),
        "reason": item.get("reason", ""),
        "risk_note": _risk_note(item),
        "created_at": now.isoformat(),
        "source": "opportunity_scanner",
    }


def _risk_note(item: dict[str, Any]) -> str:
    cat = item.get("category_id", "")
    if cat == "breakout":
        return "放量突破信号需要关注次日是否继续放量，缩量回落则信号失效。"
    if cat == "trend":
        return "趋势延续信号需要关注均线结构是否保持，跌破短期均线需降级。"
    if cat == "oversold":
        return "超跌反弹信号反转确认较弱，若继续创新低应快速剔除。"
    if cat == "event":
        return "事件催化信号对新闻和外部概率变化敏感，需要防止高开低走。"
    return "仅作为候选标的，需要结合流动性、仓位和止损条件复核。"


def _bar_date(index_value: Any) -> str:
    if hasattr(index_value, "strftime"):
        return index_value.strftime("%Y-%m-%d")
    return str(index_value)[:10]


def _performance_for(record: dict[str, Any]) -> dict[str, Any]:
    from src.data.ohlcv_cache import fetch_with_cache

    price = float(record.get("price_at_pick", 0) or 0)
    symbol = str(record.get("symbol", ""))
    if not symbol or price <= 0:
        return {"status": "missing_price"}

    df = fetch_with_cache(symbol, days=40)
    if df is None or df.empty or "close" not in df.columns:
        return {"status": "no_market_data"}

    pick_date = str(record.get("date", ""))
    rows = []
    for idx, row in df.sort_index().iterrows():
        date = _bar_date(idx)
        if date >= pick_date:
            close = float(row.get("close", 0) or 0)
            high = float(row.get("high", close) or close)
            low = float(row.get("low", close) or close)
            rows.append({"date": date, "close": close, "high": high, "low": low})
    if not rows:
        return {"status": "pending"}

    out: dict[str, Any] = {
        "status": "ok",
        "latest_date": rows[-1]["date"],
        "latest_return_pct": round((rows[-1]["close"] - price) / price * 100, 2),
        "max_gain_pct": round((max(r["high"] for r in rows) - price) / price * 100, 2),
        "max_drawdown_pct": round((min(r["low"] for r in rows) - price) / price * 100, 2),
    }
    horizons = {"t0": 0, "t1": 1, "t3": 3, "t5": 5}
    for key, offset in horizons.items():
        if len(rows) > offset:
            close = rows[offset]["close"]
            out[key] = {
                "date": rows[offset]["date"],
                "close": round(close, 3),
                "return_pct": round((close - price) / price * 100, 2),
            }
        else:
            out[key] = None
    return out


def _with_performance(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for record in records:
        enriched.append({**record, "performance": _performance_for(record)})
    return enriched


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [r for r in records if r.get("performance", {}).get("t1")]
    if not completed:
        return {"count": len(records), "t1_count": 0, "t1_win_rate": None, "t1_avg_return": None}
    t1_returns = [float(r["performance"]["t1"]["return_pct"]) for r in completed]
    wins = [x for x in t1_returns if x > 0]
    return {
        "count": len(records),
        "t1_count": len(t1_returns),
        "t1_win_rate": round(len(wins) / len(t1_returns) * 100, 1),
        "t1_avg_return": round(sum(t1_returns) / len(t1_returns), 2),
    }


def _has_slot_record(records: list[dict[str, Any]], date: str, slot: str) -> bool:
    return any(r.get("date") == date and r.get("slot") == slot for r in records)


def _generate_for_slot(slot: str, limit: int) -> list[dict[str, Any]]:
    slot = _normalize_slot(slot)
    date = _today_cst()
    candidates = _candidate_pool(slot)
    if not candidates:
        return []

    selected = candidates[: min(limit, _MAX_GENERATED)]
    new_records = [_make_record(item, slot, rank + 1) for rank, item in enumerate(selected)]
    with _STORE_LOCK:
        records = _load_records()
        existing = {str(r.get("id")): r for r in records}
        for record in new_records:
            existing[record["id"]] = record
        records = sorted(existing.values(), key=lambda r: str(r.get("created_at", "")), reverse=True)
        _save_records(records)
    return new_records


def _is_trading_day_today() -> bool:
    try:
        from src.data.trade_calendar import is_trading_day

        return bool(is_trading_day(_today_cst()))
    except Exception:
        return _now_cst().weekday() < 5


AuthDep = Callable[..., Awaitable[Any] | Any]


def register_daily_recommendation_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
    require_event_stream_auth: AuthDep | None = None,
) -> None:
    if require_auth is None or require_event_stream_auth is None:
        import sys as _sys

        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:
            raise RuntimeError("register_daily_recommendation_routes: api_server not in sys.modules")
        if require_auth is None:
            require_auth = host.require_auth
        if require_event_stream_auth is None:
            require_event_stream_auth = host.require_event_stream_auth

    @app.post("/daily-recommendations/generate", dependencies=[Depends(require_auth)])
    async def generate_recommendations(body: GenerateRecommendationsRequest, request: Request) -> dict[str, Any]:
        slot = _normalize_slot(body.slot)
        date = _today_cst()
        new_records = _generate_for_slot(slot, body.limit)
        if not new_records:
            raise HTTPException(status_code=503, detail="No recommendation candidates are available")

        return {
            "date": date,
            "slot": slot,
            "slot_label": _slot_label(slot),
            "items": _with_performance(new_records),
            "updated_at": _now_cst().isoformat(),
        }

    @app.get("/daily-recommendations", dependencies=[Depends(require_auth)])
    async def list_recommendations(
        request: Request,
        date: str = Query("", max_length=10),
        slot: str = Query("", max_length=16),
        limit: int = Query(80, ge=1, le=300),
    ) -> dict[str, Any]:
        with _STORE_LOCK:
            records = _load_records()

        if date:
            records = [r for r in records if r.get("date") == date]
        if slot:
            normalized = _normalize_slot(slot)
            records = [r for r in records if r.get("slot") == normalized]
        records = records[:limit]
        enriched = _with_performance(records)
        return {
            "items": enriched,
            "summary": _summary(enriched),
            "updated_at": _now_cst().isoformat(),
        }

    @app.get("/daily-recommendations/backtest", dependencies=[Depends(require_auth)])
    async def recommendation_backtest(
        request: Request,
        days: int = Query(30, ge=1, le=365),
    ) -> dict[str, Any]:
        cutoff = (_now_cst() - timedelta(days=days)).strftime("%Y-%m-%d")
        with _STORE_LOCK:
            records = [r for r in _load_records() if str(r.get("date", "")) >= cutoff]
        enriched = _with_performance(records)

        by_slot: dict[str, list[dict[str, Any]]] = {}
        for record in enriched:
            by_slot.setdefault(str(record.get("slot", "manual")), []).append(record)

        slot_rows = []
        for slot, rows in sorted(by_slot.items()):
            slot_rows.append({"slot": slot, "slot_label": _slot_label(slot), **_summary(rows)})

        return {
            "days": days,
            "summary": _summary(enriched),
            "by_slot": slot_rows,
            "items": enriched,
            "updated_at": _now_cst().isoformat(),
        }

    @app.on_event("startup")
    async def start_daily_recommendation_scheduler() -> None:
        if os.getenv("DAILY_RECOMMENDATIONS_AUTORUN", "1").strip().lower() in {"0", "false", "no"}:
            return

        import asyncio

        async def _loop() -> None:
            while True:
                try:
                    now = _now_cst()
                    if _is_trading_day_today():
                        checks = [
                            ("morning", 9, 27),
                            ("afternoon", 14, 30),
                        ]
                        with _STORE_LOCK:
                            records = _load_records()
                        for slot, hour, minute in checks:
                            due = now.hour > hour or (now.hour == hour and now.minute >= minute)
                            before_close = now.hour < 15 or (now.hour == 15 and now.minute <= 5)
                            if due and before_close and not _has_slot_record(records, _today_cst(), slot):
                                await asyncio.get_running_loop().run_in_executor(None, _generate_for_slot, slot, 5)
                                logger.info("daily recommendations generated for %s", slot)
                    await asyncio.sleep(60)
                except Exception:
                    logger.exception("daily recommendation scheduler tick failed")
                    await asyncio.sleep(300)

        asyncio.create_task(_loop())
