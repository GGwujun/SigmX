"""Web reader tool: fetch a URL as Markdown text.

Two-strategy fetch with automatic fallback:
  1. **Direct fetch** — for China-domestic sites (gov.cn, eastmoney.com,
     nhsa.gov.cn, sina, etc.) where the境外 Jina Reader is unreliable
     (SSL EOF / blocked). Uses ``requests`` + ``BeautifulSoup`` to pull the
     page and extract readable text directly.
  2. **Jina Reader** (r.jina.ai) — the original strategy; kept for foreign
     sites and as a universal fallback.

Strategy selection:
  - A URL whose host matches a known domestic domain set → direct fetch first,
    fall back to Jina on failure.
  - All other URLs → Jina first (preserves prior behavior), fall back to
    direct fetch on failure.
  - ``strategy`` param lets the caller force one: ``auto`` (default),
    ``direct``, or ``jina``.

Never pass credentials/tokens or private addresses to either strategy.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from src.agent.progress import emit_progress
from src.agent.tools import BaseTool
from src.security.scanner import with_security_warnings

logger = logging.getLogger(__name__)

_JINA_PREFIX = "https://r.jina.ai/"
_TIMEOUT = 30
_DIRECT_TIMEOUT = 20
_MAX_LENGTH = 8000
_CACHED_MARKER = "Warning: This is a cached snapshot"

# Domestic domains that should be fetched directly (no need to route through
# the境外 Jina Reader, which is slow / blocked from mainland China).
_DOMESTIC_SUFFIXES = (
    ".cn",
    ".gov.cn",
    ".com.cn",
    ".eastmoney.com",
    ".xueqiu.com",
    ".sina.com.cn",
    "sina.com.cn",
    ".10jqka.com.cn",
    ".finance.sina",
    ".nhsa.gov.cn",
    ".csrc.gov.cn",
    ".sse.com.cn",
    ".szse.cn",
    ".cn-healthc.com",
    ".caixin.com",
    ".cls.cn",
    ".yicai.com",
    ".stcn.com",
    ".cs.com.cn",
    ".ce.cn",
    ".21jingji.com",
    ".guancha.cn",
    ".thepaper.cn",
    ".36kr.com",
    ".tushare.pro",
)

# Common boilerplate tags to strip during direct extraction.
_STRIP_TAGS = (
    "script", "style", "noscript", "iframe", "header", "footer",
    "nav", "aside", "form", "button", "svg",
)


def _url_allowed(url: str) -> tuple[bool, str]:
    """Return whether a URL is safe to fetch (no private/loopback hosts)."""
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return False, "target URL is not allowed"

    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "target URL is not allowed"
    if not parsed.hostname:
        return False, "target URL is not allowed"
    if parsed.username or parsed.password:
        return False, "target URL is not allowed"

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False, "target URL is not allowed"

    ip_host = host.split("%", 1)[0]
    try:
        ip = ipaddress.ip_address(ip_host)
    except ValueError:
        return True, ""

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    ):
        return False, "target URL is not allowed"
    return True, ""


def _is_domestic(url: str) -> bool:
    """Heuristic: does this URL point at a China-domestic site?"""
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return False
    host = host.rstrip(".").lower()
    return any(host == s.lstrip(".") or host.endswith(s) for s in _DOMESTIC_SUFFIXES)


def _direct_fetch(url: str, no_cache: bool = False) -> dict:
    """Fetch a page directly with requests + BeautifulSoup, return reader-style dict.

    Suitable for domestic sites (gov.cn, eastmoney, sina, etc.) where Jina is
    unreachable. Extracts the main readable text + title, strips nav/ads.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=_DIRECT_TIMEOUT, allow_redirects=True)
    if resp.status_code != 200:
        return {
            "status": "error",
            "error": f"direct fetch returned HTTP {resp.status_code}",
        }

    # Respect apparent encoding (Chinese sites often mis-declare); fall back
    # to apparent_encoding when requests' default guess is ascii-only.
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Strip boilerplate before extraction
    for tag_name in _STRIP_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()

    # Prefer semantic main/article containers; fall back to body
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=lambda v: v and v.lower() in {"content", "article", "main", "detail"})
        or soup.find(class_=lambda v: v and any(
            k in str(v).lower() for k in ("content", "article", "main", "detail", "text")
        ))
        or soup.body
        or soup
    )

    text = container.get_text(separator="\n", strip=True) if container else ""
    # Collapse blank lines
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = "\n".join(lines)

    if len(text) > _MAX_LENGTH:
        text = text[:_MAX_LENGTH] + f"\n\n... (truncated, total {len(text)} chars)"

    return {
        "status": "ok",
        "title": title,
        "url": url,
        "content": text,
        "length": len(text),
        "strategy": "direct",
    }


