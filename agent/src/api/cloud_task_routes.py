"""Authenticated personal cloud-task APIs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.auth_routes import require_user
from src.product.cloud_tasks import CloudTaskService, InvalidTaskTransition
from src.product.credits import InsufficientCredits
from src.product.query_history import QueryHistoryService


class CreateCloudTaskRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    cost: int = Field(ge=1, le=100_000)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)


class CloudTaskResponse(BaseModel):
    id: str
    user_id: str
    task_type: str
    title: str
    status: str
    payload: dict[str, Any]
    reserved_credits: int
    reservation_id: str
    result_ref: str | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


class CloudTaskListResponse(BaseModel):
    items: list[CloudTaskResponse]


class RecordQueryExecutionRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    intent: str = Field(min_length=1, max_length=64)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    result_count: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)


class QueryExecutionResponse(BaseModel):
    id: str
    user_id: str
    query: str
    intent: str
    conditions: list[dict[str, Any]]
    condition_version: int
    result_count: int
    executed_at: str


class QueryExecutionListResponse(BaseModel):
    items: list[QueryExecutionResponse]


router = APIRouter(prefix="/api/cloud/tasks", tags=["cloud-tasks"], dependencies=[Depends(require_user)])
query_router = APIRouter(prefix="/api/cloud/query-executions", tags=["query-history"], dependencies=[Depends(require_user)])
_service: CloudTaskService | None = None
_query_history: QueryHistoryService | None = None


def _get_service() -> CloudTaskService:
    global _service
    if _service is None:
        from src.api import product_routes
        from src.product.cloud_tasks import CloudTaskService

        _service = CloudTaskService(product_routes._get_store(), product_routes._get_ledger())
    return _service


def _get_query_history() -> QueryHistoryService:
    global _query_history
    if _query_history is None:
        from src.api import product_routes
        _query_history = QueryHistoryService(product_routes._get_store())
    return _query_history


def _response(task) -> CloudTaskResponse:
    return CloudTaskResponse(**asdict(task))


@router.post("", response_model=CloudTaskResponse)
async def create_cloud_task(body: CreateCloudTaskRequest, user: dict = Depends(require_user)) -> CloudTaskResponse:
    try:
        return _response(_get_service().create(
            user["id"], task_type=body.task_type, title=body.title, cost=body.cost,
            payload=body.payload, idempotency_key=body.idempotency_key,
        ))
    except InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


@router.get("", response_model=CloudTaskListResponse)
async def list_cloud_tasks(limit: int = Query(50, ge=1, le=200), user: dict = Depends(require_user)) -> CloudTaskListResponse:
    return CloudTaskListResponse(items=[_response(task) for task in _get_service().list(user["id"], limit)])


@router.post("/{task_id}/start", response_model=CloudTaskResponse)
async def start_cloud_task(task_id: str, user: dict = Depends(require_user)) -> CloudTaskResponse:
    return _transition(lambda: _get_service().start(user["id"], task_id))


@router.post("/{task_id}/cancel", response_model=CloudTaskResponse)
async def cancel_cloud_task(task_id: str, user: dict = Depends(require_user)) -> CloudTaskResponse:
    return _transition(lambda: _get_service().cancel(user["id"], task_id))


def _transition(operation) -> CloudTaskResponse:
    try:
        return _response(operation())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="cloud task not found") from exc
    except InvalidTaskTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@query_router.post("", response_model=QueryExecutionResponse)
async def record_query_execution(body: RecordQueryExecutionRequest, user: dict = Depends(require_user)) -> QueryExecutionResponse:
    return QueryExecutionResponse(**asdict(_get_query_history().record(
        user["id"], query=body.query, intent=body.intent, conditions=body.conditions,
        result_count=body.result_count, idempotency_key=body.idempotency_key,
    )))


@query_router.get("", response_model=QueryExecutionListResponse)
async def list_query_executions(limit: int = Query(100, ge=1, le=500), user: dict = Depends(require_user)) -> QueryExecutionListResponse:
    return QueryExecutionListResponse(items=[QueryExecutionResponse(**asdict(item)) for item in _get_query_history().list(user["id"], limit)])


def register_cloud_task_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/cloud/tasks" for route in app.routes):
        app.include_router(router)
        app.include_router(query_router)
    return router
