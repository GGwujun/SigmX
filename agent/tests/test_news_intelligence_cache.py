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


def test_news_aggregation_deduplicates_same_title_across_sources(monkeypatch) -> None:
    rows = {
        "wallstreetcn": [
            {"title": "相同标题", "snippet": "华尔街见闻版本", "published": "Fri, 29 Aug 2026 10:00:00 +0800", "url": ""},
            {"title": "独有标题", "snippet": "只有见闻有", "published": "Fri, 29 Aug 2026 09:00:00 +0800", "url": ""},
        ],
        "cls": [
            {"title": "相同标题", "snippet": "财联社转载", "published": "Fri, 29 Aug 2026 10:05:00 +0800", "url": ""},
        ],
    }
    monkeypatch.setattr("src.data.tushare_news_client.fetch_tushare_news",
                        lambda src, limit: rows[src])

    result = news_routes._build_news_list("")

    assert [a["title"] for a in result["articles"]] == ["相同标题", "独有标题"]
    assert result["sources"] == ["华尔街见闻", "财联社"]


def test_news_aggregation_skips_unavailable_source(monkeypatch) -> None:
    def fake_fetch(src: str, limit: int) -> list[dict]:
        if src == "wallstreetcn":
            raise RuntimeError("cookie 过期")
        return [{"title": "财联社快讯", "snippet": "内容", "published": "", "url": ""}]

    monkeypatch.setattr("src.data.tushare_news_client.fetch_tushare_news", fake_fetch)

    result = news_routes._build_news_list("")

    assert [a["title"] for a in result["articles"]] == ["财联社快讯"]
    assert result["sources"] == ["财联社"]
