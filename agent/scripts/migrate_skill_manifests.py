"""Idempotently migrate installed Skills to the SigmX data policy schema."""

from __future__ import annotations

import re
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.product.skill_catalog_zh import SKILL_NAMES_ZH
from src.skill_runtime.migration_registry import policy_for_slug


ROOT = Path(__file__).resolve().parents[1] / "src" / "skills"
ADAPTED = {
    "announcement-search", "news-search", "report-search",
    *{f"hithink-{name}" for name in (
        "astock-selector", "basicinfo-query", "business-query", "cb-selector",
        "etf-selector", "event-query", "finance-query", "fund-query", "fund-selector",
        "fundcompany-selector", "fundmanager-selector", "futures-query",
        "futures-selector", "hkstock-selector", "industry-query", "insresearch-query",
        "macro-query", "management-query", "market-query", "sector-selector",
        "usstock-selector", "zhishu-query",
    )},
}


def _yaml_list(values: tuple[str, ...]) -> list[str]:
    if not values:
        return ["    []"]
    return [f"    - {value}" for value in values]


def _policy_block(slug: str) -> str:
    policy = policy_for_slug(slug)
    if policy is None:
        raise RuntimeError(f"no migration policy for {slug}")
    lines = [
        "sigmx:",
        f"  schema_version: {policy.schema_version}",
        f"  ownership: {policy.ownership}",
        f"  execution: {policy.execution}",
        f"  primary_source: {policy.primary_source}",
        "  datahub_endpoints:",
        *_yaml_list(policy.datahub_endpoints),
        "  fallback_sources:",
        *_yaml_list(policy.fallback_sources),
        "  markets:",
        *_yaml_list(policy.markets),
        "  credentials:",
        *_yaml_list(policy.credentials),
        f"  capability_status: {policy.capability_status}",
    ]
    return "\n".join(lines)


def _replace_policy(content: str, slug: str) -> str:
    front = re.match(r"^(---\s*\r?\n)(.*?)(\r?\n---)", content, re.DOTALL)
    if not front:
        raise RuntimeError(f"missing front matter: {slug}")
    metadata = re.sub(r"\nsigmx:\n(?: {2}.*(?:\n|$)| {4}.*(?:\n|$))*", "\n", front.group(2)).rstrip()
    replacement = f"{front.group(1)}{metadata}\n{_policy_block(slug)}{front.group(3)}"
    return replacement + content[front.end():]


def _adapted_manifest(slug: str, original: str) -> str:
    name = SKILL_NAMES_ZH.get(slug, slug)
    description_match = re.search(r"^description:\s*(.+)$", original, re.MULTILINE)
    description = description_match.group(1).strip().strip('"\'') if description_match else f"使用 SigmX 数据能力完成{name}。"
    policy = policy_for_slug(slug)
    assert policy is not None
    endpoints = "\n".join(f"- `{code}`" for code in policy.datahub_endpoints) or "- 当前 Data Hub 尚无等价全文检索接口"
    fallbacks = "、".join(policy.fallback_sources) or "无"
    capability = policy.datahub_endpoints[0] if policy.datahub_endpoints else "capability_not_supported"
    return f"""---
name: {slug}
description: {description}
{_policy_block(slug)}
---

# {name}

## 定位

这是经过 SigmX 适配的数据研究 Skill。它保留原研究场景与稳定安装标识，但不再默认连接问财服务。

## 数据策略

主数据接口：

{endpoints}

候补数据源：{fallbacks}。候补只在清单允许且能够保持指标口径时启用；结果必须展示实际来源、数据日期和降级原因。

## 执行

通过统一运行时请求数据：

```bash
python -m src.skill_runtime.cli {capability} --params '{{}}'
```

执行前根据用户问题构造结构化参数，不得删除用户条件来制造结果。Data Hub 不支持所需能力且候补源也不能保持同一口径时，返回 `capability_not_supported`。

## 输出要求

- 展示实际数据源和数据日期；
- 解释筛选条件、指标单位与排序方法；
- 区分事实、计算结果和判断；
- 不把空数据解释为不存在候选；
- 结果不构成投资建议。
"""


