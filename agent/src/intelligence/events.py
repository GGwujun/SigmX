from __future__ import annotations

from dataclasses import dataclass

from src.intelligence.models import NormalizedArticle


@dataclass(frozen=True)
class EventCandidate:
    title: str
    article_ids: list[str]
    source_ids: list[str]
    confidence: float


def _grams(value: str) -> set[str]:
    compact = "".join(char.casefold() for char in value if char.isalnum())
    return {compact[index:index + 2] for index in range(max(1, len(compact) - 1))}


def _similar(left: str, right: str) -> float:
    a, b = _grams(left), _grams(right)
    return len(a & b) / max(1, min(len(a), len(b)))


class EventClusterer:
    def cluster(self, articles: list[NormalizedArticle]) -> list[EventCandidate]:
        groups: list[list[NormalizedArticle]] = []
        for article in sorted(articles, key=lambda item: item.published_at):
            target = next((group for group in groups if _similar(group[0].title, article.title) >= 0.45), None)
            if target is None:
                groups.append([article])
            else:
                target.append(article)
        candidates: list[EventCandidate] = []
        for group in groups:
            sources = sorted({item.source_id for item in group})
            confidence = min(0.95, 0.45 + 0.25 * max(0, len(sources) - 1))
            candidates.append(EventCandidate(group[0].title, [item.id or item.upstream_id for item in group], sources, confidence))
        return candidates
