from datetime import datetime, timedelta, timezone

from src.intelligence.events import EventClusterer
from src.intelligence.models import NormalizedArticle


def make_article(source: str, title: str, hours: int = 0) -> NormalizedArticle:
    now = datetime(2026, 8, 27, 8, tzinfo=timezone.utc) + timedelta(hours=hours)
    return NormalizedArticle(source + title, title, f"https://{source}.test/{hours}", source, source, "media", now, now, "news")


def test_clusterer_requires_multiple_sources_for_high_confidence() -> None:
    rows = [
        make_article("reuters", "美联储宣布降息 全球市场上涨"),
        make_article("ap", "美联储宣布降息 全球股市上涨", 1),
    ]

    candidates = EventClusterer().cluster(rows)

    assert len(candidates) == 1
    assert len(candidates[0].article_ids) == 2
    assert candidates[0].confidence >= 0.7


def test_clusterer_keeps_unrelated_articles_separate() -> None:
    rows = [make_article("a", "台风登陆广东"), make_article("b", "芯片公司发布财报")]
    assert len(EventClusterer().cluster(rows)) == 2
