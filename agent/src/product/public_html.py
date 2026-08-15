"""Route-specific semantic HTML for the public acquisition funnel."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote


_EXACT = {"/", "/pricing", "/product/data-hub", "/product/desktop", "/download"}
_PREFIXES = ("/query/", "/stock/", "/fund/", "/research/", "/docs/data-hub")


def is_public_html_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in _EXACT or any(normalized.startswith(prefix) for prefix in _PREFIXES)


@dataclass(frozen=True)
class PageDescriptor:
    title: str
    heading: str
    description: str


def _descriptor(path: str) -> PageDescriptor:
    decoded = unquote(path)
    tail = decoded.rstrip("/").split("/", 2)[-1]
    if decoded == "/":
        return PageDescriptor("SigmX｜AI 投研与金融数据平台", "发现机会，完成可验证的专业研究", "自然语言选股、Financial Harness Desktop 与独立 Data Hub。")
    if decoded == "/pricing":
        return PageDescriptor("SigmX 个人套餐与价格", "选择适合你的个人套餐", "Free、Desktop Pro、Data Developer 与 Pro Bundle，权益和积分透明计量。")
    if decoded == "/product/desktop":
        return PageDescriptor("SigmX Desktop｜Financial Harness", "面向个人研究者的 Financial Harness", "本地优先的 Agent、数据、工具、上下文、治理和可观测运行环境。")
    if decoded == "/product/data-hub":
        return PageDescriptor("SigmX Data Hub｜金融数据 API", "标准化金融数据服务", "面向 Desktop 与个人量化开发者的 REST API、Python SDK 和 CLI。")
    if decoded == "/download":
        return PageDescriptor("下载 SigmX Desktop", "下载 SigmX Financial Harness", "安装本地优先的 AI 投研工作台，并按需连接个人云账户。")
    if decoded.startswith("/stock/"):
        return PageDescriptor(f"{tail} 个股研究｜SigmX", "SigmX 个股研究", f"查看 {tail} 的延迟行情、关键指标、事件和 AI 简析。")
    if decoded.startswith("/fund/"):
        return PageDescriptor(f"{tail} 基金研究｜SigmX", "SigmX ETF / LOF 研究", f"查看 {tail} 的基础信息与折溢价概览。")
    if decoded.startswith("/query/"):
        return PageDescriptor("自然语言选股结果｜SigmX", "自然语言选股结果", f"查询：{tail}。登录后可保存，并在 Desktop 继续研究。")
    if decoded.startswith("/research/"):
        return PageDescriptor(f"研究快照 {tail}｜SigmX", "公开研究快照", "用户主动发布的脱敏研究摘要，可撤销且不包含本地私有报告。")
    return PageDescriptor("SigmX Data Hub 文档", "Data Hub 开发者文档", "查看 REST API、Python SDK、CLI、接口权限与 Data Credit 计费规则。")


def render_public_html(index_html: str, path: str, site_url: str) -> str:
    if not is_public_html_path(path):
        raise ValueError("path is not an allowed public HTML route")
    descriptor = _descriptor(path)
    title = html.escape(descriptor.title)
    heading = html.escape(descriptor.heading)
    description = html.escape(descriptor.description)
    canonical = f"{site_url.rstrip('/')}{quote(unquote(path), safe='/:.-_')}"
    document = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", index_html, count=1, flags=re.S)
    document = re.sub(
        r'<meta\s+name=["\']description["\']\s+content=["\'].*?["\']\s*/?>',
        f'<meta name="description" content="{description}" />',
        document,
        count=1,
        flags=re.S,
    )
    structured = json.dumps(
        {"@context": "https://schema.org", "@type": "WebPage", "name": descriptor.title, "description": descriptor.description, "url": canonical},
        ensure_ascii=False,
    ).replace("<", "\\u003c")
    metadata = (
        f'<link rel="canonical" href="{html.escape(canonical)}" />'
        f'<meta property="og:title" content="{title}" />'
        f'<meta property="og:description" content="{description}" />'
        f'<meta property="og:url" content="{html.escape(canonical)}" />'
        f'<script type="application/ld+json">{structured}</script>'
    )
    document = document.replace("</head>", f"{metadata}</head>", 1)
    fallback = (
        '<div id="root"><main data-sigmx-server-rendered="true">'
        f"<h1>{heading}</h1><p>{description}</p>"
        '<nav><a href="/pricing">套餐与价格</a> <a href="/product/desktop">Desktop</a> '
        '<a href="/product/data-hub">Data Hub</a></nav></main></div>'
    )
    return document.replace('<div id="root"></div>', fallback, 1)
