from __future__ import annotations

from src.intelligence.events import EventClusterer
from src.intelligence.models import EventEvidence, EventSearchResult, EventView, GlobalEvent, NormalizedArticle
from src.intelligence.store import IntelligenceStore


def _event_type(title: str, sources: set[str] | None = None) -> str:
    if sources and sources & {"federal_reserve", "ecb", "pbc", "imf", "world_bank"}:
        return "macro_policy"
    value = title.casefold()
    rules = (
        (("央行", "美联储", "利率", "通胀", "gdp", "fed"), "macro_policy"),
        (("战争", "制裁", "冲突", "导弹", "停火"), "geopolitical"),
        (("台风", "地震", "洪水", "火山"), "disaster"),
        (("原油", "天然气", "黄金", "铜价"), "energy_commodity"),
        (("芯片", "ai", "人工智能", "科技"), "technology"),
    )
    return next((kind for words, kind in rules if any(word in value for word in words)), "company")


class GlobalEventService:
    def __init__(self, store: IntelligenceStore, clusterer: EventClusterer | None = None) -> None:
        self.store = store
        self.clusterer = clusterer or EventClusterer()

    def refresh(self, articles: list[NormalizedArticle]) -> list[GlobalEvent]:
        by_id = {article.id or article.upstream_id: article for article in articles}
        created: list[GlobalEvent] = []
        for candidate in self.clusterer.cluster(articles):
            supporting = [by_id[item_id] for item_id in candidate.article_ids if item_id in by_id]
            if len({item.source_id for item in supporting}) < 2 and not any(item.source_tier == "official" for item in supporting):
                continue
            if all(item.source_tier == "search" for item in supporting):
                continue
            evidence = [EventEvidence(article_id=by_id[item_id].id) for item_id in candidate.article_ids if item_id in by_id and by_id[item_id].id]
            if not evidence:
                continue
            times = [by_id[item_id].published_at for item_id in candidate.article_ids if item_id in by_id]
            event = GlobalEvent(
                title=candidate.title, summary=candidate.title,
                event_type=_event_type(candidate.title, {item.source_id for item in supporting}), status="active",
                first_seen_at=min(times), updated_at=max(times), importance=min(1.0, 0.35 + 0.15 * len(evidence)),
                confidence=candidate.confidence,
            )
            created.append(self.store.upsert_event(event, evidence))
        return created

    def list(self, *, event_type: str = "", status: str = "active", limit: int = 30, offset: int = 0) -> EventSearchResult:
        return self.store.list_events(event_type=event_type, status=status, limit=limit, offset=offset)

    def get(self, event_id: str) -> EventView:
        return self.store.get_event(event_id)
