"""Explainable intent parsing for the anonymous Web discovery entry point."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IntentKind(StrEnum):
    INSTRUMENT = "instrument"
    INSTRUMENT_SEARCH = "instrument_search"
    SCREENER = "screener"
    MARKET_QUESTION = "market_question"
    API_DOCS = "api_docs"
    FUND_SEARCH = "fund_search"


@dataclass(frozen=True)
class QueryIntent:
    kind: IntentKind
    normalized_query: str
    conditions: tuple[dict[str, Any], ...] = ()


_SCREENERS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("低估值", {"field": "pe_ttm", "operator": "between", "value": [0, 20], "label": "市盈率 0-20"}),
    ("高股息", {"field": "dividend_yield", "operator": "gte", "value": 3, "label": "股息率 ≥ 3%"}),
    ("小市值", {"field": "total_market_value", "operator": "sort", "value": "asc", "label": "按总市值升序"}),
)


def parse_query(query: str) -> QueryIntent:
    normalized = " ".join(query.strip().split())
    if not normalized:
        raise ValueError("query is required")
    lowered = normalized.lower()

    if any(token in lowered for token in ("data hub", "datahub", "api", "接口", "sdk")):
        return QueryIntent(IntentKind.API_DOCS, normalized)
    if any(token in lowered for token in ("etf", "lof", "基金", "折溢价")):
        return QueryIntent(IntentKind.FUND_SEARCH, normalized)

    conditions = tuple(condition.copy() for marker, condition in _SCREENERS if marker in normalized)
    if conditions:
        return QueryIntent(IntentKind.SCREENER, normalized, conditions)
    if any(token in normalized for token in ("市场", "上涨家数", "下跌家数", "情绪", "大盘", "行情怎么样")):
        return QueryIntent(IntentKind.MARKET_QUESTION, normalized)
    if re.fullmatch(r"(?:\d{6})(?:\.(?:SH|SZ|BJ))?", normalized, flags=re.IGNORECASE):
        return QueryIntent(IntentKind.INSTRUMENT, normalized.upper())
    return QueryIntent(IntentKind.INSTRUMENT_SEARCH, normalized)
