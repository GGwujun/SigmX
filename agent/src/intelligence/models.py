from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


SourceTier = Literal["official", "licensed", "media", "search"]


@dataclass
class NormalizedArticle:
    upstream_id: str
    title: str
    url: str
    source_id: str
    source_name: str
    source_tier: SourceTier
    published_at: datetime
    fetched_at: datetime
    content_type: str
    summary: str = ""
    market: str = "GLOBAL"
    language: str = "zh"
    region: str = ""
    content_policy: str = "metadata"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class EventEvidence:
    article_id: str
    is_key: bool = False
    strength: float = 1.0


@dataclass
class GlobalEvent:
    title: str
    summary: str
    event_type: str
    status: str
    first_seen_at: datetime
    updated_at: datetime
    importance: float = 0.0
    confidence: float = 0.0
    region: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass(frozen=True)
class ArticleWriteResult:
    inserted: int
    updated: int
    items: list[NormalizedArticle]


@dataclass(frozen=True)
class ArticleSearchResult:
    items: list[NormalizedArticle]
    total: int


@dataclass(frozen=True)
class EventEvidenceView:
    article: NormalizedArticle
    is_key: bool
    strength: float


@dataclass(frozen=True)
class EventView:
    event: GlobalEvent
    evidence: list[EventEvidenceView]
