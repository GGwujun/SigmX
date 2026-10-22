# -*- coding: utf-8 -*-
"""A 股插件 + runner 挂载测试：真插件 + 合成取数 + FakeLLM 跑通五阶段，
再挂真 ResearchOrchestrator 验证 research_agent_outputs 落库。全程无网络。"""

import json
import time
from pathlib import Path

import pytest
from src.providers.chat import LLMResponse, ToolCallRequest

from src.research_pipeline.calc import calculation_id
from src.research_pipeline.orchestrator import verify_protected
from src.research_pipeline.plugin import validate_plugin
from src.research_pipeline.plugins.a_stock import (A_STOCK_DEEP_RESEARCH,
                                                   REPORT_SECTIONS,
                                                   a_stock_plugin)
from src.research_pipeline.runner_adapter import (PipelineDispatchRunner,
                                                  PipelineResearchRunner,
                                                  resolve_code)


# ---------------------------------------------------------------------------
# 脚手架
# ---------------------------------------------------------------------------

def _registry():
    return {
        "security_profile": lambda s, c, td: [{"code": "300750", "name": "示例股份", "industry": "电力设备"}],
        "bars_daily_90d": lambda s, c, td: [
            {"date": "2026-09-01", "close": 100.0},
            {"date": "2026-09-02", "close": 110.0},
            {"date": "2026-09-03", "close": 105.0},
        ],
        "daily_basic_90d": lambda s, c, td: [
            {"date": "2026-09-01", "pe_ttm": 45.0, "pb": 5.0, "total_mv": 1.1e12},
            {"date": "2026-09-02", "pe_ttm": 46.0, "pb": 5.1, "total_mv": 1.12e12},
            {"date": "2026-09-03", "pe_ttm": 44.0, "pb": 4.9, "total_mv": 1.08e12},
        ],
        "capital_flow_20d": lambda s, c, td: [
            {"date": "2026-09-02", "net_amount": 1.5e8},
            {"date": "2026-09-03", "net_amount": -0.5e8},
        ],
        "pool_zt_today": lambda s, c, td: [{"code": "300750", "pool": "zt"}],
        "shortline_themes": lambda s, c, td: [{"trade_date": "2026-09-03", "kind": "themes",
                                               "payload": {"themes": [{"name": "固态电池"}]}}],
        "announcements_90d": lambda s, c, td: [{"date": "2026-08-01", "title": "关于回购股份的公告"}],
    }


class FakeLLM:
    """脚本化模型：队列元素 = 一次收工尝试的回复列表。"""

    def __init__(self, turns):
        self.turns = list(turns)
        self.model_name = "fake-researcher"
        self.seen_users = []
        self._current = None

    def chat(self, messages, tools=None, timeout=None):
        if self._current is None:
            if not self.turns:
                raise AssertionError("FakeLLM 脚本用尽")
            self._current = list(self.turns.pop(0))
        users = [m for m in messages if m.get("role") == "user"]
        self.seen_users.append(str(users[-1].get("content", "")) if users else "")
        kind, name_or_text, *rest = self._current.pop(0)
        if kind == "tool":
            call = ToolCallRequest(id=f"call-{len(self.seen_users)}-{len(name_or_text)}",
                                   name=name_or_text, arguments=rest[0] if rest else {})
            return LLMResponse(content="", tool_calls=[call], finish_reason="tool_calls")
        resp = LLMResponse(content=name_or_text, tool_calls=[], finish_reason="stop")
        if not self._current:
            self._current = None
        return resp


VOL_ID = calculation_id("volatility", {"series": [100.0, 110.0, 105.0]})
MDD_ID = calculation_id("max_drawdown", {"series": [100.0, 110.0, 105.0]})
PE_RANK_ID = calculation_id("percentile_rank", {"value": 44.0, "series": [45.0, 46.0, 44.0]})
PB_RANK_ID = calculation_id("percentile_rank", {"value": 4.9, "series": [5.0, 5.1, 4.9]})

