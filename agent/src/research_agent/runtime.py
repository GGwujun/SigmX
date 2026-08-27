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


_SYSTEM_PROMPT = """你是 SigmX Web AI 投研智能体。你只能执行只读金融研究。
严禁访问或操作交易、订单、券商、账户、持仓、Mandate、影子账户、Shell 和任意服务器文件。
先加载相关 Skill，再使用被授予的工具完成数据检索、计算、比较和反向验证。
所有重要数值结论必须引用工具返回的 evidence id。
最终只输出 JSON 对象：summary、conclusions[{text,evidence_ids}]、risks。不要输出 JSON 以外的文字。"""


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
        max_iterations: int = 50, runs_dir: str | Path | None = None,
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
        registry = ToolRegistry()
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
        if any(not set(map(str, item.get("evidence_ids", []))).issubset(known) for item in conclusions):
            raise ValueError("AI conclusion references unknown evidence")
        emit({"type": "runtime_completed", "iterations": result.get("iterations", 0),
              "max_iterations": self.max_iterations, "tools": registry.tool_names})
        return AgentResearchOutput(
            summary=str(payload.get("summary") or "研究已完成"), conclusions=conclusions,
            evidence=evidence, risks=[str(item) for item in payload.get("risks", [])],
            model=getattr(llm, "model_name", None),
        )
