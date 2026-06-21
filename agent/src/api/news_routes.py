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


def _fetch_wallstreetcn(limit: int = 30, keyword: str = "") -> list[dict[str, Any]]:
    """Fetch financial news from RSSHub 华尔街见闻 (only working RSSHub route on Aliyun)."""
    try:
        import os
        import requests as http
        import xml.etree.ElementTree as ET
        from bs4 import BeautifulSoup
        base = os.getenv("RSSHUB_URL", "http://rsshub:1200").rstrip("/")
        resp = http.get(f"{base}/wallstreetcn/news/global", timeout=10)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        items: list[dict[str, Any]] = []
        for it in root.findall(".//item")[:limit]:
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            # Parse HTML in description to make it readable
            desc_raw = (it.findtext("description") or "").strip()
            soup = BeautifulSoup(desc_raw, "html.parser")
            desc = soup.get_text(separator=" ", strip=True)[:500]  # 更长内容 + 解析HTML
            pub = (it.findtext("pubDate") or "").strip()
            if keyword and keyword not in title:
                continue
            items.append({
                "title": title,
                "url": link,
                "source": "华尔街见闻",
                "published": pub,
                "snippet": desc,
                "_provider": "wscn",
            })
        return items
    except Exception as exc:
        logger.warning("Wallstreetcn fetch failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Source 2: DuckDuckGo News
# ---------------------------------------------------------------------------


def _fetch_bing_news(query: str, max_results: int = 15) -> list[dict[str, Any]]:
    """Fallback: broader news search via Bing (works on Aliyun, unlike DDG)."""
    try:
        import requests as http
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 Chrome/120.0", "Accept-Language": "zh-CN,zh;q=0.9"}
        resp = http.get("https://cn.bing.com/search", params={"q": query, "count": max_results, "setlang": "zh-CN"},
                        headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict[str, Any]] = []
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if not a or not a.get("href"):
                continue
            title = a.get_text(strip=True)
            snippet = ""
            snip = li.select_one(".b_caption p") or li.select_one("p")
            if snip:
                snippet = snip.get_text(strip=True)
            items.append({
                "title": title, "url": a["href"], "source": "Bing",
                "published": "", "snippet": snippet[:200], "_provider": "bing",
            })
            if len(items) >= max_results:
                break
        return items
    except Exception as exc:
        logger.warning("Bing fetch failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Build payload — aggregate sources
# ---------------------------------------------------------------------------


def _build_news_list(keyword: str = "") -> dict[str, Any]:
    """Aggregate news from RSSHub + Bing, deduplicate by title."""
    # RSSHub wallstreetcn first (fresher, more relevant)
    rss_articles = _fetch_wallstreetcn(limit=25, keyword=keyword)
    seen = {a["title"].strip().lower()[:60] for a in rss_articles}

    # DDG as supplement
    bing_query = f"A股 {keyword}" if keyword else "A股"
    bing_articles = _fetch_bing_news(bing_query, max_results=15)
    for a in bing_articles:
        key = a["title"].strip().lower()[:60]
        if key not in seen:
            seen.add(key)
            rss_articles.append(a)

    # Sort by published date (newest first), unknown dates at bottom
    rss_articles.sort(key=lambda a: a.get("published", ""), reverse=True)

    return {
        "articles": rss_articles,
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
        sina = _fetch_wallstreetcn(limit=10, keyword=name)
        ddg = _fetch_bing_news(f"{name} 股票 A股", max_results=8)
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
