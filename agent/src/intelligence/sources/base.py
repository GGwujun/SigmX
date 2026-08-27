from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.intelligence.models import NormalizedArticle


class SourceHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class SourceError:
    code: str
    message: str
    retryable: bool


@dataclass
class SourceBatch:
    source_id: str
    fetched_at: datetime
    articles: list[NormalizedArticle]
    health: SourceHealth
    errors: list[SourceError] = field(default_factory=list)
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        if any(article.source_id != self.source_id for article in self.articles):
            raise ValueError("article source_id does not match batch source_id")


class IntelligenceSourceAdapter(ABC):
    source_id: str
    source_name: str

    @abstractmethod
    def fetch(self, *, query: str = "", cursor: str | None = None, limit: int = 30) -> SourceBatch:
        """Fetch and normalize one source without fabricating fallback rows."""
