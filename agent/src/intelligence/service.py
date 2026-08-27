from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.intelligence.models import NormalizedArticle
from src.intelligence.sources.base import IntelligenceSourceAdapter, SourceBatch, SourceHealth
from src.intelligence.store import IntelligenceStore


@dataclass(frozen=True)
class IntelligenceQuery:
    query: str = ""
    content_type: str = ""
    market: str = ""
    limit: int = 30
    offset: int = 0


@dataclass(frozen=True)
class IntelligenceResult:
    articles: list[NormalizedArticle]
    total: int
    source_health: dict[str, SourceBatch]
    degraded: bool
    warnings: list[str] = field(default_factory=list)


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


class IntelligenceService:
    def __init__(self, store: IntelligenceStore, sources: Iterable[IntelligenceSourceAdapter]) -> None:
        self.store = store
        self.sources = list(sources)

    def search(self, query: IntelligenceQuery) -> IntelligenceResult:
        batches: dict[str, SourceBatch] = {}
        unique: dict[str, NormalizedArticle] = {}
        title_keys: set[str] = set()
        warnings: list[str] = []
        fetched: dict[str, SourceBatch] = {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(self.sources)))) as pool:
            futures = {pool.submit(source.fetch, query=query.query, limit=max(query.limit, 30)): source for source in self.sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    fetched[source.source_id] = future.result()
                except Exception as exc:
                    from datetime import datetime, timezone
                    from src.intelligence.sources.base import SourceError
                    fetched[source.source_id] = SourceBatch(source.source_id, datetime.now(timezone.utc), [], SourceHealth.UNAVAILABLE,
                                                            [SourceError("adapter_error", str(exc), True)])
        for source in self.sources:
            batch = fetched[source.source_id]
            batches[source.source_id] = batch
            if batch.health is not SourceHealth.HEALTHY:
                warnings.extend(error.message for error in batch.errors)
            for article in batch.articles:
                url_key = _canonical_url(article.url)
                title_key = "".join(article.title.casefold().split())
                if (url_key and url_key in unique) or title_key in title_keys:
                    continue
                unique[url_key or f"title:{title_key}"] = article
                title_keys.add(title_key)
        if unique:
            self.store.upsert_articles(list(unique.values()))
        stored = self.store.search_articles(query=query.query, limit=query.limit, offset=query.offset)
        articles = [item for item in stored.items
                    if (not query.content_type or item.content_type == query.content_type)
                    and (not query.market or item.market == query.market)]
        return IntelligenceResult(
            articles=articles,
            total=len(articles) if query.content_type or query.market else stored.total,
            source_health=batches,
            degraded=any(batch.health is not SourceHealth.HEALTHY for batch in batches.values()),
            warnings=warnings,
        )
