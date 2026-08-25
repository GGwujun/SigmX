from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.data.market_store import MarketStore


def test_news_query_cache_uses_fresh_then_stale_window(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    fetched_at = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    payload = {"articles": [{"title": "测试新闻"}], "query": "A股"}

    store.cache_news_query("news:", payload, ttl_seconds=300, now=fetched_at)

    fresh = store.get_cached_news_query("news:", max_stale_seconds=86_400, now=fetched_at + timedelta(minutes=4))
    stale = store.get_cached_news_query("news:", max_stale_seconds=86_400, now=fetched_at + timedelta(minutes=6))
    expired = store.get_cached_news_query("news:", max_stale_seconds=86_400, now=fetched_at + timedelta(hours=25))

    assert fresh is not None and fresh["cache_status"] == "fresh"
    assert stale is not None and stale["cache_status"] == "stale"
    assert expired is None
    assert stale["payload"] == payload


def test_news_retention_prunes_query_snapshots_and_historical_rows(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    now = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=91)
    recent = now - timedelta(days=89)
    store.cache_news_query("old", {"articles": []}, ttl_seconds=300, now=old)
    store.cache_news_query("recent", {"articles": []}, ttl_seconds=300, now=recent)
    store._conn.execute(
        "INSERT INTO stock_news (code,title,trade_date,url,source,summary,news_date,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("000001.SZ", "旧闻", "20260525", "old", "test", "", "", old.isoformat()),
    )
    store._conn.execute(
        "INSERT INTO stock_news (code,title,trade_date,url,source,summary,news_date,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        ("000001.SZ", "新讯", "20260528", "new", "test", "", "", recent.isoformat()),
    )
    store._conn.commit()

    removed = store.prune_news_history(keep_days=90, now=now)

    assert removed["query_cache"] == 1
    assert removed["stock_news"] == 1
    assert store.get_cached_news_query("old", max_stale_seconds=10_000_000, now=now) is None
    assert store.get_cached_news_query("recent", max_stale_seconds=10_000_000, now=now) is not None
    assert store._conn.execute("SELECT title FROM stock_news").fetchone()[0] == "新讯"
