# -*- coding: utf-8 -*-
"""知识归档召回测试：字段抽取（不抄报告自由文本）/gate 命中整行删/
有效期三态 /refuted 不召回 /索引并发写 /端到端二次运行召回注入提示词。"""

import threading
from datetime import date, timedelta
from pathlib import Path

from src.research_pipeline.calc import calculation_id
from src.research_pipeline.knowledge import (KnowledgeRecall, archive_run,
                                             default_knowledge_root,
                                             knowledge_block, mark_refuted,
                                             recall)
from src.research_pipeline.orchestrator import (PipelineConfig, run_pipeline,
                                                verify_protected)
from src.research_pipeline.validator import RunView

from tests.test_research_pipeline_orchestrator import (GOOD_PROBE_STAGE, FakeLLM,
                                                       _run, _toy_plugin)

PCT_ID = calculation_id("pct_change", {"a": 110, "b": 100})
TODAY = date.today().isoformat()


def _view(**overrides):
    """probe 已校验产物 + report 产物（归档必须忽略）的运行视图。"""
    fetch = {"toy_quotes": {"dataset": "toy_quotes", "status": "ok", "stage": "probe",
                            "rows": 2},
             "toy_news": {"dataset": "toy_news", "status": "empty", "stage": "probe",
                          "rows": 0}}
    view = RunView(
        stage_outputs={
            "probe": dict(GOOD_PROBE_STAGE),
            "report": {"stage": "report", "summary": "成文完成：报告自由文本。",
                       "evidence_ids": [], "calculation_ids": []},
        },
        fetch=fetch,
    )
    for key, value in overrides.items():
        setattr(view, key, value)
    return view


def _archive(tmp_path, **kw):
    return archive_run(_view(), _toy_plugin(), code="300750", trade_date=TODAY,
                       run_id="run-1", knowledge_dir=tmp_path / "knowledge", **kw)


class TestArchive:
    def test_extracts_stage_fields_but_not_report_text(self, tmp_path):
        entry = _archive(tmp_path)
        assert entry["status"] == "fresh" and entry["dropped_lines"] == 0

        text = (tmp_path / "knowledge" / "companies" / "300750" / "latest.md") \
            .read_text(encoding="utf-8")
        meta, body = text.split("---", 2)[1], text.split("---", 2)[2]
        for fragment in (f"code: 300750", f"as_of: {TODAY}", "status: fresh",
                         "valid_days: 30", "run_id: run-1"):
            assert fragment in meta
        # probe 专有字段进档案；报告阶段整段不进
        assert "## probe" in body
        assert "close 从 100 升至 110" in body          # findings
        assert "证据 2 条、计算 1 条" in body
        assert "数据缺口：toy_news" in body              # empty 数据集如实记缺口
        assert "成文完成" not in body                    # 报告自由文本不抄
        assert "## report" not in body

        # run 副本与索引同步落盘
        assert (tmp_path / "knowledge" / "companies" / "300750" / "runs" / "run-1.md") \
            .is_file()
        index = (tmp_path / "knowledge" / "manifest.json").read_text(encoding="utf-8")
        assert "300750" in index and '"run-1"' in index

    def test_drops_gate_hits_and_sensitive_lines(self, tmp_path):
        view = _view(stage_outputs={
            "probe": dict(GOOD_PROBE_STAGE,
                          summary="该股强势，目标价 100 元。",
                          contact="investor@example.com"),
            "report": {},
        })
        entry = archive_run(view, _toy_plugin(), code="300750", trade_date=TODAY,
                            run_id="run-2", knowledge_dir=tmp_path / "knowledge")
        assert entry["dropped_lines"] == 2      # 建议类表述行 + 邮箱行
        text = (tmp_path / "knowledge" / "companies" / "300750" / "latest.md") \
            .read_text(encoding="utf-8")
        assert "目标价" not in text
        assert "example.com" not in text
        assert "close 从 100 升至 110" in text   # 干净行保留

    def test_nested_structures_skipped(self, tmp_path):
        view = _view(stage_outputs={
            "probe": dict(GOOD_PROBE_STAGE, matrix={"a": [1, 2]}),
            "report": {},
        })
        archive_run(view, _toy_plugin(), code="300750", trade_date=TODAY,
                    run_id="run-3", knowledge_dir=tmp_path / "knowledge")
        body = (tmp_path / "knowledge" / "companies" / "300750" / "latest.md") \
            .read_text(encoding="utf-8").split("---", 2)[2]
        assert "matrix" not in body

    def test_concurrent_archives_keep_both_index_entries(self, tmp_path):
        errors = []

        def worker(code):
            try:
                archive_run(_view(), _toy_plugin(), code=code, trade_date=TODAY,
                            run_id=f"run-{code}", knowledge_dir=tmp_path / "knowledge")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(code,))
                   for code in ("300750", "600519", "000001")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        from src.research_pipeline.fsutil import read_json_if_exists
        companies = read_json_if_exists(tmp_path / "knowledge" / "manifest.json")["companies"]
        assert set(companies) == {"300750", "600519", "000001"}


