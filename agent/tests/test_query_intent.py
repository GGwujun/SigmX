import pytest

from src.product.query_intent import IntentKind, parse_query


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("600519", IntentKind.INSTRUMENT),
        ("贵州茅台", IntentKind.INSTRUMENT_SEARCH),
        ("低估值 高股息 小市值", IntentKind.SCREENER),
        ("今天市场怎么样", IntentKind.MARKET_QUESTION),
        ("上涨家数和市场情绪", IntentKind.MARKET_QUESTION),
        ("Data Hub 股票日线接口怎么调用", IntentKind.API_DOCS),
        ("沪深300 ETF", IntentKind.FUND_SEARCH),
        ("LOF 折溢价", IntentKind.FUND_SEARCH),
    ],
)
def test_parse_query_recognizes_every_public_search_intent(query: str, kind: IntentKind) -> None:
    assert parse_query(query).kind is kind


def test_screener_intent_exposes_structured_explainable_conditions() -> None:
    intent = parse_query("低估值 高股息 小市值")

    assert intent.conditions == (
        {"field": "pe_ttm", "operator": "between", "value": [0, 20], "label": "市盈率 0-20"},
        {"field": "dividend_yield", "operator": "gte", "value": 3, "label": "股息率 ≥ 3%"},
        {"field": "total_market_value", "operator": "sort", "value": "asc", "label": "按总市值升序"},
    )


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="query is required"):
        parse_query("  ")
