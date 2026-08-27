from __future__ import annotations

from datetime import datetime, timezone

from src.intelligence.models import NormalizedArticle
from src.intelligence.service import IntelligenceQuery, IntelligenceService
from src.intelligence.sources.base import SourceBatch, SourceError, SourceHealth
from src.intelligence.store import IntelligenceStore


class FakeSource:
    def __init__(self, source_id: str, rows: list[NormalizedArticle], *, failed: bool = False) -> None:
        self.source_id = source_id
        self.source_name = source_id
        self.rows = rows
        self.failed = failed

    def fetch(self, *, query: str = "", cursor: str | None = None, limit: int = 30) -> SourceBatch:
        if self.failed:
            return SourceBatch(self.source_id, datetime.now(timezone.utc), [], SourceHealth.UNAVAILABLE,
                               [SourceError("upstream", "failed", True)])
        return SourceBatch(self.source_id, datetime.now(timezone.utc), self.rows, SourceHealth.HEALTHY)


def row(source: str, upstream: str, title: str, url: str) -> NormalizedArticle:
    now = datetime.now(timezone.utc)
    return NormalizedArticle(upstream, title, url, source, source, "media", now, now, "news", summary=title)


def test_service_deduplicates_urls_and_reports_source_failure(tmp_path) -> None:
    first = row("sina", "1", "政策推动新能源发展", "https://example.test/story?utm_source=x")
    duplicate = row("eastmoney", "2", "政策推动新能源发展", "https://example.test/story")
    service = IntelligenceService(
        IntelligenceStore(tmp_path / "intel.db"),
        [FakeSource("sina", [first]), FakeSource("eastmoney", [duplicate]), FakeSource("gdelt", [], failed=True)],
    )

    result = service.search(IntelligenceQuery(limit=20))

    assert len(result.articles) == 1
    assert result.source_health["gdelt"].health is SourceHealth.UNAVAILABLE
    assert result.degraded is True
