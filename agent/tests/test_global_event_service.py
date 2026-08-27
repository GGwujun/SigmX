from datetime import datetime, timezone

from src.intelligence.event_service import GlobalEventService
from src.intelligence.models import NormalizedArticle
from src.intelligence.store import IntelligenceStore


def test_refresh_persists_traceable_event_and_returns_detail(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    store = IntelligenceStore(tmp_path / "intel.db")
    articles = store.upsert_articles([
        NormalizedArticle("1", "美联储宣布降息 全球市场上涨", "https://a.test/1", "a", "A", "media", now, now, "news"),
        NormalizedArticle("2", "美联储宣布降息 全球股市上涨", "https://b.test/2", "b", "B", "media", now, now, "news"),
    ]).items

    service = GlobalEventService(store)
    created = service.refresh(articles)
    detail = service.get(created[0].id)

    assert created[0].event_type == "macro_policy"
    assert len(detail.evidence) == 2
