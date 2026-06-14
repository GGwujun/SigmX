"""Web search tool: multi-source search with automatic fallback.

Three sources tried in order until one returns results:
  1. **DuckDuckGo** (ddgs) — original; good for English, weak for Chinese A-share.
  2. **Bing China** (cn.bing.com) — strong Chinese support, reachable from mainland.
  3. **Eastmoney** (eastmoney.com) — A-share news specialist; best for stock queries.

Each source returns a normalized list of {title, url, snippet}. The first source
that yields ≥1 result wins; later sources are skipped. If all fail, an error is
returned so the agent can fall back to read_url on known pages.

A query is auto-detected as ``chinese`` when it contains CJK characters — in that
case Bing/Eastmoney are tried before DDG (which often returns nothing for Chinese).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.agent.tools import BaseTool
from src.security.scanner import with_security_warnings

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_TIMEOUT = 15
_CJK_RE = re.compile(r"[一-鿿]")


def _is_chinese(query: str) -> bool:
    return bool(_CJK_RE.search(query or ""))


def _search_ddg(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo via ddgs/duckduckgo_search.

    If an overseas proxy is configured, route DDG through it — the proxy server
    sits overseas and reaches DuckDuckGo freely, avoiding CN access instability.
    """
    # Overseas proxy path (preferred when configured).
    base = os.getenv("OVERSEAS_PROXY_URL", "").strip().rstrip("/")
    if base:
        import requests as _requests
        secret = os.getenv("PROXY_SECRET", "").strip()
        headers = {"X-Proxy-Key": secret} if secret else {}
        try:
            resp = _requests.get(
                f"{base}/search",
                params={"q": query, "max": max_results},
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception:
            pass  # fall through to local DDGS

    # Local DDGS (works when the host can reach DuckDuckGo directly).
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError as exc:
        raise RuntimeError("DuckDuckGo search package not installed") from exc

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]


def _search_bing(query: str, max_results: int) -> list[dict]:
    """Bing China (cn.bing.com) — parse HTML result list."""
    headers = {"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    resp = requests.get(
        "https://cn.bing.com/search",
        params={"q": query, "count": max_results, "setlang": "zh-CN"},
        headers=headers,
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Bing HTTP {resp.status_code}")
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    results: list[dict] = []
    # Bing organic results live in <li class="b_algo"> with an <h2><a> title link
    # and a sibling snippet container.
    for li in soup.select("li.b_algo"):
        a = li.select_one("h2 a")
        if not a or not a.get("href"):
            continue
        title = a.get_text(strip=True)
        url = a["href"]
        snippet = ""
        # snippet is usually in .b_caption p or directly under the li
        snip_node = li.select_one(".b_caption p") or li.select_one("p")
        if snip_node:
            snippet = snip_node.get_text(strip=True)
        if title or url:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _search_eastmoney(query: str, max_results: int) -> list[dict]:
    """Eastmoney search API — A-share news specialist.

    Uses the public search-api-web endpoint (JSONP). Returns cmsArticle news
    results with title, url, and a publish date snippet.
    """
    param = json.dumps({
        "uid": "",
        "keyword": query,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": max_results,
                "preTag": "",
                "postTag": "",
            }
        },
    })
    resp = requests.get(
        "https://search-api-web.eastmoney.com/search/jsonp",
        params={"cb": "jQuery", "param": param},
        headers={"User-Agent": _UA, "Referer": "https://so.eastmoney.com/"},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Eastmoney HTTP {resp.status_code}")

    text = resp.text
    # Strip JSONP wrapper: jQuery...( {...} )
    m = re.search(r"\((\{.*\})\)\s*$", text, re.DOTALL)
    if not m:
        raise RuntimeError("Eastmoney returned non-JSONP response")
    data = json.loads(m.group(1))

    articles = (
        data.get("result", {})
        .get("cmsArticleWebOld", {})
        .get("list")
        or []
    )
    results: list[dict] = []
    for art in articles:
        title = (art.get("title") or "").replace("<em>", "").replace("</em>", "")
        url = art.get("url") or ""
        date = art.get("date") or ""
        content = (art.get("content") or "").replace("<em>", "").replace("</em>", "")
        snippet = content[:200]
        if date:
            snippet = f"[{date}] {snippet}"
        if title or url:
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


class WebSearchTool(BaseTool):
    """Multi-source web search with automatic fallback."""

    name = "web_search"

    @classmethod
    def check_available(cls) -> bool:
        """Available if ddgs/duckduckgo_search is installed (Bing/Eastmoney
        need no extra package — just requests + bs4)."""
        try:
            try:
                import ddgs  # noqa: F401
            except ImportError:
                import duckduckgo_search  # noqa: F401
            return True
        except ImportError:
            return False

    description = (
        "Search the web. Returns top results with title, URL, and snippet. "
        "For Chinese / A-share queries, Bing China and Eastmoney are tried first "
        "(DuckDuckGo is weak for Chinese). Use this to find news or URLs before "
        "reading them with read_url."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {
                "type": "integer",
                "description": "Maximum results per source (default 5, max 10)",
                "default": 5,
            },
        },
        "required": ["query"],
    }
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        """Run a multi-source search with fallback.

        Source order:
          - Chinese query: Eastmoney → Bing → DDG
          - Non-Chinese query: DDG → Bing → Eastmoney
        First source with ≥1 result wins.
        """
        query = kwargs["query"]
        max_results = min(int(kwargs.get("max_results", 5)), 10)

        if _is_chinese(query):
            sources = [
                ("eastmoney", _search_eastmoney),
                ("bing", _search_bing),
                ("ddg", _search_ddg),
            ]
        else:
            sources = [
                ("ddg", _search_ddg),
                ("bing", _search_bing),
                ("eastmoney", _search_eastmoney),
            ]

        errors: list[str] = []
        for name, fn in sources:
            try:
                results = fn(query, max_results)
                if results:
                    payload = {
                        "status": "ok",
                        "query": query,
                        "source": name,
                        "results": results,
                    }
                    payload = with_security_warnings(
                        payload,
                        fields=("results.*.title", "results.*.snippet"),
                    )
                    return json.dumps(payload, ensure_ascii=False)
                errors.append(f"{name}: no results")
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        return json.dumps(
            {
                "status": "error",
                "query": query,
                "error": "all sources failed",
                "details": errors,
            },
            ensure_ascii=False,
        )
