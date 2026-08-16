from pathlib import Path

import pytest

from src.harness.store import HarnessStore, InvalidRunTransition


def test_harness_run_persists_full_observability_record(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path / "harness.db", now=lambda: "2026-08-16T03:00:00+00:00")

    run = store.create_run(
        user_id="u1",
        run_type="research", title="贵州茅台完整研究", goal="验证估值与盈利质量",
        context_manifest={"current_symbol": "600519.SH", "data_versions": {"bars_daily": "20260814"}},
    )
    store.start_run(run.id)
    step = store.add_step(run.id, title="读取财务数据", status="running")
    store.add_tool_call(run.id, step_id=step.id, tool_id="datahub.financial_snapshot", status="succeeded", duration_ms=82, input_data={"code": "600519.SH"}, output_ref="data://financial/600519")
    store.add_evidence(run.id, kind="dataset", title="财务快照", ref="data://financial/600519", source="Data Hub", data_version="20260814")
    store.add_artifact(run.id, kind="report", name="研究报告", ref="artifact://r1/report.md")
    store.add_cost(run.id, dimension="data_credit", amount=3)
    store.add_degradation(run.id, code="NEWS_DELAYED", message="新闻源延迟 15 分钟")
    store.add_governance_event(run.id, level="simulate", decision="allowed", reason="只读研究")
    completed = store.finish_run(run.id, result_ref="artifact://r1/report.md")

    assert completed.status == "succeeded"
    detail = store.get_run(run.id)
    assert detail.steps[0].title == "读取财务数据"
    assert detail.tool_calls[0].duration_ms == 82
    assert detail.evidence[0].data_version == "20260814"
    assert detail.artifacts[0].name == "研究报告"
    assert detail.costs == {"data_credit": 3.0}
    assert detail.degradations[0].code == "NEWS_DELAYED"
    assert detail.governance_events[0].decision == "allowed"


def test_harness_run_rejects_invalid_terminal_transition(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path / "harness.db")
    run = store.create_run(user_id="u1", run_type="backtest", title="因子回测", goal="验证因子")
    store.cancel_run(run.id)

    with pytest.raises(InvalidRunTransition):
        store.start_run(run.id)


def test_harness_runs_are_filterable_by_type_and_status(tmp_path: Path) -> None:
    store = HarnessStore(tmp_path / "harness.db")
    research = store.create_run(user_id="u1", run_type="research", title="研究", goal="研究")
    backtest = store.create_run(user_id="u1", run_type="backtest", title="回测", goal="回测")
    store.create_run(user_id="u2", run_type="research", title="别人的研究", goal="隔离")
    store.start_run(research.id)
    store.finish_run(research.id, result_ref="artifact://research")

    assert [run.id for run in store.list_runs(user_id="u1", run_type="research", status="succeeded")] == [research.id]
    assert [run.id for run in store.list_runs(user_id="u1", run_type="backtest")] == [backtest.id]
    assert store.get_run(research.id, user_id="u2") is None
