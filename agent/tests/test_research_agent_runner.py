from src.research_agent.runner import ResearchAgentRunner, ResearchRunRequest
from src.research_agent.tools import ResearchTool


class ToolCallingLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None, timeout=None):
        from src.providers.chat import LLMResponse, ToolCallRequest

        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="正在检索",
                tool_calls=[ToolCallRequest(id="call-1", name="search_market_data", arguments={"query": "现金流改善"})],
                finish_reason="tool_calls",
            )
        return LLMResponse(content='{"summary":"找到高质量候选","conclusions":[{"text":"样本现金流改善","evidence_ids":["ev-1"]}],"risks":["数据可能延迟"]}')


def test_runner_calls_research_tool_and_emits_evidence_without_thought_chain() -> None:
    events = []
    tool = ResearchTool(
        name="search_market_data",
        description="检索研究数据",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        execute=lambda args: {"evidence": [{"id": "ev-1", "field": "operating_cashflow", "value": 12, "source": "data_hub", "as_of": "2026-06-30"}]},
    )
    runner = ResearchAgentRunner(lambda: ToolCallingLLM(), [tool])

    output = runner.run(ResearchRunRequest(question="寻找现金流改善公司", plan={}), events.append)

    assert output.summary == "找到高质量候选"
    assert output.evidence[0]["id"] == "ev-1"
    assert output.conclusions[0]["evidence_ids"] == ["ev-1"]
    assert {event["type"] for event in events} >= {"tool_started", "tool_completed", "completed"}
    assert all("reasoning" not in event and "thought" not in event for event in events)
