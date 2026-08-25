import asyncio
import re
from pathlib import Path
from src.api import public_skill_routes as routes

def test_catalog_is_discovered_from_real_skill_manifests(tmp_path: Path) -> None:
    skill_dir = tmp_path / "dividend-analysis"; skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("""---
name: dividend-analysis
description: Analyze dividend sustainability.
sigmx:
  schema_version: 1
  ownership: official
  execution: executable
  primary_source: data_hub
  datahub_endpoints: [stocks.daily_basic, stocks.dividends]
  fallback_sources: [akshare]
  markets: [CN_A]
  credentials: [SIGMX_DATA_HUB_KEY]
  capability_status: full
---
# Dividend Analysis

Use stocks.daily_basic.
""", encoding="utf-8")
    routes._skills_root = tmp_path
    catalog = asyncio.run(routes.public_skills())
    assert catalog.skills[0].slug == "dividend-analysis"
    assert catalog.skills[0].name == "股息质量与分红持续性分析"
    assert "数据获取" in catalog.skills[0].description
    assert catalog.skills[0].ownership == "official"
    assert catalog.skills[0].ownership_label == "SigmX 官方"
    assert catalog.skills[0].primary_source == "data_hub"
    assert catalog.skills[0].primary_source_label == "SigmX Data Hub"
    assert catalog.skills[0].datahub_endpoints == ["stocks.daily_basic", "stocks.dividends"]
    assert catalog.skills[0].fallback_sources == ["akshare"]
    assert catalog.skills[0].credential_required is True
    detail = asyncio.run(routes.public_skill("dividend-analysis"))
    assert "stocks.daily_basic" in detail.content

def test_catalog_does_not_expose_fake_usage_or_credit_estimates() -> None:
    fields = routes.PublicSkillSummary.model_fields
    assert "uses" not in fields
    assert "data_credits" not in fields


def test_published_catalog_uses_chinese_names_and_descriptions() -> None:
    routes._skills_root = Path(__file__).resolve().parents[1] / "src" / "skills"
    catalog = asyncio.run(routes.public_skills())

    assert catalog.skills
    assert all(re.search(r"[\u4e00-\u9fff]", item.name) for item in catalog.skills)
    assert all(re.search(r"[\u4e00-\u9fff]", item.description) for item in catalog.skills)
    assert len({item.name for item in catalog.skills}) == len(catalog.skills)


def test_catalog_truthfully_labels_adapted_and_public_source_skills() -> None:
    routes._skills_root = Path(__file__).resolve().parents[1] / "src" / "skills"
    catalog = asyncio.run(routes.public_skills())
    by_slug = {item.slug: item for item in catalog.skills}

    assert by_slug["hithink-finance-query"].ownership_label == "SigmX 适配"
    assert by_slug["hithink-finance-query"].capability_status == "partial"
    assert by_slug["akshare"].ownership_label == "第三方"
    assert by_slug["akshare"].primary_source_label == "公共数据源"
    assert by_slug["akshare"].credential_required is False
    assert by_slug["financial-statement"].execution == "instructional"
