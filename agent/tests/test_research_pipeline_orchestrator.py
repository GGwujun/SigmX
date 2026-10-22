# -*- coding: utf-8 -*-
"""六阶段编排器 Core 测试：toy 插件 + 合成取数 + FakeLLM 状态机，全程无网络。"""

import json
from pathlib import Path

import pytest
from src.providers.chat import LLMResponse, ToolCallRequest

from src.research_pipeline.calc import calculation_id
from src.research_pipeline.orchestrator import (PipelineConfig, run_pipeline,
                                                 verify_protected)
from src.research_pipeline.plugin import (ResearchPlugin, StageDatasets,
                                          StageSchema, validate_plugin)
from src.research_pipeline.run_tools import (RunToolsError, TurnContext,
                                             call_run_tool)
from src.research_pipeline.stage_loop import run_stage_turn
from src.research_pipeline.stop_guard import StopGuard


# ---------------------------------------------------------------------------
# 脚手架：toy 插件 / 合成取数 / FakeLLM
# ---------------------------------------------------------------------------

def _toy_plugin():
    return ResearchPlugin(
        id="toy",
        stages=("probe", "report"),
        report_stage="report",
        stage_datasets={
            "probe": StageDatasets(required=("toy_quotes",), optional=("toy_news",)),
            "report": StageDatasets(),
        },
        critical_datasets=("toy_quotes",),
        stage_schemas={
            "probe": StageSchema(
                properties={"findings": {"type": "array", "items": {"type": "string"},
                                         "minItems": 1}},
                required=("findings",),
            ),
        },
        report_sections=("结论",),
        build_stage_prompt=lambda stage, cfg: f"【{stage}】研究 {cfg.get('code')}：读数据、算数、写产物。",
    )


def _toy_fetch_registry():
    return {
        "toy_quotes": lambda store, code, td: [{"close": 100.0}, {"close": 110.0}],
        "toy_news": lambda store, code, td: [{"title": "中性消息"}],
    }


class FakeLLM:
    """脚本化模型：按队列回放，队列每个元素是一段回复列表（= 一次收工尝试的脚本）；
    回复 = ("tool", name, args) 或 ("say", text)。每次 chat 记录对话里最后一条
    user 消息（prompt 或收工检查的打回消息），供断言反馈注入。"""

    def __init__(self, turns):
        self.turns = list(turns)
        self.seen_users = []
        self._current = None

    def chat(self, messages, tools=None, timeout=None):
        if self._current is None:
            if not self.turns:
                raise AssertionError("FakeLLM 脚本用尽（编排器多跑了一段对话）")
            self._current = list(self.turns.pop(0))
        users = [m for m in messages if m.get("role") == "user"]
        self.seen_users.append(str(users[-1].get("content", "")) if users else "")
        kind, name_or_text, *rest = self._current.pop(0)
        if kind == "tool":
            call = ToolCallRequest(id=f"call-{len(self.seen_users)}-{len(name_or_text)}",
                                   name=name_or_text, arguments=rest[0] if rest else {})
            resp = LLMResponse(content="", tool_calls=[call], finish_reason="tool_calls")
        else:
            resp = LLMResponse(content=name_or_text, tool_calls=[], finish_reason="stop")
        if not self._current:
            self._current = None
        return resp


PCT_ID = calculation_id("pct_change", {"a": 110, "b": 100})

GOOD_PROBE_STAGE = {
    "stage": "probe", "summary": "读数完成，涨幅 10.0%。",
    "findings": ["close 从 100 升至 110"],
    "evidence_ids": ["ev-toy_quotes-0", "ev-toy_quotes-1"],
    "calculation_ids": [PCT_ID],
}


def _good_report_md(calc_id=PCT_ID):
    return (
        "状态: incomplete\n\n# 结论\n\n两期收盘 100 与 110，涨幅 10.0%。"
        f"计算引用 {calc_id}。\n"
    )


def _run(tmp_path, llm, plugin=None, **kw):
    cfg = PipelineConfig(
        task_id="task-test", code="300750", plugin=plugin or _toy_plugin(),
        llm=llm, run_dir=tmp_path / "run",
        store=object(),          # 合成取数不碰 store，但取数层要求非 None
        fetch_registry=_toy_fetch_registry(),
        methodology_dir=None,   # 用仓库内 agent/methodology
        **kw,
    )
    return run_pipeline(cfg), cfg


