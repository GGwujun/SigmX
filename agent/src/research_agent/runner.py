"""A small AgentLoop-compatible research runner with public-safe events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.research_agent.tools import ResearchTool


@dataclass(frozen=True)
class ResearchRunRequest:
    question: str
    plan: dict[str, Any]


@dataclass(frozen=True)
class AgentResearchOutput:
    summary: str
    conclusions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    risks: list[str]
    model: str | None = None


class ResearchAgentRunner:
    def __init__(self, llm_factory: Callable[[], Any], tools: list[ResearchTool], *, max_turns: int = 8, timeout_seconds: int = 90) -> None:
        self.llm_factory = llm_factory
        self.tools = {tool.name: tool for tool in tools}
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds

    def run(self, request: ResearchRunRequest, emit: Callable[[dict[str, Any]], None], cancel: Callable[[], bool] | None = None) -> AgentResearchOutput:
        llm = self.llm_factory()
        evidence: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": json.dumps({"question": request.question, "confirmed_plan": request.plan}, ensure_ascii=False)},
        ]
        schemas = [tool.schema() for tool in self.tools.values()]
        for _ in range(self.max_turns):
            if cancel and cancel():
                raise RuntimeError("research cancelled")
            response = llm.chat(messages, tools=schemas, timeout=self.timeout_seconds)
            if response.tool_calls:
                messages.append({"role": "assistant", "content": response.content or "", "tool_calls": [
                    {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
                    for call in response.tool_calls
                ]})
                for call in response.tool_calls:
                    tool = self.tools.get(call.name)
                    if tool is None:
                        raise ValueError(f"research tool is not allowed: {call.name}")
                    emit({"type": "tool_started", "tool": call.name})
                    result = tool.execute(call.arguments)
                    found = result.get("evidence", []) if isinstance(result, dict) else []
                    if isinstance(found, list):
                        evidence.extend(item for item in found if isinstance(item, dict))
                    emit({"type": "tool_completed", "tool": call.name, "evidence_count": len(found)})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
                continue
            payload = self._parse_final(response.content or "")
            known = {str(item.get("id")) for item in evidence if item.get("id")}
            conclusions = payload.get("conclusions", [])
            if any(not set(map(str, item.get("evidence_ids", []))).issubset(known) for item in conclusions):
                raise ValueError("AI conclusion references unknown evidence")
            output = AgentResearchOutput(
                summary=str(payload.get("summary") or "研究已完成"), conclusions=conclusions,
                evidence=evidence, risks=[str(item) for item in payload.get("risks", [])],
                model=getattr(llm, "model_name", None),
            )
            emit({"type": "completed", "evidence_count": len(evidence)})
            return output
        raise TimeoutError("research agent exceeded maximum turns")

    @staticmethod
    def _parse_final(content: str) -> dict[str, Any]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("research agent returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("research agent result must be an object")
        return payload

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是 SigmX Web AI 投研智能体。只允许进行研究，不得访问账户、持仓、券商、订单、交易、"
            "Mandate、live runner 或影子账户。所有数值结论必须引用工具返回的 evidence id。"
            "最终只输出 JSON：summary、conclusions[{text,evidence_ids}]、risks。"
        )