def _jina_fetch(url: str, no_cache: bool = False) -> dict:
    """Original strategy: fetch via the Jina Reader service (r.jina.ai)."""
    headers = {"Accept": "text/markdown"}
    if no_cache:
        headers["x-no-cache"] = "true"
    resp = requests.get(
        f"{_JINA_PREFIX}{url}",
        headers=headers,
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        logger.warning("read_url jina HTTP %s: %s", resp.status_code, resp.text[:500])
        return {
            "status": "error",
            "error": f"remote reader returned HTTP {resp.status_code}: {resp.text[:500]}",
        }

    text = resp.text
    title = ""
    for line in text.split("\n"):
        if line.startswith("Title:"):
            title = line[6:].strip()
            break

    if len(text) > _MAX_LENGTH:
        text = text[:_MAX_LENGTH] + f"\n\n... (truncated, total {len(resp.text)} chars)"

    result = {
        "status": "ok",
        "title": title,
        "url": url,
        "content": text,
        "length": len(resp.text),
        "strategy": "jina",
    }
    if _CACHED_MARKER in resp.text:
        result["cached"] = True
    return result


# ---------------------------------------------------------------------------
# Overseas proxy strategy (when the main service runs in CN, route foreign-site
# reads through a lightweight proxy on an overseas server — it reaches
# Yahoo/Reuters/Jina fast, avoiding CN->overseas slowness/blocks).
# ---------------------------------------------------------------------------

def _overseas_proxy_url() -> str:
    return os.getenv("OVERSEAS_PROXY_URL", "").strip().rstrip("/")


def _proxy_fetch(url: str, no_cache: bool = False) -> dict:
    """Fetch via the overseas proxy (which uses Jina/raw from a fast vantage)."""
    base = _overseas_proxy_url()
    if not base:
        return {"status": "error", "error": "OVERSEAS_PROXY_URL not configured"}
    secret = os.getenv("PROXY_SECRET", "").strip()
    headers = {"X-Proxy-Key": secret} if secret else {}
    try:
        resp = requests.get(
            f"{base}/fetch",
            params={"url": url, "strategy": "jina"},
            headers=headers,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        return {"status": "error", "error": f"proxy request failed: {exc}"}
    if resp.status_code != 200:
        return {"status": "error", "error": f"proxy HTTP {resp.status_code}: {resp.text[:200]}"}
    data = resp.json()
    if data.get("status") != "ok":
        return data
    return {
        "status": "ok",
        "title": data.get("title", ""),
        "url": url,
        "content": data.get("content", ""),
        "length": data.get("length", 0),
        "strategy": "proxy",
    }


def read_url(url: str, no_cache: bool = False, strategy: str = "auto") -> str:
    """Fetch web page content as Markdown text.

    Strategies with automatic fallback:
      - ``auto`` (default): domestic sites → direct first (proxy/jina fallback);
        foreign sites → overseas proxy first (jina/direct fallback).
        foreign sites → Jina first, direct fallback.
      - ``direct``: force direct fetch only.
      - ``jina``: force Jina Reader only.

    Never pass credentials/tokens or private addresses.

    Args:
        url: Target URL.
        no_cache: When true, ask the reader for a fresh (uncached) fetch.
        strategy: Fetch strategy: ``auto`` | ``direct`` | ``jina``.

    Returns:
        JSON result with title, content, url, strategy.
    """
    target_url = url.strip()
    allowed, error = _url_allowed(target_url)
    if not allowed:
        return json.dumps({"status": "error", "error": error}, ensure_ascii=False)

    strategy = (strategy or "auto").lower()
    if strategy not in {"auto", "direct", "jina"}:
        strategy = "auto"

    # Resolve strategy order. If an overseas proxy is configured, foreign sites
    # go through it first (it reaches Yahoo/Reuters/Jina fast from overseas).
    has_proxy = bool(_overseas_proxy_url())
    if strategy == "direct":
        order = ["direct"]
    elif strategy == "jina":
        order = ["jina"]
    else:  # auto
        if _is_domestic(target_url):
            order = ["direct", "jina"]
        elif has_proxy:
            order = ["proxy", "jina", "direct"]
        else:
            order = ["jina", "direct"]

    emit_progress(
        "fetching",
        message=f"GET {target_url[:60]}{'…' if len(target_url) > 60 else ''} ({order[0]})",
    )

    errors: list[str] = []
    for idx, strat in enumerate(order):
        try:
            emit_progress("parsing", message=f"extracting via {strat}")
            if strat == "direct":
                result = _direct_fetch(target_url, no_cache)
            elif strat == "proxy":
                result = _proxy_fetch(target_url, no_cache)
            else:
                result = _jina_fetch(target_url, no_cache)
            if result.get("status") == "ok":
                result = with_security_warnings(result, fields=("content",))
                return json.dumps(result, ensure_ascii=False)
            # Strategy returned an error envelope — record and try next
            errors.append(f"{strat}: {result.get('error', 'unknown')}")
            logger.info("read_url %s failed (%s), trying next strategy", target_url, errors[-1])
        except requests.Timeout:
            errors.append(f"{strat}: timed out ({_TIMEOUT}s)")
            logger.info("read_url %s %s timed out", target_url, strat)
        except Exception as exc:
            errors.append(f"{strat}: {exc}")
            logger.warning("read_url %s via %s failed: %s", target_url, strat, exc)

    # All strategies exhausted
    return json.dumps(
        {"status": "error", "error": "all strategies failed", "details": errors},
        ensure_ascii=False,
    )


class WebReaderTool(BaseTool):
    """Web reader tool with domestic-direct + Jina fallback."""

    name = "read_url"
    description = (
        "Fetch web page content: provide a URL and receive the page as Markdown text. "
        "China-domestic sites (gov.cn, eastmoney.com, sina, etc.) are fetched directly; "
        "foreign sites use the Jina Reader, with automatic fallback between the two."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the web page to read"},
            "no_cache": {
                "type": "boolean",
                "description": "Request a fresh (uncached) fetch",
                "default": False,
            },
            "strategy": {
                "type": "string",
                "enum": ["auto", "direct", "jina"],
                "description": "Fetch strategy: auto (default), direct (China-domestic), or jina (foreign).",
                "default": "auto",
            },
        },
        "required": ["url"],
    }
    repeatable = True

    def execute(self, **kwargs) -> str:
        """Fetch web page."""
        return read_url(
            kwargs["url"],
            no_cache=bool(kwargs.get("no_cache", False)),
            strategy=str(kwargs.get("strategy", "auto")),
        )