PROFILE_OUT = {
    "stage": "profile", "summary": "主营电力设备，近 90 日区间震荡，年化波动率偏高。",
    "trend": "range", "volatility_pct": 115.5, "max_drawdown_pct": 4.5,
    "data_freshness": "fresh",
    "evidence_ids": ["ev-security_profile-0", "ev-bars_daily_90d-0", "ev-daily_basic_90d-2"],
    "calculation_ids": [VOL_ID, MDD_ID],
}
VALUATION_OUT = {
    "stage": "valuation", "summary": "市盈率与市净率均处 90 日窗口偏高分位。",
    "pe_ttm_percentile": 66.7, "pb_percentile": 66.7, "total_mv_note": "总市值约 1.08 万亿元",
    "evidence_ids": ["ev-daily_basic_90d-2"],
    "calculation_ids": [PE_RANK_ID, PB_RANK_ID],
}
FUNDS_OUT = {
    "stage": "funds_sentiment", "summary": "近 20 日主力资金小幅净流入，今日属于涨停池，主题暴露固态电池。",
    "capital_direction": "net_inflow", "pool_membership": ["zt"], "theme_exposure": ["固态电池"],
    "evidence_ids": ["ev-capital_flow_20d-0", "ev-pool_zt_today-0", "ev-shortline_themes-0"],
    "calculation_ids": [],
}
RISK_OUT = {
    "stage": "risk", "summary": "估值分位偏高与资金流波动构成主要反证。",
    "counter_evidence": ["近 20 日主力资金最后一日转为净流出 0.5 亿元"],
    "decision_points": ["跟踪下一期主力资金方向", "跟踪市盈率分位回落情况", "跟踪回购进展公告"],
    "source_conflicts": [],
    "evidence_ids": ["ev-announcements_90d-0", "ev-capital_flow_20d-1"],
    "calculation_ids": [],
}


def _report_md():
    sections = "\n\n".join(f"# {s}\n\n本节为事实陈述，数字见证据引用。" for s in REPORT_SECTIONS)
    return f"状态: complete\n\n{sections}\n\n区间波动率计算引用 {VOL_ID}。\n"


def _full_llm_script():
    return [
        [  # profile
            ("tool", "calculate", {"function": "volatility", "args": {"series": [100.0, 110.0, 105.0]},
                                   "output_file": "01_vol.json"}),
            ("tool", "calculate", {"function": "max_drawdown", "args": {"series": [100.0, 110.0, 105.0]},
                                   "output_file": "02_mdd.json"}),
            ("tool", "write_stage", {"stage_output": PROFILE_OUT}),
            ("say", "done"),
        ],
        [  # valuation
            ("tool", "calculate", {"function": "percentile_rank",
                                   "args": {"value": 44.0, "series": [45.0, 46.0, 44.0]},
                                   "output_file": "01_pe_rank.json"}),
            ("tool", "calculate", {"function": "percentile_rank",
                                   "args": {"value": 4.9, "series": [5.0, 5.1, 4.9]},
                                   "output_file": "02_pb_rank.json"}),
            ("tool", "write_stage", {"stage_output": VALUATION_OUT}),
            ("say", "done"),
        ],
        [  # funds_sentiment
            ("tool", "write_stage", {"stage_output": FUNDS_OUT}),
            ("say", "done"),
        ],
        [  # risk
            ("tool", "write_stage", {"stage_output": RISK_OUT}),
            ("say", "done"),
        ],
        [  # report
            ("tool", "write_report", {"markdown": _report_md(),
                                      "stage_output": {"stage": "report", "summary": "五阶段整合完成，估值处窗口偏高分位。"}}),
            ("say", "done"),
        ],
    ]


def _request(plan, question="深研 300750"):
    from src.research_agent.runner import ResearchRunRequest
    return ResearchRunRequest(question=question, plan=plan)


