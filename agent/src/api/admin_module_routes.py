"""Read-only, database-backed operations module summaries."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel
from src.api.auth_routes import require_admin
from src.auth.store import UserStore
from src.product.store import ProductStore

class AdminStat(BaseModel):
    key: str; label: str; value: int | float | str | None
class AdminRow(BaseModel):
    id: str; cells: list[str]
class AdminModuleResponse(BaseModel):
    module: str; title: str; description: str; columns: list[str]; stats: list[AdminStat]; rows: list[AdminRow]; as_of: str

router = APIRouter(prefix="/api/admin/modules", tags=["admin-modules"], dependencies=[Depends(require_admin)])
_user_store: UserStore | None = None
_product_store: ProductStore | None = None

def _stores() -> tuple[UserStore, ProductStore]:
    global _user_store, _product_store
    if _user_store is None:
        from src.api.auth_routes import _get_store
        _user_store = _get_store()
    if _product_store is None:
        from src.api.product_routes import _get_store
        _product_store = _get_store()
    return _user_store, _product_store

@router.get("/{module}", response_model=AdminModuleResponse)
async def admin_module(module: str, admin: dict = Depends(require_admin)) -> AdminModuleResponse:
    users, product = _stores(); now = datetime.now(timezone.utc).isoformat()
    if module == "users":
        conn = users._get_conn(); rows = conn.execute("SELECT id,email,is_admin,disclaimer_accepted_at,created_at FROM users ORDER BY created_at DESC LIMIT 100").fetchall()
        return AdminModuleResponse(module=module, title="用户", description="来自账户库的真实注册与角色状态。", columns=["邮箱", "角色", "声明状态", "注册时间"], stats=[AdminStat(key="total_users", label="总用户", value=conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]), AdminStat(key="admins", label="管理员", value=conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0])], rows=[AdminRow(id=row["id"], cells=[row["email"], "管理员" if row["is_admin"] else "用户", "已确认" if row["disclaimer_accepted_at"] else "未确认", row["created_at"]]) for row in rows], as_of=now)
    conn = product._get_conn()
    if module == "dataHub":
        total = conn.execute("SELECT COUNT(*) FROM datahub_credentials WHERE revoked_at IS NULL").fetchone()[0]; requests = conn.execute("SELECT COUNT(*) FROM datahub_request_usage").fetchone()[0]
        grouped = conn.execute("SELECT endpoint_code,COUNT(*) AS requests,SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END) AS success FROM datahub_request_usage GROUP BY endpoint_code ORDER BY requests DESC LIMIT 100").fetchall()
        return AdminModuleResponse(module=module, title="Data Hub 运营", description="来自 Credential 与接口调用账本。", columns=["接口", "调用量", "成功量"], stats=[AdminStat(key="active_credentials", label="活跃 Credential", value=total), AdminStat(key="requests", label="累计调用", value=requests)], rows=[AdminRow(id=row["endpoint_code"], cells=[row["endpoint_code"], str(row["requests"]), str(row["success"] or 0)]) for row in grouped], as_of=now)
    if module == "audit":
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]; rows = conn.execute("SELECT id,created_at,actor,action,target,reason FROM audit_log ORDER BY created_at DESC LIMIT 100").fetchall()
        return AdminModuleResponse(module=module, title="审计日志", description="来自运营审计记录。", columns=["时间", "操作者", "动作", "目标", "原因"], stats=[AdminStat(key="audit_events", label="审计事件", value=count)], rows=[AdminRow(id=row["id"], cells=[str(row[key] or "—") for key in ("created_at", "actor", "action", "target", "reason")]) for row in rows], as_of=now)
    if module in {"content", "system"}:
        return AdminModuleResponse(module=module, title="内容运营" if module == "content" else "系统状态", description="尚无已接入的运营记录。" if module == "content" else "产品数据库连接正常。", columns=[], stats=[AdminStat(key="records", label="可用记录", value=0)], rows=[], as_of=now)
    raise HTTPException(status_code=404, detail="运营模块不存在")

def register_admin_module_routes(app: FastAPI) -> APIRouter:
    if not any(getattr(route, "path", "") == "/api/admin/modules/{module}" for route in app.routes): app.include_router(router)
    return router
