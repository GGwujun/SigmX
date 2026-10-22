# -*- coding: utf-8 -*-
"""A 股插件视角的受控工具行为：真 schema 拦截、calc 记录与引用链、报告阶段工具边界。"""

import json
from pathlib import Path

import pytest

from src.research_pipeline.calc import calculation_id
from src.research_pipeline.plugins.a_stock import a_stock_plugin
from src.research_pipeline.run_tools import (RunToolsError, TurnContext,
                                             call_run_tool)


def _ctx(tmp_path, stage):
    run_dir = tmp_path / "run"
    for sub in ("fetch", "calcs", "stages"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return TurnContext(run_dir=str(run_dir), stage=stage, plugin=a_stock_plugin)


def _seed_profile_evidence(ctx):
    (Path(ctx.run_dir) / "fetch" / "bars_daily_90d.json").write_text(json.dumps({
        "dataset": "bars_daily_90d", "status": "ok", "rows": 2,
        "evidence": [{"id": "ev-bars_daily_90d-0", "data": {"close": 100.0}},
                     {"id": "ev-bars_daily_90d-1", "data": {"close": 110.0}}],
    }, ensure_ascii=False), encoding="utf-8")


PROFILE_MIN = {
    "stage": "profile", "summary": "近 90 日震荡。",
    "trend": "range", "volatility_pct": 30.0, "data_freshness": "fresh",
    "evidence_ids": ["ev-bars_daily_90d-0"],
}


class TestWriteStageSchema:
    def test_profile_ok(self, tmp_path):
        ctx = _ctx(tmp_path, "profile")
        _seed_profile_evidence(ctx)
        out = call_run_tool(ctx, "write_stage", {"stage_output": PROFILE_MIN})
        assert out["written"] == "stages/profile.json"

    def test_profile_missing_required_field_rejected(self, tmp_path):
        ctx = _ctx(tmp_path, "profile")
        bad = {k: v for k, v in PROFILE_MIN.items() if k != "trend"}
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "write_stage", {"stage_output": bad})
        assert ei.value.code == "stage_schema_invalid"
        assert not list((Path(ctx.run_dir) / "stages").glob("*.json"))

    def test_profile_bad_enum_rejected(self, tmp_path):
        ctx = _ctx(tmp_path, "profile")
        bad = dict(PROFILE_MIN, trend="moon")
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "write_stage", {"stage_output": bad})
        assert ei.value.code == "stage_schema_invalid"

    def test_risk_decision_points_min_items(self, tmp_path):
        ctx = _ctx(tmp_path, "risk")
        bad = {"stage": "risk", "summary": "反证。",
               "counter_evidence": ["一条"], "decision_points": ["只有一条", "第二条"],
               "source_conflicts": []}
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "write_stage", {"stage_output": bad})
        assert ei.value.code == "stage_schema_invalid"


class TestCalculateAndRefs:
    def test_percentile_rank_records_and_citable(self, tmp_path):
        ctx = _ctx(tmp_path, "valuation")
        out = call_run_tool(ctx, "calculate", {
            "function": "percentile_rank",
            "args": {"value": 44.0, "series": [45.0, 46.0, 44.0]},
            "output_file": "01_pe_rank.json"})
        expect_id = calculation_id("percentile_rank",
                                   {"value": 44.0, "series": [45.0, 46.0, 44.0]})
        assert out["calculation_id"] == expect_id
        rec = json.loads((Path(ctx.run_dir) / "calcs" / "01_pe_rank.json").read_text(encoding="utf-8"))
        assert rec["calculation_id"] == expect_id and rec["status"] == "ok"
        assert abs(rec["value"] - 100.0 / 3) < 1e-9   # 窗口内 1/3 的值 ≤ 44（含自身）

    def test_unknown_calc_function_records_error_envelope(self, tmp_path):
        """未知函数不炸：error 信封也是审计痕迹，落盘供 validator/守卫看见。"""
        ctx = _ctx(tmp_path, "profile")
        rec = call_run_tool(ctx, "calculate", {"function": "predict_future",
                                               "args": {"days": 30}, "output_file": "01_p.json"})
        assert rec["status"] == "error"
        assert "未知函数" in str(rec.get("reason"))
        assert (Path(ctx.run_dir) / "calcs" / "01_p.json").is_file()

    def test_bad_output_file_rejected(self, tmp_path):
        ctx = _ctx(tmp_path, "profile")
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "calculate", {"function": "ratio", "args": {"a": 1, "b": 2},
                                             "output_file": "../escape.json"})
        assert ei.value.code == "bad_output_file"


class TestReportStageTools:
    def test_report_tool_only_in_report_stage(self, tmp_path):
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(_ctx(tmp_path, "profile"), "write_report", {"markdown": "# x"})
        assert ei.value.code == "wrong_stage"

    def test_report_first_write_needs_stage_output(self, tmp_path):
        ctx = _ctx(tmp_path, "report")
        with pytest.raises(RunToolsError) as ei:
            call_run_tool(ctx, "write_report", {"markdown": "# 只有正文"})
        assert ei.value.code == "report_stage_missing"

    def test_read_run_file_whitelist(self, tmp_path):
        ctx = _ctx(tmp_path, "profile")
        _seed_profile_evidence(ctx)
        out = call_run_tool(ctx, "read_run_file", {"path": "fetch/bars_daily_90d.json"})
        assert "ev-bars_daily_90d-0" in out["text"]
        for bad in ("fetch/bars_daily_90d.json.bak", "fetch/../../_ledger.json",
                    "calcs/../../stages/profile.json"):
            with pytest.raises(RunToolsError) as ei:
                call_run_tool(ctx, "read_run_file", {"path": bad})
            assert ei.value.code == "path_not_allowed"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
