from __future__ import annotations

from datetime import datetime, timezone

from src.intelligence.models import EventEvidence, GlobalEvent, NormalizedArticle
from src.intelligence.store import IntelligenceStore


def article(*, upstream_id: str = "a-1", title: str = "央行发布政策") -> NormalizedArticle:
    return NormalizedArticle(
        upstream_id=upstream_id,
        title=title,
        url=f"https://example.test/{upstream_id}",
        source_id="pbc",
        source_name="中国人民银行",
        source_tier="official",
        published_at=datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 8, 27, 2, 1, tzinfo=timezone.utc),
        content_type="policy",
        summary="政策摘要",
        market="CN",
    )


def test_article_upsert_is_idempotent_and_searchable(tmp_path) -> None:
    store = IntelligenceStore(tmp_path / "intel.db")

    first = store.upsert_articles([article()])
    second = store.upsert_articles([article(title="央行发布政策（更新）")])
    result = store.search_articles(query="央行", limit=20, offset=0)

    assert first.inserted == 1
    assert second.updated == 1
    assert result.total == 1
    assert result.items[0].title == "央行发布政策（更新）"


def test_event_requires_traceable_evidence_and_keeps_versions(tmp_path) -> None:
    store = IntelligenceStore(tmp_path / "intel.db")
    stored = store.upsert_articles([article()]).items[0]
    event = GlobalEvent(
        title="中国货币政策更新",
        summary="央行公布新的政策安排",
        event_type="macro_policy",
        status="active",
        importance=0.8,
        confidence=0.9,
        first_seen_at=datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 27, 2, 2, tzinfo=timezone.utc),
    )

    created = store.upsert_event(event, [EventEvidence(article_id=stored.id, is_key=True)])
    event.summary = "央行公布新的政策安排，市场关注流动性影响"
    updated = store.upsert_event(event, [EventEvidence(article_id=stored.id, is_key=True)])

    assert created.id == updated.id
    assert store.get_event(created.id).evidence[0].article.id == stored.id
    assert len(store.list_event_versions(created.id)) == 2


def test_event_without_evidence_is_rejected(tmp_path) -> None:
    store = IntelligenceStore(tmp_path / "intel.db")
    event = GlobalEvent(
        title="无来源事件",
        summary="不可公开",
        event_type="world",
        status="active",
        first_seen_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    try:
        store.upsert_event(event, [])
    except ValueError as exc:
        assert "evidence" in str(exc)
    else:
        raise AssertionError("event without evidence must be rejected")


def test_events_can_be_filtered_and_ordered_by_importance(tmp_path) -> None:
    store = IntelligenceStore(tmp_path / "intel.db")
    stored = store.upsert_articles([article()]).items[0]
    for title, kind, importance in (("低影响", "company", 0.2), ("高影响", "geopolitical", 0.9)):
        store.upsert_event(GlobalEvent(
            title=title, summary=title, event_type=kind, status="active",
            importance=importance, confidence=0.8,
            first_seen_at=datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 27, 2, 2, tzinfo=timezone.utc),
        ), [EventEvidence(article_id=stored.id)])

    all_events = store.list_events(limit=20, offset=0)
    filtered = store.list_events(event_type="company", limit=20, offset=0)

    assert [item.event.title for item in all_events.items] == ["高影响", "低影响"]
    assert filtered.total == 1
    assert filtered.items[0].event.title == "低影响"
