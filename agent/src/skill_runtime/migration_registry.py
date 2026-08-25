from __future__ import annotations

from .models import SkillDataPolicy


_IWENCAI_DATA_HUB = {
    "hithink-astock-selector": ("stocks.daily_basic", "stocks.financial_snapshot"),
    "hithink-basicinfo-query": ("stocks.metadata",),
    "hithink-business-query": ("stocks.financial_statement",),
    "hithink-cb-selector": ("stocks.metadata", "stocks.daily_basic"),
    "hithink-etf-selector": ("etf.daily", "etf.share_size"),
    "hithink-event-query": ("stocks.unusual", "stocks.block_trade"),
    "hithink-finance-query": ("stocks.financial_statement", "stocks.financial_snapshot"),
    "hithink-fund-query": ("fund.daily",),
    "hithink-fund-selector": ("fund.daily",),
    "hithink-fundcompany-selector": ("fund.daily",),
    "hithink-fundmanager-selector": ("fund.daily",),
    "hithink-futures-query": ("market.overview",),
    "hithink-futures-selector": ("market.overview",),
    "hithink-hkstock-selector": ("market.overview",),
    "hithink-industry-query": ("boards.daily", "boards.members"),
    "hithink-insresearch-query": ("stocks.eps_forecast",),
    "hithink-macro-query": ("market.overview",),
    "hithink-management-query": ("stocks.holder_num",),
    "hithink-market-query": ("stocks.daily", "quotes.realtime"),
    "hithink-sector-selector": ("boards.daily", "boards.members"),
    "hithink-usstock-selector": ("market.overview",),
    "hithink-zhishu-query": ("indices.daily",),
}

_PUBLIC_PRIMARY = {
    "adr-hshare": ("yfinance", "GLOBAL"),
    "akshare": ("akshare", "CN_A"),
    "commodity-analysis": ("akshare", "GLOBAL"),
    "cross-market-strategy": ("yfinance", "GLOBAL"),
    "geopolitical-risk": ("rsshub", "GLOBAL"),
    "global-macro": ("akshare", "GLOBAL"),
    "macro-analysis": ("akshare", "GLOBAL"),
    "mootdx": ("mootdx", "CN_A"),
    "yfinance": ("yfinance", "GLOBAL"),
    "okx-market": ("okx", "CRYPTO"),
    "ccxt": ("ccxt", "CRYPTO"),
    "edgar-sec-filings": ("sec", "US"),
    "news-search": ("rsshub", "GLOBAL"),
    "announcement-search": ("cninfo", "CN_A"),
    "report-search": ("bing", "CN_A"),
    "social-media-intelligence": ("bing", "GLOBAL"),
    "us-etf-flow": ("yfinance", "US"),
}

_IWENCAI_PUBLIC = {
    "hithink-usstock-selector": ("yfinance", "US"),
    "hithink-hkstock-selector": ("yfinance", "HK"),
    "hithink-futures-query": ("akshare", "GLOBAL"),
    "hithink-futures-selector": ("akshare", "GLOBAL"),
    "hithink-macro-query": ("akshare", "GLOBAL"),
}

_NO_SOURCE = {
    "backtest-diagnose", "behavioral-finance", "data-routing", "doc-reader",
    "pine-script", "regulatory-knowledge", "report-generate", "research-goal",
    "shadow-account", "strategy-generate", "trade-journal", "vnpy-export", "web-reader",
}

_USER_PRIMARY = {"tushare": "TUSHARE_TOKEN"}

_THIRD_PARTY_ADAPTERS = {"akshare", "mootdx", "yfinance", "okx-market", "ccxt", "edgar-sec-filings"}

_CRYPTO = {
    "crypto-derivatives", "defi-yield", "liquidation-heatmap", "onchain-analysis",
    "perp-funding-basis", "stablecoin-flow", "token-unlock-treasury",
}

_INSTRUCTIONAL = {
    "behavioral-finance", "doc-reader", "geopolitical-risk", "pine-script",
    "regulatory-knowledge", "report-generate", "research-goal", "shadow-account",
    "social-media-intelligence", "trade-journal", "web-reader",
}