# ---------------------------------------------------------------------------
# 插件与适配层
# ---------------------------------------------------------------------------

class TestAStockPlugin:
    def test_registers_clean(self):
        assert validate_plugin(a_stock_plugin) == []

    def test_stage_prompt_sheets_cover_all_stages(self):
        for stage in a_stock_plugin.stages:
            prompt = a_stock_plugin.build_stage_prompt(stage, {"code": "300750", "trade_date": None})
            assert "300750" in prompt and stage in prompt

    def test_report_stage_is_last_and_sections_declared(self):
        assert a_stock_plugin.stages[-1] == a_stock_plugin.report_stage == "report"
        assert a_stock_plugin.report_sections == REPORT_SECTIONS

    def test_resolve_code(self):
        assert resolve_code({"code": "600519"}, "任意") == "600519"
        assert resolve_code({}, "帮我深研 300750 这只股票") == "300750"
        assert resolve_code({"code": " 000001 "}, "") == "000001"
        with pytest.raises(ValueError):
            resolve_code({}, "没有代码的问题")

    def test_canonical_store_code_aligns_bare_to_suffixed_store(self):
        """线上库（tushare 后缀码）：裸码探测命中后缀后返回库内码型。"""
        from src.research_pipeline.runner_adapter import canonical_store_code

        class SuffixStore:
            def __init__(self, codes):
                self.codes = set(codes)
                self.probes = []

            def get_security_profile(self, code):
                self.probes.append(code)
                return {"code": code} if code in self.codes else None

        store = SuffixStore({"600519.SH"})
        assert canonical_store_code(store, "600519") == "600519.SH"
        assert store.probes == ["600519", "600519.SH"]   # 裸码未命中后只试了 .SH

    def test_canonical_store_code_keeps_bare_store_and_unknown(self):
        from src.research_pipeline.runner_adapter import canonical_store_code

        class BareStore:
            def get_security_profile(self, code):
                return {"code": code} if code == "600519" else None

        assert canonical_store_code(BareStore(), "600519") == "600519"    # 裸码库
        assert canonical_store_code(None, "600519") == "600519"           # 无库不探测
        assert canonical_store_code(BareStore(), "600519.SH") == "600519.SH"  # 已带后缀原样

        class EmptyStore:
            def get_security_profile(self, code):
                return None

        # 全不命中：原样返回（宁可 empty 信封亮缺口，不猜码）
        assert canonical_store_code(EmptyStore(), "600519") == "600519"


class TestPipelineResearchRunner:
    def test_full_five_stage_run(self, tmp_path):
        llm = FakeLLM(_full_llm_script())
        events = []
        runner = PipelineResearchRunner(llm=llm, store=object(), runs_root=tmp_path / "runs",
                                        fetch_registry=_registry())
        output = runner.run(_request({"id": "plan-e2e", "code": "300750"}), emit=events.append)

        run_dir = tmp_path / "runs" / "plan-e2e"
        assert (run_dir / "report.md").is_file()
        assert (run_dir / "stages" / "profile.json").is_file()
        assert (run_dir / "calcs" / "01_vol.json").is_file()
        assert verify_protected(run_dir) == []
        # funds_sentiment 有 optional 缺口（zb/dt/yzt 池）→ 报告状态档归一为 incomplete
        first_line = (run_dir / "report.md").read_text(encoding="utf-8").splitlines()[0]
        assert "incomplete" in first_line

        assert output.model == "fake-researcher"
        assert "五阶段整合完成" in output.summary
        assert [c["stage"] for c in output.conclusions] == ["profile", "valuation", "funds_sentiment", "risk"]
        assert output.conclusions[0]["calculation_ids"] == [VOL_ID, MDD_ID]
        ev_ids = {e["id"] for e in output.evidence}
        assert {"ev-security_profile-0", "ev-pool_zt_today-0"} <= ev_ids
        assert any("净流出" in r for r in output.risks)
        # 事件贯穿任务系统（带 type 键）
        kinds = [e["type"] for e in events]
        assert "pipeline_started" in kinds and kinds.count("pipeline_stage_started") == 5

    def test_failure_raises_for_orchestrator(self, tmp_path):
        llm = FakeLLM([[("say", "不干了")], [("say", "还是不干")]])  # probe 永不写产物
        runner = PipelineResearchRunner(llm=llm, store=object(), runs_root=tmp_path / "runs",
                                        fetch_registry=_registry(),
                                        stop_limits={"max_idle": 1, "max_total": 1})
        with pytest.raises(RuntimeError, match="管线未完成"):
            runner.run(_request({"id": "p-fail", "code": "300750"}))


