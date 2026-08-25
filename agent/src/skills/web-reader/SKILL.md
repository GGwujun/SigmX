---
name: web-reader
description: Read web pages, articles, and document links by converting URLs into Markdown text. Use the `read_url` tool directly, without bash. Sends the full URL to the third-party Jina Reader (r.jina.ai).
category: tool
sigmx:
  schema_version: 1
  ownership: official
  execution: instructional
  primary_source: none
  datahub_endpoints:
    []
  fallback_sources:
    []
  markets:
    - LOCAL
  credentials:
    []
  capability_status: instructional
---
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

该 Skill 是本地方法或文档流程，不需要市场数据源。 不要为了填充结果而调用未声明的外部数据接口。

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
# Web Reading

## Purpose

Converts any URL into clean Markdown text, removing ads, navigation, styling, and other distractions. Suitable for:
- Reading API documentation (`tushare`, `OKX`, `yfinance`, and similar)
- Reading technical articles and blogs
- Retrieving research reports and announcements
- Reading GitHub README / Wiki pages

## Usage

**Call the `read_url` tool directly (do not use bash + requests, call the tool directly):**

```
read_url(url="https://tushare.pro/document/2?doc_id=27")
```

Returns JSON:
```json
{
  "status": "ok",
  "title": "Page title",
  "url": "Original URL",
  "content": "Page content in Markdown format",
  "length": 12345
}
```

## Notes

- Content longer than 8000 characters will be truncated, with the total length noted at the end
- Dynamically rendered SPA pages may return only skeleton HTML
- Chinese content is supported normally

## Privacy & freshness

- **Third-party dependency:** `read_url` forwards the full target URL
  (including any query string) to the external Jina Reader service
  (`r.jina.ai`). Do **not** pass URLs containing credentials, tokens, or
  private/internal addresses — they would leave this host.
- **Caching/staleness:** results may be a cached snapshot, not live data.
  When stale, the JSON includes `"cached": true`; pass `no_cache=true` to
  force a fresh fetch (slower — use only when freshness matters).
- **Bash fallback caveat:** if a site blocks the reader (e.g. HTTP 451) a
  manual `bash + requests` fetch is possible, but it **bypasses this
  tool's URL safety guard and the Jina layer** — use sparingly and never
  for internal/authenticated URLs.

## Common Usage

### Read API Documentation
```
read_url(url="https://tushare.pro/document/2?doc_id=27")
```

### Read Technical Articles
```
read_url(url="https://blog.example.com/quantitative-trading-guide")
```

### Retrieve GitHub Project Information
```
read_url(url="https://github.com/PaddlePaddle/PaddleOCR")
```