def _runtime_rule(content: str, slug: str) -> str:
    policy = policy_for_slug(slug)
    assert policy is not None
    content = re.sub(
        r"\n?<!-- sigmx-runtime:start -->.*?<!-- sigmx-runtime:end -->\n?",
        "\n",
        content,
        flags=re.DOTALL,
    )
    if policy.primary_source == "data_hub":
        source_rule = "默认且优先使用 SigmX Data Hub；只在清单声明允许且指标口径一致时使用候补源。"
        command = f"`python -m src.skill_runtime.cli {policy.datahub_endpoints[0]} --params '<JSON>'`"
    elif policy.primary_source == "public_source":
        source_rule = f"当前能力由公共数据源（{', '.join(policy.fallback_sources)}）提供；不得标记为 Data Hub 返回。"
        command = "通过统一路由执行，并在结果中标明公共来源、时间和可用性限制。"
    elif policy.primary_source == "user_source":
        source_rule = "当前能力使用用户自备数据源；只有用户本地配置凭证后才可执行。"
        command = "不得读取、记录或回显用户的完整数据源凭证。"
    else:
        source_rule = "该 Skill 是本地方法或文档流程，不需要市场数据源。"
        command = "不要为了填充结果而调用未声明的外部数据接口。"
    block = f"""
<!-- sigmx-runtime:start -->
## SigmX 数据运行规则（优先级最高）

{source_rule} {command}

本节覆盖下文遗留示例中的数据源优先级、认证变量和直连方式；下文分析方法仍然有效。任何降级结果必须包含实际来源、数据日期和降级原因。数据不可用时返回明确能力错误，不得删除用户条件、静默改变指标口径或把取数失败解释为没有候选。
<!-- sigmx-runtime:end -->
"""
    front = re.match(r"^(---\s*\r?\n.*?\r?\n---)", content, re.DOTALL)
    if not front:
        raise RuntimeError(f"missing front matter after migration: {slug}")
    return content[:front.end()] + "\n" + block.strip() + "\n" + content[front.end():].lstrip("\r\n")


def _sanitize_primary_source(content: str, slug: str) -> str:
    policy = policy_for_slug(slug)
    assert policy is not None
    if policy.primary_source != "data_hub":
        return content
    replacements = {
        "TUSHARE_TOKEN": "SIGMX_DATA_HUB_KEY",
        "[tushare skill](../tushare/SKILL.md)": "SigmX Skill Runtime",
        "tushare 优先 → akshare 兜底": "SigmX Data Hub 优先 → 清单候补源兜底",
        "tushare 接口（首选）": "Data Hub 能力（首选）",
        "tushare 接口": "Data Hub 能力",
        "tushare `": "Data Hub `",
        "tushare ": "Data Hub ",
        "Tushare ": "Data Hub ",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def _wrapper(slug: str) -> str:
    policy = policy_for_slug(slug)
    assert policy is not None
    capability = policy.datahub_endpoints[0] if policy.datahub_endpoints else "capability_not_supported"
    return f'''"""Compatibility entry point for the migrated {slug} Skill."""
from __future__ import annotations
import json
import sys
from src.skill_runtime.cli import main as runtime_main

if __name__ == "__main__":
    params = sys.argv[1] if len(sys.argv) > 1 else "{{}}"
    try:
        json.loads(params)
    except json.JSONDecodeError:
        params = json.dumps({{"query": params}}, ensure_ascii=False)
    raise SystemExit(runtime_main(["{capability}", "--params", params]))
'''


def migrate(root: Path = ROOT) -> None:
    for manifest in sorted(root.glob("*/SKILL.md")):
        slug = manifest.parent.name
        original = manifest.read_text(encoding="utf-8")
        updated = _adapted_manifest(slug, original) if slug in ADAPTED else _replace_policy(original, slug)
        updated = _runtime_rule(updated, slug)
        updated = _sanitize_primary_source(updated, slug)
        manifest.write_bytes(updated.replace("\r\n", "\n").encode("utf-8"))
        if slug in ADAPTED:
            for script in manifest.parent.rglob("*.py"):
                script.write_bytes(_wrapper(slug).encode("utf-8"))
            for reference in manifest.parent.rglob("*.md"):
                if reference == manifest:
                    continue
                content = reference.read_text(encoding="utf-8", errors="ignore")
                if "openapi.iwencai.com" in content or "IWENCAI_API_KEY" in content:
                    reference.write_bytes((
                        "# SigmX 数据接口说明\n\n"
                        "该 Skill 已迁移到统一 SigmX Skill Runtime。实际接口、认证、"
                        "候补源与错误契约以同目录 `SKILL.md` 的 `sigmx` 清单为准。\n"
                    ).encode("utf-8"))


if __name__ == "__main__":
    migrate()
