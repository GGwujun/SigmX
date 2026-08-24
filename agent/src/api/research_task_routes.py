"""Authenticated Web research task and result APIs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.product.research_tasks import InvalidResearchConstraint, ResearchTaskService


class ResearchConstraintRequest(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    op: str = Field(min_length=1, max_length=4)
    value: float


class CreateResearchTaskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    template_id: str | None = Field(default=None, max_length=64)
    scope: dict[str, Any] = Field(default_factory=dict)
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1, max_length=128)


class ResearchStepResponse(BaseModel):
    key: str
    label: str
    status: str


class ResearchTaskResponse(BaseModel):
    id: str
    user_id: str
    question: str
    template_id: str | None
    scope: dict[str, Any]
    constraints: list[dict[str, Any]]
    status: str
    steps: list[ResearchStepResponse]
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class ResearchEvidenceResponse(BaseModel):
    field: str
    value: Any
    source: str
    as_of: str | None


class ResearchCandidateResponse(BaseModel):
    code: str
    name: str
    industry: str | None
    close: float | None
    pe_ttm: float | None
    pb: float | None
    dividend_yield: float | None
    total_market_value: float | None
    reason: str
    evidence: list[ResearchEvidenceResponse]


class ResearchResultResponse(BaseModel):
    task_id: str
    question: str
    template_id: str | None
    summary: str
    source: str
    as_of: str | None
    scope: dict[str, Any]
    candidates: list[ResearchCandidateResponse]
    risks: list[str]
    created_at: str


router = APIRouter(
    prefix="/api/research/tasks",
    tags=["research-tasks"],
    dependencies=[Depends(require_user)],
)
_service: ResearchTaskService | None = None


def _get_service() -> ResearchTaskService:
    global _service
    if _service is None:
        from src.api import product_routes
        from src.product.public_research import PublicResearchService

        _service = ResearchTaskService(product_routes._get_store(), PublicResearchService())
    return _service


@router.post("", response_model=ResearchTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_research_task(
    body: CreateResearchTaskRequest,
    user: dict = Depends(require_user),
) -> ResearchTaskResponse:
    try:
        task = _get_service().create_and_run(
            user["id"],
            question=body.question.strip(),
            template_id=body.template_id,
            scope=body.scope,
            constraints=body.constraints,
            idempotency_key=body.idempotency_key,
        )
        return ResearchTaskResponse(**asdict(task))
    except InvalidResearchConstraint as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="研究服务暂时不可用") from exc


@router.get("/{task_id}", response_model=ResearchTaskResponse)
async def get_research_task(task_id: str, user: dict = Depends(require_user)) -> ResearchTaskResponse:
    try:
        return ResearchTaskResponse(**asdict(_get_service().get(user["id"], task_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究任务不存在") from exc


@router.get("/{task_id}/result", response_model=ResearchResultResponse)
async def get_research_result(task_id: str, user: dict = Depends(require_user)) -> ResearchResultResponse:
    try:
        return ResearchResultResponse(**asdict(_get_service().result(user["id"], task_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究结果不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{task_id}/cancel", response_model=ResearchTaskResponse)
async def cancel_research_task(task_id: str, user: dict = Depends(require_user)) -> ResearchTaskResponse:
    try:
        return ResearchTaskResponse(**asdict(_get_service().cancel(user["id"], task_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究任务不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def register_research_task_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/research/tasks" for route in app.routes):
        app.include_router(router)
    return router
