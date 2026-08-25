"""Public catalog backed by the installed SKILL.md manifests."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
from src.product.skill_catalog_zh import localized_skill_metadata
from src.skill_runtime.manifest import ManifestValidationError, load_skill_manifest

_skills_root = Path(__file__).resolve().parents[1] / "skills"
router = APIRouter(tags=["public-skills"])

class PublicSkillSummary(BaseModel):
    slug: str
    name: str
    description: str
    updated_at: str
    official: bool
    ownership: str
    ownership_label: str
    execution: str
    primary_source: str
    primary_source_label: str
    datahub_endpoints: list[str]
    fallback_sources: list[str]
    markets: list[str]
    credential_required: bool
    capability_status: str
class PublicSkillDetail(PublicSkillSummary):
    content: str
class PublicSkillCatalog(BaseModel):
    skills: list[PublicSkillSummary]

def _manifest(path: Path) -> PublicSkillDetail | None:
    try:
        parsed = load_skill_manifest(path)
    except (OSError, UnicodeError, ManifestValidationError):
        return None
    slug = parsed.slug
    name, description = localized_skill_metadata(slug, slug.replace("-", " ").title(), parsed.description)
    policy = parsed.policy
    updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    ownership_labels = {"official": "SigmX 官方", "adapted": "SigmX 适配", "third_party": "第三方", "community": "社区"}
    source_labels = {"data_hub": "SigmX Data Hub", "public_source": "公共数据源", "user_source": "用户自备数据源", "none": "无需数据源"}
    return PublicSkillDetail(
        slug=slug,
        name=name,
        description=description,
        updated_at=updated,
        official=policy.ownership == "official",
        ownership=policy.ownership,
        ownership_label=ownership_labels[policy.ownership],
        execution=policy.execution,
        primary_source=policy.primary_source,
        primary_source_label=source_labels[policy.primary_source],
        datahub_endpoints=list(policy.datahub_endpoints),
        fallback_sources=list(policy.fallback_sources),
        markets=list(policy.markets),
        credential_required=policy.credential_required,
        capability_status=policy.capability_status,
        content=parsed.content,
    )

@router.get("/api/public/skills", response_model=PublicSkillCatalog)
async def public_skills() -> PublicSkillCatalog:
    skills = [item for path in sorted(_skills_root.glob("*/SKILL.md")) if (item := _manifest(path))]
    return PublicSkillCatalog(skills=[PublicSkillSummary(**item.model_dump(exclude={"content"})) for item in skills])

@router.get("/api/public/skills/{slug}", response_model=PublicSkillDetail)
async def public_skill(slug: str) -> PublicSkillDetail:
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug): raise HTTPException(status_code=404, detail="Skill 不存在")
    item = _manifest(_skills_root / slug / "SKILL.md")
    if item is None: raise HTTPException(status_code=404, detail="Skill 不存在")
    return item

def register_public_skill_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/public/skills" for route in app.routes): app.include_router(router)
    return router