_EXECUTABLE = {
    "announcement-search", "ashare-pre-st-filter", "candlestick", "chanlun",
    "cross-market-strategy", "elliott-wave", "fundamental-filter", "harmonic",
    "hithink-astock-selector", "hithink-basicinfo-query", "hithink-business-query",
    "hithink-cb-selector", "hithink-etf-selector", "hithink-event-query",
    "hithink-finance-query", "hithink-fund-query", "hithink-fund-selector",
    "hithink-fundcompany-selector", "hithink-fundmanager-selector",
    "hithink-futures-query", "hithink-futures-selector", "hithink-hkstock-selector",
    "hithink-industry-query", "hithink-insresearch-query", "hithink-macro-query",
    "hithink-management-query", "hithink-market-query", "hithink-sector-selector",
    "hithink-usstock-selector", "hithink-zhishu-query", "ichimoku", "minute-analysis",
    "multi-factor", "news-search", "okx-market", "pair-trading", "report-search",
    "seasonal", "smc", "technical-basic", "tushare", "vnpy-export", "volatility",
}


def _data_hub_endpoints(slug: str) -> tuple[str, ...]:
    if any(token in slug for token in ("financial", "fundamental", "valuation", "dividend", "credit", "earnings")):
        return ("stocks.financial_statement", "stocks.financial_snapshot")
    if any(token in slug for token in ("etf", "fund-analysis")):
        return ("etf.daily", "fund.daily")
    if any(token in slug for token in ("sector", "industry", "rotation")):
        return ("boards.daily", "boards.members")
    if any(token in slug for token in ("option", "volatility")):
        return ("option_chain", "stocks.daily")
    if any(token in slug for token in ("flow", "sentiment", "event", "corporate")):
        return ("stocks.fund_flow", "stocks.unusual")
    return ("stocks.daily", "stocks.daily_basic")


def policy_for_slug(slug: str) -> SkillDataPolicy | None:
    if slug in _IWENCAI_PUBLIC:
        source, market = _IWENCAI_PUBLIC[slug]
        return SkillDataPolicy(1, "adapted", "executable", "public_source", (), (source,), (market,), (), "partial")
    if slug in _IWENCAI_DATA_HUB:
        return SkillDataPolicy(1, "adapted", "executable", "data_hub", _IWENCAI_DATA_HUB[slug], ("akshare",), ("CN_A",), ("SIGMX_DATA_HUB_BASE_URL", "SIGMX_DATA_HUB_KEY"), "partial")
    if slug in _PUBLIC_PRIMARY:
        source, market = _PUBLIC_PRIMARY[slug]
        ownership = "adapted" if slug in {"news-search", "announcement-search", "report-search"} else "third_party" if slug in _THIRD_PARTY_ADAPTERS else "official"
        execution = "executable" if slug in _EXECUTABLE else "instructional"
        return SkillDataPolicy(1, ownership, execution, "public_source", (), (source,), (market,), (), "partial" if slug in {"news-search", "announcement-search", "report-search"} else "full")
    if slug in _USER_PRIMARY:
        execution = "executable" if slug in _EXECUTABLE else "instructional"
        return SkillDataPolicy(1, "third_party", execution, "user_source", (), (), ("CN_A",), (_USER_PRIMARY[slug],), "full")
    if slug in _CRYPTO:
        return SkillDataPolicy(1, "official", "instructional", "public_source", (), ("okx", "ccxt"), ("CRYPTO",), (), "full")
    if slug in _NO_SOURCE:
        execution = "executable" if slug in _EXECUTABLE else "instructional"
        return SkillDataPolicy(1, "official", execution, "none", (), (), ("LOCAL",), (), "instructional")
    execution = "executable" if slug in _EXECUTABLE else "instructional"
    return SkillDataPolicy(1, "official", execution, "data_hub", _data_hub_endpoints(slug), ("akshare",), ("CN_A",), ("SIGMX_DATA_HUB_BASE_URL", "SIGMX_DATA_HUB_KEY"), "full")
