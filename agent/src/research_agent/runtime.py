from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from src.agent.context import ContextBuilder
from src.agent.loop import AgentLoop
from src.agent.memory import WorkspaceMemory
from src.agent.tools import BaseTool, ToolRegistry
from src.research_agent.runner import AgentResearchOutput, ResearchRunRequest
from src.research_agent.tools import ResearchTool
from src.research_agent.policy import build_research_registry


_SYSTEM_PROMPT = """你是 SigmX Web AI 投研智能体。你只能执行只读金融研究。
严禁访问或操作交易、订单、券商、账户、持仓、Mandate、影子账户、Shell 和任意服务器文件。
先加载相关 Skill，再使用被授予的工具完成数据检索、计算、比较和反向验证。
所有重要数值结论必须引用工具返回的 evidence id,evidence_ids 必须逐字复制工具返回结果中的 id 字段,禁止编造或改写。
最终只输出 JSON 对象：summary、conclusions[{text,evidence_ids}]、risks。不要输出 JSON 以外的文字。"""


def _cites_unknown_evidence(conclusions: list[dict[str, Any]], known: set[str]) -> bool:
    return any(not set(map(str, item.get("evidence_ids", []))).issubset(known) for item in conclusions)


class _CallableResearchTool(BaseTool):
    is_readonly = True
    repeatable = True

    def __init__(self, definition: ResearchTool, evidence: list[dict[str, Any]], lock: threading.Lock) -> None:
        self.name = definition.name
        self.description = definition.description
        self.parameters = definition.parameters
        self._definition = definition
        self._evidence = evidence
        self._lock = lock

    def execute(self, **kwargs: Any) -> str:
        result = self._definition.execute(kwargs)
        found = result.get("evidence", []) if isinstance(result, dict) else []
        with self._lock:
            self._evidence.extend(item for item in found if isinstance(item, dict))
        return json.dumps(result, ensure_ascii=False, default=str)


class ResearchAgentRuntime:
    def __init__(
        self, llm_factory: Callable[[], Any], tools: list[ResearchTool], *,
        max_iterations: int = 12, runs_dir: str | Path | None = None,
    ) -> None:
        self.llm_factory = llm_factory
        self.tools = tools
        self.max_iterations = max_iterations
        self.runs_dir = Path(runs_dir) if runs_dir is not None else None

    def run(
        self, request: ResearchRunRequest, emit: Callable[[dict[str, Any]], None],
        cancel: Callable[[], bool] | None = None,
    ) -> AgentResearchOutput:
        evidence: list[dict[str, Any]] = []
        evidence_lock = threading.Lock()
        registry: ToolRegistry = build_research_registry()
        for definition in self.tools:
            registry.register(_CallableResearchTool(definition, evidence, evidence_lock))
        memory = WorkspaceMemory()
        if self.runs_dir is not None:
            run_dir = self.runs_dir / uuid.uuid4().hex
            run_dir.mkdir(parents=True, exist_ok=True)
            memory.run_dir = str(run_dir)
        context = ContextBuilder(registry, memory, system_prompt=_SYSTEM_PROMPT)
        llm = self.llm_factory()
        agent: AgentLoop

        def forward(event_type: str, data: dict[str, Any]) -> None:
            if cancel and cancel():
                agent.cancel()
            payload = {"type": event_type, **data}
            emit(payload)

        agent = AgentLoop(
            registry=registry, llm=llm, memory=memory, context_builder=context,
            event_callback=forward, max_iterations=self.max_iterations,
        )
        prompt = json.dumps({"question": request.question, "confirmed_plan": request.plan}, ensure_ascii=False)
        result = agent.run(prompt, session_id=f"web-research-{uuid.uuid4().hex}")
        if result.get("status") != "success":
            raise RuntimeError(str(result.get("reason") or "AI research execution failed"))
        try:
            payload = json.loads(result.get("content") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("research agent returned invalid JSON") from exc
        known = {str(item.get("id")) for item in evidence if item.get("id")}
        conclusions = payload.get("conclusions") or []
        if _cites_unknown_evidence(conclusions, known):
            repaired = self._repair_output(llm, request, payload, sorted(known), emit)
            if repaired is not None:
                payload = repaired
                conclusions = payload.get("conclusions") or []
        if _cites_unknown_evidence(conclusions, known):
            raise ValueError("AI conclusion references unknown evidence")
        emit({"type": "runtime_completed", "iterations": result.get("iterations", 0),
              "max_iterations": self.max_iterations, "tools": registry.tool_names})
        return AgentResearchOutput(
            summary=str(payload.get("summary") or "研究已完成"), conclusions=conclusions,
            evidence=evidence, risks=[str(item) for item in payload.get("risks", [])],
            model=getattr(llm, "model_name", None),
        )

    def _repair_output(self, llm: Any, request: ResearchRunRequest,
                       payload: dict[str, Any], known_ids: list[str],
                       emit: Callable[[dict[str, Any]], None]) -> dict[str, Any] | None:
        """Ask the model to fix conclusions that cite hallucinated evidence ids.

        Returns the repaired payload, or ``None`` when the repair itself
        fails — the caller then rejects the output rather than serving
        unverifiable claims.
        """
        if known_ids:
            instruction = (
                "invalid_output 中的 conclusions 引用了不存在的 evidence id。"
                "只能使用 valid_evidence_ids 里逐字出现的 id;无法引用的结论直接删除。"
                "只输出修正后的 JSON 对象:summary、conclusions[{text,evidence_ids}]、risks。"
            )
        else:
            instruction = (
                "本次研究没有获取到任何可用证据,valid_evidence_ids 为空。"
                "conclusions 必须输出空数组 [],不允许引用任何 evidence id;"
                "在 summary 中如实说明数据不可用的情况与原因。"
                "只输出修正后的 JSON 对象:summary、conclusions[]、risks。"
            )
        prompt = json.dumps({
            "question": request.question,
            "invalid_output": payload,
            "valid_evidence_ids": known_ids,
            "instruction": instruction,
        }, ensure_ascii=False)
        emit({"type": "repair_started", "reason": "unknown_evidence"})
        try:
            response = llm.chat([{"role": "user", "content": prompt}])
            repaired = json.loads(response.content or "{}")
        except Exception:  # noqa: BLE001 — any repair failure falls back to rejection
            emit({"type": "repair_failed"})
            return None
        if not isinstance(repaired, dict):
            emit({"type": "repair_failed"})
            return None
        emit({"type": "repair_completed"})
        return repaired