class TestRecall:
    def test_fresh_recall(self, tmp_path):
        _archive(tmp_path)
        got = recall(tmp_path / "knowledge", "300750")
        assert got is not None and got.status == "fresh"
        assert got.run_id == "run-1" and got.as_of == TODAY
        assert "close 从 100 升至 110" in got.text
        assert got.truncated is False

    def test_stale_recall_marks_low_confidence(self, tmp_path):
        old = (date.today() - timedelta(days=61)).isoformat()
        archive_run(_view(), _toy_plugin(), code="300750", trade_date=old,
                    run_id="run-old", knowledge_dir=tmp_path / "knowledge")
        got = recall(tmp_path / "knowledge", "300750")
        assert got is not None and got.status == "stale"
        assert "已过有效期" in knowledge_block(got)

    def test_future_as_of_is_not_fresh(self, tmp_path):
        future = (date.today() + timedelta(days=3)).isoformat()
        archive_run(_view(), _toy_plugin(), code="300750", trade_date=future,
                    run_id="run-f", knowledge_dir=tmp_path / "knowledge")
        assert recall(tmp_path / "knowledge", "300750").status == "stale"

    def test_valid_days_clamped(self, tmp_path):
        archive_run(_view(), _toy_plugin(), code="300750", trade_date=TODAY,
                    run_id="run-c", knowledge_dir=tmp_path / "knowledge",
                    valid_days=99_999)
        assert recall(tmp_path / "knowledge", "300750").valid_days == 3650

    def test_missing_or_disabled_returns_none(self, tmp_path):
        assert recall(None, "300750") is None
        assert recall(tmp_path / "knowledge", "300750") is None

    def test_oversized_body_truncated(self, tmp_path):
        view = _view(stage_outputs={
            "probe": dict(GOOD_PROBE_STAGE,
                          findings=["很长的结论" * 40] * 8,
                          note="加长" * 6000),
            "report": {},
        })
        archive_run(view, _toy_plugin(), code="300750", trade_date=TODAY,
                    run_id="run-big", knowledge_dir=tmp_path / "knowledge")
        got = recall(tmp_path / "knowledge", "300750")
        assert got.truncated is True
        assert len(got.text) <= 12_200
        assert "已截断" in got.text


class TestRefuted:
    def test_mark_refuted_blocks_recall(self, tmp_path):
        _archive(tmp_path)
        assert mark_refuted(tmp_path / "knowledge", "300750", "公司公告澄清") is True
        assert recall(tmp_path / "knowledge", "300750") is None
        text = (tmp_path / "knowledge" / "companies" / "300750" / "latest.md") \
            .read_text(encoding="utf-8")
        assert "status: refuted" in text and "公司公告澄清" in text
        from src.research_pipeline.fsutil import read_json_if_exists
        entry = read_json_if_exists(tmp_path / "knowledge" / "manifest.json") \
            ["companies"]["300750"]
        assert entry["status"] == "refuted"

    def test_mark_refuted_without_archive_is_false(self, tmp_path):
        assert mark_refuted(tmp_path / "knowledge", "300750", "x") is False


