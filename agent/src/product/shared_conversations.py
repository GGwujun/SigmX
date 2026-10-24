"""Publicly shared research conversation links (read-only, revocable).

信任模型与 report_snapshots 相同：slug（uuid4().hex）是不可猜测凭据，
知道 slug 即授权只读。属主身份存在分享行里，公开读取经现有
``ResearchOrchestrator.thread(user_id, task_id)`` 走原有属主过滤，零旁路。
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from src.product.store import ProductStore

# 公开投影的固定文案：原始异常可能带 provider base_url、内部路径，一律不外泄。
FAILED_TASK_PLACEHOLDER = "研究任务执行失败"
FAILED_EVENT_PLACEHOLDER = "研究任务执行失败"
ERROR_KEY_PLACEHOLDER = "内部错误"


class SharedConversationNotFound(Exception):
    pass


class SharedConversationRevoked(Exception):
    pass


@dataclass(frozen=True)
class SharedConversation:
    id: str
    user_id: str
    task_id: str
    slug: str
    created_at: str
    revoked_at: str | None


def _sanitize(value: Any) -> Any:
    """递归清洗事件 payload：``error`` 键的值换成固定文案（stage_loop 会存原始异常字符串）。"""
    if isinstance(value, dict):
        return {key: (ERROR_KEY_PLACEHOLDER if key == "error" else _sanitize(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _public_turn(turn: dict[str, Any]) -> dict[str, Any]:
    task = dict(turn["task"])
    task.pop("user_id", None)  # 内部用户 UUID 不进公开页
    if task.get("status") == "failed":
        task["error"] = FAILED_TASK_PLACEHOLDER
    events = []
    for event in turn.get("events") or []:
        payload = _sanitize(event.get("payload"))
        if event.get("type") == "failed" and isinstance(payload, dict):
            payload = {**payload, "message": FAILED_EVENT_PLACEHOLDER}
        events.append({"id": event.get("id"), "type": event.get("type"),
                       "payload": payload, "created_at": event.get("created_at")})
    return {"task": task, "events": events, "result": turn.get("result")}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SharedConversationService:
    def __init__(self, store: ProductStore,
                 thread_loader: Callable[[str, str], list[dict[str, Any]]],
                 now: Callable[[], str] = _utc_now_iso) -> None:
        self.store = store
        self.thread_loader = thread_loader
        self._now = now

    def share(self, user_id: str, task_id: str) -> SharedConversation:
        """生成（或幂等复用）公开链接；对话未通过合规检查时拒绝公开。"""
        existing = self.get_active(user_id, task_id)
        if existing is not None:
            return existing
        turns = self.thread_loader(user_id, task_id)  # 属主校验在 thread 读取里完成
        self._compliance_check(turns)
        item = SharedConversation(id=str(uuid.uuid4()), user_id=user_id, task_id=task_id,
                                  slug=uuid.uuid4().hex, created_at=self._now(), revoked_at=None)
        try:
            with self.store.transaction() as conn:
                conn.execute(
                    "INSERT INTO shared_conversations (id,user_id,task_id,slug,created_at,revoked_at) "
                    "VALUES (?,?,?,?,?,NULL)",
                    (item.id, item.user_id, item.task_id, item.slug, item.created_at),
                )
        except sqlite3.IntegrityError:
            # 部分唯一索引竞态：并发分享同一任务时复用先到者的链接
            existing = self.get_active(user_id, task_id)
            if existing is not None:
                return existing
            raise
        return item

    def get_active(self, user_id: str, task_id: str) -> SharedConversation | None:
        row = self.store._get_conn().execute(
            "SELECT * FROM shared_conversations WHERE user_id=? AND task_id=? AND revoked_at IS NULL",
            (user_id, task_id),
        ).fetchone()
        return self._item(row) if row else None

    def get_by_slug(self, slug: str) -> SharedConversation | None:
        row = self.store._get_conn().execute(
            "SELECT * FROM shared_conversations WHERE slug=?", (slug,)
        ).fetchone()
        return self._item(row) if row else None

    def revoke(self, user_id: str, task_id: str) -> bool:
        """软撤销；旧 slug 永久 410（可能已外泄），重分享会生成新 slug。"""
        with self.store.transaction() as conn:
            cursor = conn.execute(
                "UPDATE shared_conversations SET revoked_at=? "
                "WHERE user_id=? AND task_id=? AND revoked_at IS NULL",
                (self._now(), user_id, task_id),
            )
        return cursor.rowcount > 0

    def public_conversation(self, slug: str) -> dict[str, Any]:
        row = self.get_by_slug(slug)
        if row is None:
            raise SharedConversationNotFound(slug)
        if row.revoked_at is not None:
            raise SharedConversationRevoked(slug)
        try:
            turns = [_public_turn(turn) for turn in self.thread_loader(row.user_id, row.task_id)]
        except KeyError as exc:
            raise SharedConversationNotFound(slug) from exc
        return {"slug": row.slug,
                "question": turns[-1]["task"]["question"] if turns else "",
                "created_at": row.created_at,
                "turns": turns}

    @staticmethod
    def _compliance_check(turns: list[dict[str, Any]]) -> None:
        """公开前过产物级合规 gate（与 publish_report 同一道闸）：公开页是平台外发内容。"""
        from src.compliance.gate import compliance_gate

        texts = [turn["task"]["question"] for turn in turns]
        for turn in turns:
            result = turn.get("result")
            if not result:
                continue
            texts.append(str(result.get("summary") or ""))
            for conclusion in result.get("conclusions") or []:
                texts.append(str(conclusion.get("text") or ""))
            texts.extend(str(risk) for risk in result.get("risks") or [])
        gate = compliance_gate("\n".join(text for text in texts if text))
        if not gate.ok:
            hits = "; ".join(f"第 {h.line} 行命中「{h.pattern}」" for h in gate.hits[:5])
            raise ValueError(f"对话未通过合规检查，暂不能公开: {hits}")

    @staticmethod
    def _item(row) -> SharedConversation:
        return SharedConversation(row["id"], row["user_id"], row["task_id"], row["slug"],
                                  row["created_at"], row["revoked_at"])
