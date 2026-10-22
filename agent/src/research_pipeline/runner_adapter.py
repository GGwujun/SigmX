# -*- coding: utf-8 -*-
"""runner 适配层：把六阶段管线挂进既有任务系统。

契约对齐 ``src.research_agent.runner``：
``run(ResearchRunRequest, emit, cancel) -> AgentResearchOutput``——
任务状态机/事件落库/SSE/retry/幂等全部白拿，编排器零改动。

分流键：``plan["pipeline"] == "a_stock_deep_research"`` 时走本管线
（见 ``PipelineDispatchRunner``），否则原 ResearchAgentRuntime。
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .orchestrator import PipelineConfig, run_pipeline
from .plugin import ResearchPlugin
from .plugins.a_stock import A_STOCK_DEEP_RESEARCH, a_stock_plugin
from .validator import load_run_view

_CODE_RE = re.compile(r"\b[0-9]{6}\b")

# 证据行上限：bars 90 + daily_basic 90 + 资金流 20 + 池/公告，正常不过 300；
# 截断保 research_agent_outputs 不被整段行情刷爆
_MAX_EVIDENCE_ROWS = 400


def default_runs_root() -> Path:
    root = os.getenv("SIGMX_PIPELINE_RUNS_DIR")
    if root:
        return Path(root)
    return Path.home() / ".vibe-trading" / "pipeline_runs"


def resolve_code(plan: dict, question: str) -> str:
    """从 plan 或问题文本解析 6 位标的代码。深研管线必须有明确标的。"""
    code = str((plan or {}).get("code") or "").strip()
    if _CODE_RE.fullmatch(code):
        return code
    m = _CODE_RE.search(question or "")
    if m:
        return m.group(0)
    raise ValueError("a_stock 深研管线需要 6 位股票代码（plan.code 或问题文本中给出）")


@dataclass
class PipelineResearchRunner:
    """把一次研究任务跑成六阶段管线，并把产物组装成 AgentResearchOutput。"""

    llm: Any                                  # ChatLLM 兼容（或产出它的工厂）
    store: Any = None                         # MarketStore（None → critical 取数失败）
    plugin: ResearchPlugin = None
    runs_root: "str | Path | None" = None
    fetch_registry: "dict | None" = None      # 测试注入合成取数
    methodology_dir: "str | Path | None" = None
    stop_limits: "dict | None" = None         # 收工守卫上限（测试收紧用）

    def __post_init__(self) -> None:
        if self.plugin is None:
            self.plugin = a_stock_plugin
        if callable(self.llm) and not hasattr(self.llm, "chat"):
            self.llm = self.llm()

    def run(self, request: Any, emit: "Callable[[dict], None] | None" = None,
            cancel: "Callable[[], bool] | None" = None) -> Any:
        from src.research_agent.runner import AgentResearchOutput  # 局部导入避免环

        plan = getattr(request, "plan", None) or {}
        question = getattr(request, "question", "") or ""
        code = resolve_code(plan, question)
        task_ref = str(plan.get("id") or f"pipeline-{uuid.uuid4().hex[:12]}")
        run_dir = Path(self.runs_root or default_runs_root()) / task_ref

        cfg = PipelineConfig(
            task_id=task_ref, code=code, plugin=self.plugin, llm=self.llm,
            run_dir=run_dir, trade_date=plan.get("trade_date"),
            emit=emit, cancel=cancel, store=self.store,
            fetch_registry=self.fetch_registry,
            methodology_dir=self.methodology_dir,
            stop_limits=self.stop_limits,
        )
        result = run_pipeline(cfg)
        if result.status != "completed":
            raise RuntimeError(f"六阶段研究管线未完成: {result.error or result.status}")

        view = load_run_view(run_dir)
        # summary 优先用 report 阶段产物里的摘要（编排器已校验），否则退化到报告首段
        report_out = view.stage_outputs.get(self.plugin.report_stage) or {}
        summary = str(report_out.get("summary") or "").strip() or "六阶段研究管线已完成"
        return AgentResearchOutput(
            summary=summary,
            conclusions=_conclusions(view, self.plugin),
            evidence=_evidence(view),
            risks=_risks(view),
            model=getattr(self.llm, "model_name", None),
        )


def _conclusions(view: Any, plugin: ResearchPlugin) -> "list[dict]":
    out: "list[dict]" = []
    for stage in plugin.stages:
        if stage == plugin.report_stage:
            continue
        output = view.stage_outputs.get(stage)
        if not isinstance(output, dict):
            continue
        out.append({
            "stage": stage,
            "text": str(output.get("summary") or ""),
            "evidence_ids": list(output.get("evidence_ids") or []),
            "calculation_ids": list(output.get("calculation_ids") or []),
            "gaps": list(output.get("gaps") or []),
        })
    return out


def _evidence(view: Any) -> "list[dict]":
    rows: "list[dict]" = []
    for dataset, env in sorted(view.fetch.items()):
        for ev in env.get("evidence") or []:
            rows.append({"id": ev.get("id"), "dataset": dataset, "data": ev.get("data")})
            if len(rows) >= _MAX_EVIDENCE_ROWS:
                return rows
    return rows


def _risks(view: Any) -> "list[str]":
    risk = view.stage_outputs.get("risk") or {}
    out: "list[str]" = []
    out.extend(str(x) for x in risk.get("counter_evidence") or [])
    out.extend(str(x) for x in risk.get("source_conflicts") or [])
    return out


@dataclass
class PipelineDispatchRunner:
    """按 plan["pipeline"] 分流的 runner 外壳：挂载点唯一，既有运行时零改动。"""

    default_runner: Any
    pipeline_runner: Any
    pipeline_key: str = A_STOCK_DEEP_RESEARCH

    def run(self, request: Any, emit: "Callable[[dict], None] | None" = None,
            cancel: "Callable[[], bool] | None" = None) -> Any:
        plan = getattr(request, "plan", None) or {}
        if str(plan.get("pipeline") or "") == self.pipeline_key:
            return self.pipeline_runner.run(request, emit, cancel)
        return self.default_runner.run(request, emit, cancel)