# ---------------------------------------------------------------------------
# 插件注册期校验
# ---------------------------------------------------------------------------

class TestValidatePlugin:
    def test_toy_plugin_ok(self):
        assert validate_plugin(_toy_plugin()) == []

    def test_report_stage_must_be_last(self):
        p = _toy_plugin()
        object.__setattr__(p, "stages", ("report", "probe"))
        errs = validate_plugin(p)
        assert any("最后一个阶段" in e for e in errs)

    def test_missing_stage_dataset_key(self):
        p = _toy_plugin()
        object.__setattr__(p, "stage_datasets", {"probe": StageDatasets()})
        errs = validate_plugin(p)
        assert any("缺少阶段" in e and "report" in e for e in errs)

    def test_critical_not_planned(self):
        p = _toy_plugin()
        object.__setattr__(p, "critical_datasets", ("nope_ds",))
        errs = validate_plugin(p)
        assert any("nope_ds" in e for e in errs)

    def test_required_without_property(self):
        p = _toy_plugin()
        object.__setattr__(p, "stage_schemas", {
            "probe": StageSchema(properties={}, required=("ghost",))})
        errs = validate_plugin(p)
        assert any("ghost" in e for e in errs)

    def test_bad_stage_name(self):
        p = _toy_plugin()
        object.__setattr__(p, "stages", ("../evil", "report"))
        errs = validate_plugin(p)
        assert any("安全路径段" in e for e in errs)


# ---------------------------------------------------------------------------
# 编排器主循环
# ---------------------------------------------------------------------------

