"""Tushare 资讯页新闻抓取客户端。

数据源是 tushare 的服务端渲染页面 ``https://tushare.pro/news/{src}``,
覆盖财联社、东方财富、华尔街见闻、第一财经、同花顺、雪球、新浪财经、
金十、金融界九个快讯源(API ``news`` 接口不覆盖雪球和金十)。

页面要求登录态:未登录返回 302 跳登录页。cookie 通过环境变量
``TUSHARE_COOKIE`` 提供;cookie 过期后页面同样 302,抓取会抛错,
由调用方(情报源适配器)标记源不可用。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import unescape
from typing import Any

import requests

CN_TZ = timezone(timedelta(hours=8))

SUPPORTED_SOURCES: dict[str, str] = {
    "cls": "财联社",
    "eastmoney": "东方财富",
    "wallstreetcn": "华尔街见闻",
    "yicai": "第一财经",
    "10jqka": "同花顺",
    "xq": "雪球",
    "sina": "新浪财经",
    "jinshi": "金十数据",
    "jinrongjie": "金融界",
}

# 日期分隔行:<div class="news_day news_item"><img .../>8月28日</div>
# 条目:<div class="news_datetime">16:13</div><div class="news_content">...</div>
_TOKEN_RE = re.compile(
    r'<div class="news_day news_item">(?:<img[^>]*/?>)?\s*(\d{1,2})月(\d{1,2})日</div>'
    r'|<div class="news_datetime">([^<]+)</div>\s*<div class="news_content">(.*?)</div>',
    re.S,
)
_TITLE_RE = re.compile(r"【(.+?)】")
_TAG_RE = re.compile(r"<[^>]+>")


def parse_news_page(html: str, *, limit: int = 50, now: datetime | None = None) -> list[dict[str, Any]]:
    """把 tushare 资讯页 HTML 解析为标准化新闻条目。

    页面中的时间只有时分,日期由上方最近的"X月X日"分隔行确定;首个
    分隔行之前的条目视为当天。跨年时(今天 1 月 1 日而分隔行是
    12 月 31 日)年份回退一年。
    """
    now = now or datetime.now(CN_TZ)
    year = now.year
    day = (now.month, now.day)
    items: list[dict[str, Any]] = []
    for match in _TOKEN_RE.finditer(html):
        if match.group(1):
            day = (int(match.group(1)), int(match.group(2)))
            continue
        time_str = match.group(3).strip()
        content = unescape(_TAG_RE.sub("", match.group(4))).strip()
        if not content:
            continue
        try:
            hour, minute = (int(part) for part in time_str.split(":")[:2])
        except ValueError:
            continue
        item_year = year - 1 if day > (now.month, now.day) else year
        published = datetime(item_year, day[0], day[1], hour, minute, tzinfo=CN_TZ)
        title_match = _TITLE_RE.match(content)
        title = title_match.group(1) if title_match else content[:40]
        items.append({
            "title": title,
            "snippet": content,
            "published": format_datetime(published),
            "url": "",
        })
        if len(items) >= limit:
            break
    return items


def fetch_tushare_news(src: str, *, limit: int = 50, timeout: int = 15) -> list[dict[str, Any]]:
    """抓取指定来源的最新快讯。cookie 缺失或过期时抛异常。"""
    if src not in SUPPORTED_SOURCES:
        raise ValueError(f"不支持的 tushare 资讯源: {src}")
    cookie = os.getenv("TUSHARE_COOKIE", "").strip()
    if not cookie:
        raise RuntimeError("TUSHARE_COOKIE 未配置")
    resp = requests.get(
        f"https://tushare.pro/news/{src}",
        headers={"Cookie": cookie, "User-Agent": "Mozilla/5.0"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"tushare 资讯页返回 {resp.status_code}(cookie 可能已过期)")
    items = parse_news_page(resp.text, limit=limit)
    if not items:
        raise RuntimeError("tushare 资讯页未解析到新闻(cookie 可能已过期)")
    return items
