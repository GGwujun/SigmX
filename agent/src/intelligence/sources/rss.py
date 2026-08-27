from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable

import requests

from src.intelligence.models import NormalizedArticle, SourceTier
from src.intelligence.sources.base import IntelligenceSourceAdapter, SourceBatch, SourceError, SourceHealth


class RssSourceAdapter(IntelligenceSourceAdapter):
    def __init__(self, source_id: str, source_name: str, url: str, *, market: str = "GLOBAL",
                 tier: SourceTier = "official", get: Callable[..., object] = requests.get) -> None:
        self.source_id, self.source_name, self.url, self.market, self.tier = source_id, source_name, url, market, tier
        self._get = get

    def fetch(self, *, query: str = "", cursor: str | None = None, limit: int = 30) -> SourceBatch:
        now = datetime.now(timezone.utc)
        try:
            response = self._get(self.url, timeout=15, headers={"User-Agent": "SigmX-Intelligence/1.0"})
            response.raise_for_status()
            root = ET.fromstring(response.content)
            rows: list[NormalizedArticle] = []
            for item in root.findall(".//item")[:limit]:
                title = (item.findtext("title") or "").strip()
                summary = (item.findtext("description") or "").strip()
                if not title or (query and query not in title and query not in summary):
                    continue
                url = (item.findtext("link") or "").strip()
                raw_date = (item.findtext("pubDate") or "").strip()
                try:
                    published = parsedate_to_datetime(raw_date) if raw_date else now
                    if published.tzinfo is None: published = published.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    published = now
                rows.append(NormalizedArticle(
                    upstream_id=hashlib.sha256((url or title).encode()).hexdigest()[:24], title=title, url=url,
                    source_id=self.source_id, source_name=self.source_name, source_tier=self.tier,
                    published_at=published, fetched_at=now, content_type="announcement", summary=summary[:1000],
                    market=self.market, content_policy="summary",
                ))
            return SourceBatch(self.source_id, now, rows, SourceHealth.HEALTHY)
        except Exception as exc:
            return SourceBatch(self.source_id, now, [], SourceHealth.UNAVAILABLE,
                               [SourceError("rss_unavailable", str(exc), True)])


def default_official_sources() -> list[RssSourceAdapter]:
    return [
        RssSourceAdapter("sec", "美国证券交易委员会", "https://www.sec.gov/news/pressreleases.rss", market="US"),
        RssSourceAdapter("federal_reserve", "美联储", "https://www.federalreserve.gov/feeds/press_all.xml", market="GLOBAL"),
        RssSourceAdapter("ecb", "欧洲央行", "https://www.ecb.europa.eu/rss/press.html", market="GLOBAL"),
    ]
