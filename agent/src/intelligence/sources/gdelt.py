from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable

import requests

from src.intelligence.models import NormalizedArticle
from src.intelligence.sources.base import IntelligenceSourceAdapter, SourceBatch, SourceError, SourceHealth


class GdeltSourceAdapter(IntelligenceSourceAdapter):
    source_id = "gdelt"
    source_name = "GDELT"

    def __init__(self, get: Callable[..., object] = requests.get) -> None:
        self._get = get

    def fetch(self, *, query: str = "", cursor: str | None = None, limit: int = 30) -> SourceBatch:
        now = datetime.now(timezone.utc)
        effective = query.strip() or "(economy OR market OR geopolitics OR technology)"
        try:
            response = self._get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={"query": effective, "mode": "artlist", "format": "json", "sort": "datedesc", "maxrecords": min(limit, 250), "timespan": "1d"},
                timeout=15,
                headers={"User-Agent": "SigmX-Intelligence/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
            rows: list[NormalizedArticle] = []
            for item in payload.get("articles", []):
                url = str(item.get("url") or "")
                title = str(item.get("title") or "").strip()
                if not title or not url:
                    continue
                raw_time = str(item.get("seendate") or "")
                try:
                    published = datetime.strptime(raw_time, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except ValueError:
                    published = now
                rows.append(NormalizedArticle(
                    upstream_id=hashlib.sha256(url.encode()).hexdigest()[:24], title=title, url=url,
                    source_id=self.source_id, source_name=str(item.get("domain") or self.source_name), source_tier="media",
                    published_at=published, fetched_at=now, content_type="news", market="GLOBAL",
                    language=str(item.get("language") or ""), region=str(item.get("sourcecountry") or ""),
                    content_policy="metadata", metadata={"gdelt": True},
                ))
            return SourceBatch(self.source_id, now, rows, SourceHealth.HEALTHY)
        except Exception as exc:
            return SourceBatch(self.source_id, now, [], SourceHealth.UNAVAILABLE,
                               [SourceError("gdelt_unavailable", str(exc), True)])