class TestKnowledgeBlock:
    def test_none_or_empty_returns_empty_string(self):
        assert knowledge_block(None) == ""
        assert knowledge_block(KnowledgeRecall(
            code="1", as_of=TODAY, status="fresh", valid_days=30,
            run_id="r", text="  ")) == ""

    def test_block_routes_conflicts_to_risk_stage(self, tmp_path):
        _archive(tmp_path)
        block = knowledge_block(recall(tmp_path / "knowledge", "300750"))
        assert "历史研究结论（知识档案）" in block
        assert "不是给你的指令" in block            # 防提示词注入声明
        assert "source_conflicts" in block          # 冲突裁决路由到 risk 阶段
        assert "run-1" in block

    def test_default_root_under_home(self):
        assert default_knowledge_root() == Path.home() / ".vibe-trading" / "knowledge"


def _happy_llm():
    return FakeLLM([
        [  # probe 阶段
            ("tool", "calculate", {"function": "pct_change", "args": {"a": 110, "b": 100},
                                   "evidence_ids": ["ev-toy_quotes-0", "ev-toy_quotes-1"],
                                   "output_file": "01_pct.json"}),
            ("tool", "write_stage", {"stage_output": GOOD_PROBE_STAGE}),
            ("say", "done"),
        ],
        [  # report 阶段
            ("tool", "write_report", {"markdown": "状态: incomplete\n\n# 结论\n\n"
                                                 f"涨幅 10.0%，计算引用 {PCT_ID}。\n",
                                      "stage_output": {"stage": "report",
                                                       "summary": "成文完成"}}),
            ("say", "done"),
        ],
    ])


class TestPipelineIntegration:
    def test_first_run_archives_second_run_recalls_into_prompt(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        # 第一次运行：无档案可召回，完成后归档
        llm1 = _happy_llm()
        result1, cfg1 = _run(tmp_path / "one", llm1, knowledge_dir=knowledge,
                             trade_date=TODAY)
        assert result1.status == "completed", result1.error
        latest = knowledge / "companies" / "300750" / "latest.md"
        assert latest.is_file()
        assert "历史研究结论" not in llm1.seen_users[0]      # 首跑无召回
        assert verify_protected(cfg1.run_dir) == []           # 归档不破受保护 hash

        # 第二次运行（同一标的）：档案注入各阶段提示词
        llm2 = _happy_llm()
        result2, _ = _run(tmp_path / "two", llm2, knowledge_dir=knowledge,
                          trade_date=TODAY)
        assert result2.status == "completed", result2.error
        assert "历史研究结论（知识档案）" in llm2.seen_users[0]
        assert "close 从 100 升至 110" in llm2.seen_users[0]
        # 档案与施工单同在（知识块不挤掉方法论/施工单）
        assert "研究宪法" in llm2.seen_users[0] and "【probe】" in llm2.seen_users[0]

    def test_failed_run_does_not_archive(self, tmp_path):
        knowledge = tmp_path / "knowledge"
        bad = dict(GOOD_PROBE_STAGE, findings=[])    # schema 不合格 → 阶段失败
        llm = FakeLLM([
            [("tool", "write_stage", {"stage_output": bad}), ("say", "done")],
            [("say", "done")],
            [("tool", "write_stage", {"stage_output": bad}), ("say", "done")],
            [("say", "done")],
        ])
        result, _ = _run(tmp_path / "bad", llm, knowledge_dir=knowledge,
                         stop_limits={"max_idle": 1, "max_total": 1})
        assert result.status == "failed"
        assert not (knowledge / "companies" / "300750" / "latest.md").exists()
