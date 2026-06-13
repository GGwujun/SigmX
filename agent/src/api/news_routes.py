"""Financial news HTTP routes — multi-source aggregation.

Mounted by ``agent/api_server.py`` via ``register_news_routes(app, ...)``.

Routes:
- ``GET /news``         — market news from Sina + DuckDuckGo
- ``GET /news/stock/{code}`` — stock-specific news

Data sources (all free, no API key):
1. 新浪财经 (Sina Finance) — primary, real-time A-share wire
2. DuckDuckGo News (ddgs) — secondary, broader coverage
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
# Uses requests library (already a project dependency)

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300  # 5 min

# ---------------------------------------------------------------------------
# Source 1: 新浪财经 (Sina Finance)
# ---------------------------------------------------------------------------

_SINA_ROLL_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2516,2509,2515,1694&k=&num={limit}&page=1"
)

_SINA_SEARCH_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2516,2509,2515,1694&k={keyword}&num={limit}&page=1"
)


def _fetch_sina_news(limit: int = 30, keyword: str = "") -> list[dict[str, Any]]:
    """Fetch real-time financial news from Sina Finance."""
    try:
        import requests as http
        if keyword.strip():
            url = _SINA_SEARCH_URL.format(keyword=keyword.strip(), limit=limit)
        else:
            url = _SINA_ROLL_URL.format(limit=limit)

        resp = http.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Financial keywords to filter non-relevant articles
        _FINANCE_KW = ["股", "基金", "债", "市", "IPO", "上市", "板", "指",
                        "银行", "保险", "券商", "利率", "央行", "美联储",
                        "黄金", "原油", "商品", "期货", "外汇", "比特币",
                        "经济", "GDP", "CPI", "PPI", "PMI", "通胀",
                        "制造业", "消费", "贸易", "关税", "制裁",
                        "房地产", "能源", "半导体", "芯片", "新能源",
                        "汽车", "手机", "互联网", "AI", "人工智能",
                        "财报", "营收", "利润", "分红", "回购",
                        "ETF", "REIT", "QDII", "北向", "南向",
                        "科创", "创业", "主板", "中小板", "北交所",
                        "沪深", "上证", "深证", "恒生", "纳指",
                        "收购", "合并", "重组", "融资", "估值",
                        "A股", "港股", "美股", "日股", "台股",
                        "建议", "评", "目标价", "评级", "看好", "看空", "减持",
                        "监管", "合规", "罚", "立案", "退市",
        ]

        def _is_finance(title: str, intro: str) -> bool:
            text = title + intro
            return any(kw in text for kw in _FINANCE_KW)

        items: list[dict[str, Any]] = []
        for row in data.get("result", {}).get("data", []):
            title = row.get("title", "")
            intro = row.get("intro", "") or row.get("summary", "")
            if not _is_finance(title, intro):
                continue
            ctime = int(row.get("ctime", 0))
            published = datetime.fromtimestamp(ctime, tz=timezone.utc).isoformat() if ctime else ""
            items.append({
                "title": title,
                "url": row.get("url", "") or row.get("wapurl", ""),
                "source": row.get("media_name", "新浪财经"),
                "published": published,
                "snippet": intro[:200],
                "_provider": "sina",
            })
        return items
    except Exception as exc:
        logger.warning("Sina news fetch failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Source 2: DuckDuckGo News
# ---------------------------------------------------------------------------


def _fetch_ddg_news(query: str, max_results: int = 15) -> list[dict[str, Any]]:
    """Fallback: broader news search via DuckDuckGo."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=max_results, timelimit="d"))
            if len(results) < 5:
                results = list(ddgs.news(query, max_results=max_results, timelimit="w"))
        items: list[dict[str, Any]] = []
        for r in results:
            title = r.get("title", "")
            # Keep only Chinese-language results (contains CJK characters)
            if not any('一' <= c <= '鿿' for c in title):
                continue
            items.append({
                "title": title,
                "url": r.get("url", ""),
                "source": r.get("source", "DuckDuckGo"),
                "published": r.get("date", "") or r.get("published", ""),
                "snippet": (r.get("body") or r.get("snippet") or "")[:200],
                "_provider": "ddg",
            })
        return items
    except Exception as exc:
        logger.warning("DDG news fetch failed for %r: %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# Build payload — aggregate sources
# ---------------------------------------------------------------------------


def _build_news_list(keyword: str = "") -> dict[str, Any]:
    """Aggregate news from Sina + DDG, deduplicate by title."""
    # Sina first (fresher, more relevant)
    sina_articles = _fetch_sina_news(limit=25, keyword=keyword)
    seen = {a["title"].strip().lower()[:60] for a in sina_articles}

    # DDG as supplement
    ddg_query = f"A股 {keyword}" if keyword else "A股"
    ddg_articles = _fetch_ddg_news(ddg_query, max_results=15)
    for a in ddg_articles:
        key = a["title"].strip().lower()[:60]
        if key not in seen:
            seen.add(key)
            sina_articles.append(a)

    # Sort by published date (newest first), unknown dates at bottom
    sina_articles.sort(key=lambda a: a.get("published", ""), reverse=True)

    return {
        "articles": sina_articles,
        "query": keyword or "A股",
        "sources": ["新浪财经", "DuckDuckGo"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class NewsArticle(BaseModel):
    title: str
    url: str = ""
    source: str = ""
    published: str = ""
    snippet: str = ""


class NewsListResponse(BaseModel):
    articles: list[dict[str, Any]]
    query: str
    sources: list[str] = []
    updated_at: str


class StockNewsResponse(BaseModel):
    code: str
    name: str
    articles: list[dict[str, Any]]
    updated_at: str


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

AuthDep = Callable[..., Awaitable[Any] | Any]


def register_news_routes(
    app: FastAPI,
    require_auth: AuthDep | None = None,
    require_event_stream_auth: AuthDep | None = None,
) -> None:
    if require_auth is None or require_event_stream_auth is None:
        import sys as _sys
        host = _sys.modules.get("api_server") or _sys.modules.get("agent.api_server")
        if host is None:
            raise RuntimeError("register_news_routes: api_server not in sys.modules")
        if require_auth is None:
            require_auth = host.require_auth
        if require_event_stream_auth is None:
            require_event_stream_auth = host.require_event_stream_auth

    @app.get("/news", response_model=NewsListResponse, dependencies=[Depends(require_auth)])
    async def list_news(
        request: Request,
        q: str = Query("", max_length=100),
        limit: int = Query(30, ge=5, le=60),
    ) -> dict[str, Any]:
        cache_key = f"news:{q}:{limit}"
        now = time.time()
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and (now - cached.get("_ts", 0)) < _CACHE_TTL:
                return {k: v for k, v in cached.items() if not k.startswith("_")}

        import asyncio
        loop = asyncio.get_event_loop()
        payload = await loop.run_in_executor(None, _build_news_list, q if q else "")
        payload["articles"] = payload["articles"][:limit]

        with _CACHE_LOCK:
            _CACHE[cache_key] = {**payload, "_ts": time.time()}

        return payload

    _STOCK_RE = __import__("re").compile(r"^\d{6}\.(SZ|SH)$")

    @app.get("/news/stock/{code}", response_model=StockNewsResponse, dependencies=[Depends(require_auth)])
    async def stock_news(code: str, request: Request) -> dict[str, Any]:
        code = code.strip().upper()
        if not _STOCK_RE.match(code):
            raise HTTPException(status_code=400, detail="Invalid code (e.g. 000001.SZ)")

        from src.api.position_routes import _get_stock_name
        name = _get_stock_name(code)

        cache_key = f"news_stock:{code}"
        now = time.time()
        with _CACHE_LOCK:
            cached = _CACHE.get(cache_key)
            if cached and (now - cached.get("_ts", 0)) < _CACHE_TTL:
                return {k: v for k, v in cached.items() if not k.startswith("_")}

        # Search both Sina and DDG for this stock
        sina = _fetch_sina_news(limit=10, keyword=name)
        ddg = _fetch_ddg_news(f"{name} 股票 A股", max_results=8)
        seen = {a["title"].strip().lower()[:60] for a in sina}
        for a in ddg:
            if a["title"].strip().lower()[:60] not in seen:
                sina.append(a)
        sina.sort(key=lambda a: a.get("published", ""), reverse=True)

        payload = {
            "code": code,
            "name": name,
            "articles": sina[:20],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        with _CACHE_LOCK:
            _CACHE[cache_key] = {**payload, "_ts": time.time()}

        return payload
