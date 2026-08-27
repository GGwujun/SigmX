from __future__ import annotations

from datetime import datetime, timezone

from src.intelligence.sources.base import SourceBatch, SourceError, SourceHealth


def test_source_batch_exposes_failures_without_fake_articles() -> None:
    batch = SourceBatch(
        source_id="gdelt",
        fetched_at=datetime.now(timezone.utc),
        articles=[],
        health=SourceHealth.DEGRADED,
        errors=[SourceError(code="timeout", message="upstream timed out", retryable=True)],
    )

    assert batch.articles == []
    assert batch.health is SourceHealth.DEGRADED
    assert batch.errors[0].retryable is True


def test_source_batch_rejects_articles_from_another_source() -> None:
    from src.intelligence.models import NormalizedArticle

    row = NormalizedArticle(
        upstream_id="1", title="test", url="https://example.test/1",
        source_id="bing", source_name="Bing", source_tier="search",
        published_at=datetime.now(timezone.utc), fetched_at=datetime.now(timezone.utc),
        content_type="news",
    )

    try:
        SourceBatch(
            source_id="sina", fetched_at=datetime.now(timezone.utc), articles=[row],
            health=SourceHealth.HEALTHY,
        )
    except ValueError as exc:
        assert "source_id" in str(exc)
    else:
        raise AssertionError("cross-source article must be rejected")