class TestRunPipeline:
    def test_happy_path(self, tmp_path):
        llm = FakeLLM([
            [  # probe 阶段
                ("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                       "evidence_ids": ["ev-toy_quotes-0", "ev-toy_quotes-1"],
                                       "output_file": "01_pct.json"}),
                ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}),
                ("say", "done"),
            ],
            [  # report 阶段
                ("tool", "write_report", {"markdown": _good_report_md(),
                                          "stage_output": {"stage": "report",
                                                           "summary": "成文完成"}}),
                ("say", "done"),
            ],
        ])
        result, cfg = _run(tmp_path, llm)
        assert result.status == "completed", result.error
        assert result.stages["probe"].status == "completed"
        assert result.stages["report"].status == "completed"
        assert (Path(cfg.run_dir) / "report.md").is_file()
        assert (Path(cfg.run_dir) / "calcs" / "01_pct.json").is_file()
        assert (Path(cfg.run_dir) / "fetch" / "toy_quotes.json").is_file()
        # 报告首行状态档被编排器确定性归一（两阶段全 completed → complete）
        first_line = (Path(cfg.run_dir) / "report.md").read_text(encoding="utf-8").splitlines()[0]
        assert "complete" in first_line and "incomplete" not in first_line
        # 受保护产物对账通过
        assert verify_protected(cfg.run_dir) == []
        # 方法论注入了提示词
        assert "研究宪法" in llm.seen_users[0] and "calc 计算契约" in llm.seen_users[0]

    def test_validator_rejects_then_retry_fixes(self, tmp_path):
        """守卫拦下（同对话）→ 仍不修 → 空转终止 → 编排器带校验错误补跑 → 修好。"""
        # schema 形状合法（write_stage 拦不住），但摘要带建议类表述 → validator 拦
        bad = dict(GOOD_PROBE_STAGE, summary="该股强势，建议立即买入。")
        good = GOOD_PROBE_STAGE
        calc_call = {"function": "pct_change", "args": {"a": 110, "b": 100},
                     "output_file": "01_pct.json"}
        llm = FakeLLM([
            [("tool", "write_stage", {"stage_output": bad}), ("say", "done")],  # attempt 1 写坏
            [("say", "done")],  # 被打回后仍不修 → 守卫终止本轮
            [("tool", "calculate", calc_call),
             ("tool", "write_stage", {"stage_output": good}), ("say", "done")],  # attempt 2 修好
            [("tool", "write_report", {"markdown": _good_report_md(),
                                       "stage_output": {"stage": "report",
                                                        "summary": "成文完成"}}),
             ("say", "done")],
        ])
        result, cfg = _run(tmp_path, llm, stop_limits={"max_idle": 1, "max_total": 1})
        assert result.status == "completed", result.error
        assert len(result.stages["probe"].attempts) == 2
        # attempt 2 的提示词里带上了上一轮校验错误（补跑反馈）
        assert any("建议类表述" in u for u in llm.seen_users)
        # 守卫的打回消息也进了对话
        assert any("收工检查" in u for u in llm.seen_users)

    def test_stage_fails_after_retries(self, tmp_path):
        bad = dict(GOOD_PROBE_STAGE, findings=[])
        llm = FakeLLM([
            [("tool", "write_stage", {"stage_output": bad}), ("say", "done")],
            [("say", "done")],
            [("tool", "write_stage", {"stage_output": bad}), ("say", "done")],
            [("say", "done")],
        ])
        result, _ = _run(tmp_path, llm, stop_limits={"max_idle": 1, "max_total": 1})
        assert result.status == "failed"
        assert result.stages["probe"].status == "failed"
        assert "report" not in result.stages  # 报告阶段没跑

    def test_critical_dataset_failure_fails_run(self, tmp_path):
        reg = _toy_fetch_registry()
        reg["toy_quotes"] = lambda store, code, td: (_ for _ in ()).throw(RuntimeError("db down"))
        plugin = _toy_plugin()
        cfg = PipelineConfig(task_id="t", code="300750", plugin=plugin, llm=FakeLLM([]),
                             run_dir=tmp_path / "run", store=object(), fetch_registry=reg)
        result = run_pipeline(cfg)
        assert result.status == "failed"
        assert "toy_quotes" in result.error

    def test_methodology_missing_refuses(self, tmp_path):
        cfg = PipelineConfig(task_id="t", code="300750", plugin=_toy_plugin(),
                             llm=FakeLLM([]), run_dir=tmp_path / "run",
                             store=object(), fetch_registry=_toy_fetch_registry(),
                             methodology_dir=tmp_path / "empty-methodology")
        result = run_pipeline(cfg)
        assert result.status == "failed"
        assert "方法论文件缺失" in result.error

    def test_cancel(self, tmp_path):
        llm = FakeLLM([[("say", "x")]])
        result, cfg = _run(tmp_path, llm, cancel=lambda: True)
        assert result.status == "cancelled"

    def test_protected_tamper_detected(self, tmp_path):
        llm = FakeLLM([
            [("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                    "output_file": "01_pct.json"}),
             ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}), ("say", "done")],
            [("tool", "write_report", {"markdown": _good_report_md(),
                                       "stage_output": {"stage": "report",
                                                        "summary": "成文"}}), ("say", "done")],
        ])
        result, cfg = _run(tmp_path, llm)
        assert result.status == "completed"
        # 运行结束后改受保护产物 → 对账不一致
        ledger_file = Path(cfg.run_dir) / "_ledger.json"
        ledger_file.write_text("{}\n", encoding="utf-8")
        problems = verify_protected(cfg.run_dir)
        assert problems and "_ledger.json" in problems[0]

    def test_report_gate_rewrite_loop(self, tmp_path):
        dirty = "状态: incomplete\n\n# 结论\n\n建议立即建仓并设目标价。\n"
        llm = FakeLLM([
            [("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                    "output_file": "01_pct.json"}),
             ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}), ("say", "done")],
            [("tool", "write_report", {"markdown": dirty,
                                       "stage_output": {"stage": "report",
                                                        "summary": "成文"}}), ("say", "done")],
            [  # gate 重写 turn
                ("tool", "write_report", {"markdown": _good_report_md()}),
                ("say", "done"),
            ],
        ])
        result, cfg = _run(tmp_path, llm)
        assert result.status == "completed", result.error
        final = (Path(cfg.run_dir) / "report.md").read_text(encoding="utf-8")
        assert "建仓" not in final
        # 重写提示词带了命中清单
        assert any("合规检查" in u for u in llm.seen_users)

    def test_report_gate_exhausted_fails(self, tmp_path):
        dirty = "状态: incomplete\n\n# 结论\n\n建议立即建仓。\n"
        llm = FakeLLM([
            [("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                    "output_file": "01_pct.json"}),
             ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}), ("say", "done")],
            [("tool", "write_report", {"markdown": dirty,
                                       "stage_output": {"stage": "report",
                                                        "summary": "成文"}}), ("say", "done")],
            [("tool", "write_report", {"markdown": dirty}), ("say", "done")],  # 重写还是脏的
        ])
        result, _ = _run(tmp_path, llm)
        assert result.status == "failed"
        assert "报告" in result.error


# ---------------------------------------------------------------------------
# 收工守卫与空转终止
# ---------------------------------------------------------------------------