class TestDispatchRunner:
    def test_branches_by_plan_pipeline(self):
        class _Default:
            def run(self, request, emit=None, cancel=None):
                return "default"

        class _Pipeline:
            def run(self, request, emit=None, cancel=None):
                return "pipeline"

        dispatch = PipelineDispatchRunner(default_runner=_Default(), pipeline_runner=_Pipeline())
        assert dispatch.run(_request({"pipeline": A_STOCK_DEEP_RESEARCH})) == "pipeline"
        assert dispatch.run(_request({"execution_mode": "agent"})) == "default"
        assert dispatch.run(_request({})) == "default"


# ---------------------------------------------------------------------------
# 挂真任务系统（ResearchOrchestrator）端到端
# ---------------------------------------------------------------------------

class _Search:
    def search(self, question, limit=10):
        from types import SimpleNamespace
        return SimpleNamespace(items=[], source="data_hub", interpretation=[])


def _wait(orchestrator, user_id, task_id):
    for _ in range(200):
        task = orchestrator.get(user_id, task_id)
        if task.status in {"succeeded", "failed", "cancelled"}:
            return task
        time.sleep(0.01)
    raise AssertionError("task did not finish")


def test_orchestrator_runs_pipeline_and_persists_output(tmp_path):
    from src.product.research_orchestrator import ResearchOrchestrator
    from src.product.research_tasks import ResearchTaskService
    from src.product.store import ProductStore

    llm = FakeLLM(_full_llm_script())
    pipeline = PipelineResearchRunner(llm=llm, store=object(), runs_root=tmp_path / "runs",
                                      fetch_registry=_registry())
    default_calls = []

    class _Default:
        def run(self, request, emit=None, cancel=None):
            default_calls.append(request)
            raise AssertionError("default runner should not be used")

    store = ProductStore(tmp_path / "product.db")
    service = ResearchTaskService(store, _Search())
    orchestrator = ResearchOrchestrator(
        store, service, runner_factory=lambda: PipelineDispatchRunner(
            default_runner=_Default(), pipeline_runner=pipeline),
    )
    task = orchestrator.start(
        "u1", question="深研 300750", template_id=None, scope={}, constraints=[],
        idempotency_key="pipe-1",
        plan={"execution_mode": "agent", "pipeline": A_STOCK_DEEP_RESEARCH,
              "id": "plan-orc", "code": "300750"},
    )
    assert _wait(orchestrator, "u1", task.id).status == "succeeded"
    assert default_calls == []

    result = service.result("u1", task.id)
    assert result.execution_mode == "agent"
    assert [c["stage"] for c in result.conclusions] == ["profile", "valuation", "funds_sentiment", "risk"]
    assert result.agent_evidence and result.agent_evidence[0]["id"].startswith("ev-")
    assert result.model == "fake-researcher"
    assert (tmp_path / "runs" / "plan-orc" / "report.md").is_file()
    # 管线事件进了任务事件流（SSE 可见）
    kinds = [e["type"] for e in orchestrator.events("u1", task.id)]
    assert "pipeline_stage_started" in kinds and kinds[-1] == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
