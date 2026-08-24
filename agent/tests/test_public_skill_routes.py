import asyncio
from pathlib import Path
from src.api import public_skill_routes as routes

def test_catalog_is_discovered_from_real_skill_manifests(tmp_path: Path) -> None:
    skill_dir = tmp_path / "dividend-analysis"; skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: dividend-analysis\ndescription: Analyze dividend sustainability.\n---\n# Dividend Analysis\n\nUse stocks.daily_basic.", encoding="utf-8")
    routes._skills_root = tmp_path
    catalog = asyncio.run(routes.public_skills())
    assert catalog.skills[0].slug == "dividend-analysis"
    assert catalog.skills[0].description == "Analyze dividend sustainability."
    detail = asyncio.run(routes.public_skill("dividend-analysis"))
    assert "stocks.daily_basic" in detail.content

def test_catalog_does_not_expose_fake_usage_or_credit_estimates() -> None:
    fields = routes.PublicSkillSummary.model_fields
    assert "uses" not in fields
    assert "data_credits" not in fields
