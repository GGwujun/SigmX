from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.api import news_routes
from src.api.news_routes import get_cached_news_list
from src.data.market_store import MarketStore


def _payload(title: str) -> dict:
    return {
        "articles": [{"title": title, "url": "https://example.test/1", "source": "测试源", "published": "", "snippet": ""}],
        "query": "A股",
        "sources": ["测试源"],
        "updated_at": "2026-08-25T09:00:00+00:00",
    }


def test_repeated_intelligence_query_uses_persistent_cache(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    now = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    calls = 0

    def fetcher(keyword: str) -> dict:
        nonlocal calls
        calls += 1
        return _payload("首次抓取")

    first = get_cached_news_list("新能源", store=store, fetcher=fetcher, now=now)
    second = get_cached_news_list(" 新能源 ", store=store, fetcher=fetcher, now=now + timedelta(minutes=9))

    assert calls == 1
    assert first["cache_status"] == "live"
    assert second["cache_status"] == "fresh_cache"
    assert second["articles"][0]["title"] == "首次抓取"


def test_failed_refresh_falls_back_to_cache_no_older_than_24_hours(tmp_path: Path) -> None:
    store = MarketStore(tmp_path / "market.db")
    now = datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc)
    get_cached_news_list("公告", store=store, fetcher=lambda _: _payload("缓存新闻"), now=now)

    stale = get_cached_news_list("公告", store=store, fetcher=lambda _: _payload("") | {"articles": []}, now=now + timedelta(minutes=11))
    expired = get_cached_news_list("公告", store=store, fetcher=lambda _: _payload("") | {"articles": []}, now=now + timedelta(hours=25))

    assert stale["cache_status"] == "stale_cache"
    assert stale["articles"][0]["title"] == "缓存新闻"
    assert expired["cache_status"] == "live"
    assert expired["articles"] == []


def test_news_aggregation_deduplicates_same_url_across_sources(monkeypatch) -> None:
    monkeypatch.setattr(news_routes, "_fetch_wallstreetcn", lambda limit, keyword: [
        {"title": "原始标题", "url": "https://example.test/same", "source": "源一", "published": "", "snippet": ""},
    ])
    monkeypatch.setattr(news_routes, "_fetch_bing_news", lambda query, max_results: [
        {"title": "转载标题", "url": "https://example.test/same", "source": "源二", "published": "", "snippet": ""},
    ])

    result = news_routes._build_news_list("测试")

    assert len(result["articles"]) == 1
