"""Public catalog backed by the installed SKILL.md manifests."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

_skills_root = Path(__file__).resolve().parents[1] / "skills"
router = APIRouter(tags=["public-skills"])

class PublicSkillSummary(BaseModel):
    slug: str
    name: str
    description: str
    updated_at: str
    official: bool = True
class PublicSkillDetail(PublicSkillSummary):
    content: str
class PublicSkillCatalog(BaseModel):
    skills: list[PublicSkillSummary]

def _manifest(path: Path) -> PublicSkillDetail | None:
    try: content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError): return None
    front = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    meta = front.group(1) if front else ""
    def value(key: str) -> str:
        match = re.search(rf"^{key}:\s*[\"']?(.*?)[\"']?\s*$", meta, re.MULTILINE)
        return match.group(1).strip() if match else ""
    slug = value("name") or path.parent.name
    description = value("description")
    heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    name = heading.group(1).strip() if heading else slug.replace("-", " ").title()
    updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return PublicSkillDetail(slug=slug, name=name, description=description, updated_at=updated, content=content)

@router.get("/api/public/skills", response_model=PublicSkillCatalog)
async def public_skills() -> PublicSkillCatalog:
    skills = [item for path in sorted(_skills_root.glob("*/SKILL.md")) if (item := _manifest(path))]
    return PublicSkillCatalog(skills=[PublicSkillSummary(**item.model_dump(exclude={"content"})) for item in skills])

@router.get("/api/public/skills/{slug}", response_model=PublicSkillDetail)
async def public_skill(slug: str) -> PublicSkillDetail:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug): raise HTTPException(status_code=404, detail="Skill 不存在")
    item = _manifest(_skills_root / slug / "SKILL.md")
    if item is None: raise HTTPException(status_code=404, detail="Skill 不存在")
    return item

def register_public_skill_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/public/skills" for route in app.routes): app.include_router(router)
    return router
