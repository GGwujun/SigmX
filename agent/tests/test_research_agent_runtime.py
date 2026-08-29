import json
import pytest

from src.providers.chat import LLMResponse, ToolCallRequest
from src.research_agent.runner import ResearchRunRequest
from src.research_agent.runtime import ResearchAgentRuntime
from src.research_agent.tools import build_research_tools


class ToolThenAnswerLLM:
    model_name = "test-model"

    def __init__(self) -> None:
        self.calls = 0
        self.system_prompt = ""

    def stream_chat(self, messages, tools=None, on_text_chunk=None, timeout=None):
        self.calls += 1
        self.system_prompt = messages[0]["content"]
        if self.calls == 1:
            return LLMResponse(tool_calls=[ToolCallRequest("1", "search_market_data", {"query": "现金流"})])
        return LLMResponse(content=json.dumps({
            "summary": "找到改善公司", "conclusions": [{"text": "公司现金流改善", "evidence_ids": ["e-1"]}],
            "risks": ["数据可能延迟"],
        }, ensure_ascii=False))


def test_runtime_uses_agent_loop_and_collects_evidence(tmp_path) -> None:
    llm = ToolThenAnswerLLM()
    tools = build_research_tools(
        data_search=lambda query: {"evidence": [{"id": "e-1", "field": "cashflow", "value": 1, "source": "Data Hub"}]},
        skill_loader=lambda name: {"name": name},
    )
    runtime = ResearchAgentRuntime(lambda: llm, tools, max_iterations=50, runs_dir=tmp_path)

    output = runtime.run(ResearchRunRequest("寻找现金流改善公司", {"skills": []}), lambda event: None)

    assert output.summary == "找到改善公司"
    assert output.evidence[0]["id"] == "e-1"
    assert output.model == "test-model"
    assert "extract_shadow_strategy" not in llm.system_prompt


class RepeatingToolLLM:
    def __init__(self) -> None:
        self.calls = 0

    def stream_chat(self, messages, tools=None, on_text_chunk=None, timeout=None):
        self.calls += 1
        return LLMResponse(tool_calls=[ToolCallRequest(str(self.calls), "search_market_data", {"query": "继续检索"})])


def test_runtime_stops_repetitive_research_after_twelve_iterations(tmp_path) -> None:
    llm = RepeatingToolLLM()
    tools = build_research_tools(
        data_search=lambda query: {"evidence": []},
        skill_loader=lambda name: {"name": name},
    )
    runtime = ResearchAgentRuntime(lambda: llm, tools, runs_dir=tmp_path)

    with pytest.raises(RuntimeError):
        runtime.run(ResearchRunRequest("持续检索", {"skills": []}), lambda event: None)

    assert llm.calls == 12


class HallucinatingEvidenceLLM:
    """Streams a final answer citing a fabricated evidence id, then repairs."""
    model_name = "test-model"

    def __init__(self, repaired_ids: list[str]) -> None:
        self.stream_calls = 0
        self.chat_calls = 0
        self.repaired_ids = repaired_ids

    def stream_chat(self, messages, tools=None, on_text_chunk=None, timeout=None):
        self.stream_calls += 1
        if self.stream_calls == 1:
            return LLMResponse(tool_calls=[ToolCallRequest("1", "search_market_data", {"query": "现金流"})])
        return LLMResponse(content=json.dumps({
            "summary": "找到改善公司",
            "conclusions": [{"text": "公司现金流改善", "evidence_ids": ["hallucinated-9"]}],
            "risks": [],
        }, ensure_ascii=False))

    def chat(self, messages, tools=None, timeout=None):
        self.chat_calls += 1
        assert "valid_evidence_ids" in messages[0]["content"]
        return LLMResponse(content=json.dumps({
            "summary": "找到改善公司",
            "conclusions": [{"text": "公司现金流改善", "evidence_ids": self.repaired_ids}],
            "risks": [],
        }, ensure_ascii=False))


def _evidence_tools():
    return build_research_tools(
        data_search=lambda query: {"evidence": [{"id": "e-1", "field": "cashflow", "value": 1, "source": "Data Hub"}]},
        skill_loader=lambda name: {"name": name},
    )


def test_runtime_repairs_conclusions_that_cite_unknown_evidence(tmp_path) -> None:
    llm = HallucinatingEvidenceLLM(repaired_ids=["e-1"])
    runtime = ResearchAgentRuntime(lambda: llm, _evidence_tools(), max_iterations=50, runs_dir=tmp_path)

    output = runtime.run(ResearchRunRequest("寻找现金流改善公司", {"skills": []}), lambda event: None)

    assert output.conclusions == [{"text": "公司现金流改善", "evidence_ids": ["e-1"]}]
    assert llm.chat_calls == 1


def test_runtime_rejects_output_when_repair_still_hallucinates(tmp_path) -> None:
    llm = HallucinatingEvidenceLLM(repaired_ids=["still-bad"])
    runtime = ResearchAgentRuntime(lambda: llm, _evidence_tools(), max_iterations=50, runs_dir=tmp_path)

    with pytest.raises(ValueError, match="unknown evidence"):
        runtime.run(ResearchRunRequest("寻找现金流改善公司", {"skills": []}), lambda event: None)
