"""Authenticated Web research task and result APIs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.product.research_plans import AIResearchPlanService, ResearchPlanService
from src.product.research_tasks import InvalidResearchConstraint, ResearchDataUnavailable, ResearchTaskService
from src.product.research_orchestrator import ResearchOrchestrator


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
    plan: dict[str, Any] | None = None


class CreateResearchPlanRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    template_id: str | None = Field(default=None, max_length=64)
    scope: dict[str, Any] = Field(default_factory=dict)


class ResearchConditionAlternativeResponse(BaseModel):
    label: str
    question: str


class ResearchConditionResponse(BaseModel):
    id: str
    metric: str
    label: str
    operator: str | None
    value: float | str | None
    period: str | None
    benchmark: str | None
    status: str
    reason: str | None
    alternatives: list[ResearchConditionAlternativeResponse]


class ResearchDatasetResponse(BaseModel):
    key: str
    name: str
    status: str
    as_of: str | None
    coverage: str | None


class ResearchPlanStepResponse(BaseModel):
    key: str
    label: str
    status: str


class ResearchPlanResponse(BaseModel):
    id: str
    question: str
    template_id: str | None
    scope: dict[str, Any]
    conditions: list[ResearchConditionResponse]
    ranking: list[dict[str, Any]]
    datasets: list[ResearchDatasetResponse]
    steps: list[ResearchPlanStepResponse]
    constraints: list[dict[str, Any]]
    executable: bool
    suggested_question: str | None
    execution_mode: str
    model: str | None
    skills: list[str]


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
    conclusions: list[dict[str, Any]] = Field(default_factory=list)
    agent_evidence: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    model: str | None = None
    execution_mode: str = "rules_fallback"


router = APIRouter(
    prefix="/api/research/tasks",
    tags=["research-tasks"],
    dependencies=[Depends(require_user)],
)
plan_router = APIRouter(
    prefix="/api/research/plans",
    tags=["research-plans"],
)
_service: ResearchTaskService | None = None
_orchestrator: ResearchOrchestrator | None = None
_plan_service = None


def _get_plan_service():
    global _plan_service
    if _plan_service is not None:
        return _plan_service
    try:
        from src.api.product_routes import _get_store
        from src.product.ai_runtime_config import AIRuntimeConfigService, build_configured_chat

        config = AIRuntimeConfigService(_get_store()).get_effective()
        _plan_service = AIResearchPlanService(
            lambda: build_configured_chat(
                config.planning,
                temperature=config.temperature,
                timeout_seconds=config.timeout_seconds,
                max_retries=config.max_retries,
            ),
            timeout_seconds=config.timeout_seconds,
        )
    except Exception:
        _plan_service = ResearchPlanService()
    return _plan_service


def _get_service() -> ResearchTaskService:
    global _service
    if _service is None:
        from src.api import product_routes
        from src.product.public_research import PublicResearchService

        _service = ResearchTaskService(product_routes._get_store(), PublicResearchService())
    return _service


def _get_orchestrator() -> ResearchOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        service = _get_service()
        _orchestrator = ResearchOrchestrator(service.store, service, runner_factory=_build_agent_runner)
    return _orchestrator


def _build_agent_runner():
    from pathlib import Path
    from src.api.product_routes import _get_store
    from src.product.ai_runtime_config import AIRuntimeConfigService, build_configured_chat
    from src.research_agent.runner import ResearchAgentRunner
    from src.research_agent.tools import build_research_tools
    from src.skill_runtime.manifest import load_skill_manifest

    config = AIRuntimeConfigService(_get_store()).get_effective()
    research = _get_service().research

    def data_search(query: str) -> dict[str, Any]:
        result = research.search(query, limit=20)
        evidence = []
        for item in result.items:
            for field in ("close", "pe_ttm", "pb", "dividend_yield", "total_market_value"):
                value = getattr(item, field, None)
                if value is not None:
                    evidence.append({"id": f"{item.code}:{field}:{item.as_of or 'unknown'}", "code": item.code,
                                     "name": item.name, "field": field, "value": value,
                                     "source": result.source, "as_of": item.as_of})
        return {"interpretation": result.interpretation, "evidence": evidence}

    def skill_loader(name: str) -> dict[str, Any]:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_")
        path = Path(__file__).resolve().parents[2] / "skills" / safe / "SKILL.md"
        manifest = load_skill_manifest(path)
        return {"name": manifest.slug, "description": manifest.description,
                "primary_source": manifest.policy.primary_source,
                "datahub_endpoints": list(manifest.policy.datahub_endpoints)}

    tools = build_research_tools(data_search=data_search, skill_loader=skill_loader)
    return ResearchAgentRunner(
        lambda: build_configured_chat(config.execution, temperature=config.temperature,
                                      timeout_seconds=config.timeout_seconds, max_retries=config.max_retries),
        tools, timeout_seconds=config.timeout_seconds,
    )


@plan_router.post("", response_model=ResearchPlanResponse)
async def create_research_plan(
    body: CreateResearchPlanRequest,
) -> ResearchPlanResponse:
    try:
        plan = _get_plan_service().create(body.question, body.template_id, body.scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ResearchPlanResponse(**asdict(plan), constraints=plan.to_constraints())


@router.post("", response_model=ResearchTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_research_task(
    body: CreateResearchTaskRequest,
    user: dict = Depends(require_user),
) -> ResearchTaskResponse:
    try:
        kwargs = dict(question=body.question.strip(), template_id=body.template_id,
                      scope=body.scope, constraints=body.constraints,
                      idempotency_key=body.idempotency_key)
        task = (_get_orchestrator().start(user["id"], **kwargs, plan=body.plan)
                if body.plan is not None else _get_service().create_and_run(user["id"], **kwargs))
        return ResearchTaskResponse(**asdict(task))
    except (InvalidResearchConstraint, ResearchDataUnavailable) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="研究服务暂时不可用") from exc


@router.get("", response_model=list[ResearchTaskResponse])
async def list_research_tasks(
    limit: int = 20,
    user: dict = Depends(require_user),
) -> list[ResearchTaskResponse]:
    return [ResearchTaskResponse(**asdict(task)) for task in _get_service().list(user["id"], limit)]


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
        return ResearchTaskResponse(**asdict(_get_orchestrator().cancel(user["id"], task_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究任务不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{task_id}/events")
async def list_research_events(task_id: str, after: int = 0, user: dict = Depends(require_user)) -> list[dict[str, Any]]:
    try:
        return _get_orchestrator().events(user["id"], task_id, after)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究任务不存在") from exc


@router.post("/{task_id}/retry", response_model=ResearchTaskResponse, status_code=status.HTTP_201_CREATED)
async def retry_research_task(task_id: str, user: dict = Depends(require_user)) -> ResearchTaskResponse:
    try:
        return ResearchTaskResponse(**asdict(_get_orchestrator().retry(user["id"], task_id)))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究任务不存在") from exc


def register_research_task_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/research/plans" for route in app.routes):
        app.include_router(plan_router)
    if not any(getattr(route, "path", "") == "/api/research/tasks" for route in app.routes):
        app.include_router(router)
    return router
