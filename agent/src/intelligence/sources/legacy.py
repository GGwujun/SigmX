from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

from src.intelligence.models import NormalizedArticle, SourceTier
from src.intelligence.sources.base import IntelligenceSourceAdapter, SourceBatch, SourceError, SourceHealth


class LegacyNewsAdapter(IntelligenceSourceAdapter):
    def __init__(
        self, source_id: str, source_name: str, tier: SourceTier,
        fetcher: Callable[[int, str], list[dict]], *, market: str = "CN",
    ) -> None:
        self.source_id = source_id
        self.source_name = source_name
        self.tier = tier
        self.fetcher = fetcher
        self.market = market

    def fetch(self, *, query: str = "", cursor: str | None = None, limit: int = 30) -> SourceBatch:
        now = datetime.now(timezone.utc)
        try:
            raw = self.fetcher(limit, query)
            rows = [self._normalize(item, now) for item in raw if item.get("title")]
            return SourceBatch(self.source_id, now, rows, SourceHealth.HEALTHY)
        except Exception as exc:
            return SourceBatch(self.source_id, now, [], SourceHealth.UNAVAILABLE,
                               [SourceError("upstream_error", str(exc), True)])

    def _normalize(self, item: dict, fetched_at: datetime) -> NormalizedArticle:
        published = item.get("published") or ""
        try:
            published_at = parsedate_to_datetime(published) if published else fetched_at
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            published_at = fetched_at
        url = str(item.get("url") or "")
        upstream_id = hashlib.sha256((url or str(item["title"])).encode("utf-8")).hexdigest()[:24]
        return NormalizedArticle(
            upstream_id=upstream_id, title=str(item["title"]), url=url,
            source_id=self.source_id, source_name=self.source_name, source_tier=self.tier,
            published_at=published_at, fetched_at=fetched_at, content_type="news",
            summary=str(item.get("snippet") or ""), market=self.market,
            content_policy="summary",
        )


def default_legacy_sources() -> list[LegacyNewsAdapter]:
    from src.api.news_routes import _fetch_bing_news, _fetch_wallstreetcn
    from src.data.astock_client import eastmoney_global_news, sina_7x24_news
    from src.data.tushare_news_client import fetch_tushare_news

    def eastmoney(limit: int, query: str) -> list[dict]:
        rows = eastmoney_global_news(limit)
        return [{"title": item.get("title", ""), "snippet": item.get("summary", ""),
                 "published": item.get("time", ""), "url": ""} for item in rows
                if not query or query in str(item.get("title", "")) or query in str(item.get("summary", ""))]

    def sina(limit: int, query: str) -> list[dict]:
        rows = sina_7x24_news(page_size=limit)
        return [{"title": item.get("title", ""), "snippet": item.get("summary", ""),
                 "published": item.get("date", ""), "url": item.get("url", "")} for item in rows
                if not query or query in str(item.get("title", "")) or query in str(item.get("summary", ""))]

    def tushare(src: str):
        """Tushare 资讯页抓取(需要 TUSHARE_COOKIE);cookie 过期时抛错标记源不可用。"""
        def fetch(limit: int, query: str) -> list[dict]:
            rows = fetch_tushare_news(src, limit=limit)
            return [row for row in rows
                    if not query or query in row["title"] or query in row["snippet"]]
        return fetch

    return [
        # 华尔街见闻原走 RSSHub(本地 docker 内网主机名解析不到,长期断流),
        # 改为 tushare 资讯页直连。
        LegacyNewsAdapter("wallstreetcn", "华尔街见闻", "media", tushare("wallstreetcn")),
        LegacyNewsAdapter("sina", "新浪财经", "media", sina),
        LegacyNewsAdapter("eastmoney", "东方财富", "media", eastmoney),
        LegacyNewsAdapter("cls", "财联社", "media", tushare("cls")),
        LegacyNewsAdapter("yicai", "第一财经", "media", tushare("yicai")),
        LegacyNewsAdapter("10jqka", "同花顺", "media", tushare("10jqka")),
        LegacyNewsAdapter("xueqiu", "雪球", "media", tushare("xq")),
        LegacyNewsAdapter("jinshi", "金十数据", "media", tushare("jinshi")),
        LegacyNewsAdapter("jinrongjie", "金融界", "media", tushare("jinrongjie")),
        LegacyNewsAdapter("bing", "Bing", "search", lambda limit, query: _fetch_bing_news(f"A股 {query}".strip(), limit)),
    ]