class TestStopGuardBehavior:
    def test_block_then_allow(self, tmp_path):
        """第一次想收工被拦（缺产物），补齐产物与证据后放行。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        ctx = TurnContext(run_dir=str(run_dir), stage="probe", plugin=_toy_plugin())
        guard = StopGuard(str(run_dir), "probe", ctx.plugin)
        v1 = guard.check()
        assert v1["decision"] == "block"
        assert any("缺产物" in p for p in v1["problems"])
        (run_dir / "stages").mkdir()
        (run_dir / "fetch").mkdir()
        (run_dir / "calcs").mkdir()
        (run_dir / "fetch" / "toy_quotes.json").write_text(
            json.dumps({"dataset": "toy_quotes", "status": "ok", "rows": 2,
                        "evidence": [{"id": "ev-toy_quotes-0", "data": {"close": 100}},
                                     {"id": "ev-toy_quotes-1", "data": {"close": 110}}]}),
            encoding="utf-8")
        (run_dir / "calcs" / "01_pct.json").write_text(
            json.dumps({"calculation_id": PCT_ID, "fn": "pct_change",
                        "args": {"a": 110, "b": 100}, "status": "ok",
                        "value": 10.0, "unit": "%", "calc_version": "1"}),
            encoding="utf-8")
        (run_dir / "stages" / "probe.json").write_text(
            json.dumps(GOOD_PROBE_STAGE, ensure_ascii=False), encoding="utf-8")
        v2 = guard.check()
        assert v2["decision"] == "allow"

    def test_terminate_on_idle(self, tmp_path):
        """产物一直不写：连续无推进拦截达上限 → terminate。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        plugin = _toy_plugin()
        guard = StopGuard(str(run_dir), "probe", plugin,
                          limits={"max_idle": 2, "max_total": 20})
        decisions = [guard.check()["decision"] for _ in range(3)]
        # 第 1 次 block（首查算推进）、第 2 次 block（streak=2 ≤ max_idle）、第 3 次 terminate
        assert decisions == ["block", "block", "terminate"]

    def test_progress_resets_idle(self, tmp_path):
        """两次拦截之间新增合法 calc 记录 = 推进，空转计数回 1，不终止。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "stages").mkdir()
        (run_dir / "fetch").mkdir()
        (run_dir / "fetch" / "toy_quotes.json").write_text(
            json.dumps({"dataset": "toy_quotes", "status": "ok", "rows": 1,
                        "evidence": [{"id": "ev-toy_quotes-0", "data": {}}]}),
            encoding="utf-8")
        # stage 产物缺失（所以不合格），但每轮落一条新 calc → 一直算推进
        guard = StopGuard(str(run_dir), "probe", _toy_plugin(),
                          limits={"max_idle": 2, "max_total": 20})
        from src.research_pipeline.fsutil import write_json
        for i in range(4):
            write_json(run_dir / "calcs" / f"{i:02d}_c.json",
                       {"calculation_id": f"calc-{'0'*15}{i}", "fn": "ratio",
                        "status": "ok", "value": 1, "unit": "", "calc_version": "1"})
            assert guard.check()["decision"] == "block"


# ---------------------------------------------------------------------------
# 受控工具拦截
# ---------------------------------------------------------------------------

class TestRunToolGuards:
    def _ctx(self, tmp_path, stage="probe"):
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        return TurnContext(run_dir=str(run_dir), stage=stage, plugin=_toy_plugin())

    def test_unknown_tool(self, tmp_path):
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(self._ctx(tmp_path), "shell", {})
        assert ei.value.code == "unknown_tool"

    def test_path_escape_rejected(self, tmp_path):
        for bad in ("../../etc/passwd", "fetch/../report.md", "logs/x.json", "..\\win"):
            with pytest.raises(RunToolsError) as ei:
                call_run_tool(self._ctx(tmp_path), "read_run_file", {"path": bad})
            assert ei.value.code == "path_not_allowed"

    def test_wrong_stage_write(self, tmp_path):
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(self._ctx(tmp_path, stage="probe"), "write_stage",
                          {"stage_output": {"stage": "report", "summary": "x"}})
        assert ei.value.code == "wrong_stage"

    def test_write_report_only_in_report_stage(self, tmp_path):
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(self._ctx(tmp_path, stage="probe"), "write_report",
                          {"markdown": "# x"})
        assert ei.value.code == "wrong_stage"

    def test_calculate_meta_list_not_written(self, tmp_path):
        ctx = self._ctx(tmp_path)
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "calculate", {"function": "list", "args": {},
                                             "output_file": "00_list.json"})
        assert ei.value.code == "not_a_calculation"
        assert not (Path(ctx.run_dir) / "calcs").exists() or \
            not list((Path(ctx.run_dir) / "calcs").glob("*.json"))

    def test_calc_owner_protection(self, tmp_path):
        ctx = self._ctx(tmp_path)
        args = {"function": "ratio", "args": {"a": 6, "b": 3}, "output_file": "01_r.json"}
        call_run_tool(ctx, "calculate", args)
        # 换阶段再写同名文件 → 拒
        ctx2 = TurnContext(run_dir=ctx.run_dir, stage="report", plugin=ctx.plugin)
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx2, "calculate", args)
        assert ei.value.code == "calc_owned_by_other_stage"

    def test_calculate_bad_ref(self, tmp_path):
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(self._ctx(tmp_path), "calculate",
                          {"function": "ratio", "args": {"a": 1, "b": 2},
                           "evidence_ids": ["not-a-ref"], "output_file": "01_r.json"})
        assert ei.value.code == "bad_arguments"

    def test_run_prefix_normalized(self, tmp_path):
        ctx = self._ctx(tmp_path)
        (Path(ctx.run_dir) / "fetch").mkdir(exist_ok=True)
        (Path(ctx.run_dir) / "fetch" / "toy_quotes.json").write_text("{}", encoding="utf-8")
        out = call_run_tool(ctx, "read_run_file", {"path": "RUN/fetch/toy_quotes.json"})
        assert out["text"] == "{}"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])


class TestReportNumberMasking:
    """M3 数字出处遮蔽：报告里对不上已知值池的数字替换〔未核实〕并强制 incomplete。"""

    def _report_md(self, calc_id):
        return ("状态: incomplete\n\n# 结论\n\n两期收盘 100 与 110，涨幅 10.0%。"
                f"计算引用 {calc_id}。另测分位 35.2%。\n")

    def _llm(self, calc_id):
        return FakeLLM([
            [  # probe
                ("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                       "evidence_ids": ["ev-toy_quotes-0", "ev-toy_quotes-1"],
                                       "output_file": "01_pct.json"}),
                ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}),
                ("say", "done"),
            ],
            [  # report：35.2% 无出处
                ("tool", "write_report", {"markdown": self._report_md(calc_id),
                                          "stage_output": {"stage": "report",
                                                           "summary": "成文完成"}}),
                ("say", "done"),
            ],
        ])

    def test_uncited_masked_and_forced_incomplete(self, tmp_path):
        result, cfg = _run(tmp_path, self._llm(PCT_ID))
        assert result.status == "completed", result.error
        report = (Path(cfg.run_dir) / "report.md").read_text(encoding="utf-8")
        assert "35.2" not in report and "〔未核实〕" in report
        assert "100" in report and "10.0%" in report      # bound/derived 不遮
        assert "incomplete" in report.splitlines()[0]     # 遮蔽强制降级状态档
        manifest = json.loads((Path(cfg.run_dir) / "manifest.json")
                              .read_text(encoding="utf-8"))
        assert manifest["unverified_numbers"] == 1
        events = (Path(cfg.run_dir) / "events.jsonl").read_text(encoding="utf-8")
        assert '"masked": 1' in events
        assert verify_protected(cfg.run_dir) == []        # 遮蔽事件在 hash 前

    def test_fully_cited_report_masks_nothing(self, tmp_path):
        llm = FakeLLM([
            [  # probe
                ("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                       "evidence_ids": ["ev-toy_quotes-0", "ev-toy_quotes-1"],
                                       "output_file": "01_pct.json"}),
                ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}),
                ("say", "done"),
            ],
            [("tool", "write_report", {"markdown": _good_report_md(),
                                       "stage_output": {"stage": "report",
                                                        "summary": "成文完成"}}),
             ("say", "done")],
        ])
        result, cfg = _run(tmp_path, llm)
        assert result.status == "completed", result.error
        manifest = json.loads((Path(cfg.run_dir) / "manifest.json")
                              .read_text(encoding="utf-8"))
        assert manifest["unverified_numbers"] == 0
        assert "complete" in (Path(cfg.run_dir) / "report.md") \
            .read_text(encoding="utf-8").splitlines()[0]
