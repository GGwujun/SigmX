# -*- coding: utf-8 -*-
"""编排器主循环（Core）：方法论检查 → 逐阶段（取数 → attempt 循环 → 校验）
→ 报告阶段 gate 重写循环 → 受保护产物终检。

状态**确定性推导**：阶段合格与否一律由 validator 重读磁盘产物判定，
不以 agent 自报为准（它连"我做完了"都只是说法）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.compliance.gate import (compliance_gate, missing_sections,
                                 normalize_report_status, report_status_token)

from .fetchers import fetch_dataset, write_fetch
from .knowledge import KnowledgeRecall, archive_run, knowledge_block, recall
from .fsutil import now_iso, read_json_if_exists, sha256_text, write_json
from .ledger import Ledger
from .methodology import methodology_block, methodology_missing
from .plugin import ResearchPlugin
from .run_tools import TurnContext
from .stage_loop import TurnOutcome, run_stage_turn
from .validator import load_run_view, upstream_contract_errors, validate_stage

MAX_STAGE_RETRIES = 2      # attempt 循环上限（首次 + 2 次补跑）
GATE_RETRIES = 2           # 报告合规重写上限

# 受保护产物：编排器写完即记 hash，终检重算；模型工具写不到这些路径，
# 但最终校验防的是"运行目录被运行外的手改过"这类篡改。
# manifest.json 不在清单里（它存别人的 hash，自己不能存自己的）
_PROTECTED_FILES = ("_ledger.json", "events.jsonl")

_LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    task_id: str
    code: str                       # 研究主体（如 300750）
    plugin: ResearchPlugin
    llm: Any                        # ChatLLM 兼容：chat(messages, tools, timeout)
    run_dir: "str | Path"
    trade_date: "str | None" = None
    emit: "Callable[[dict], None] | None" = None     # 事件出口（带 "type" 键，接任务 SSE）
    cancel: "Callable[[], bool] | None" = None       # 取消轮询
    store: Any = None               # MarketStore（None = 无本地数据）
    fetch_registry: "dict | None" = None             # 测试注入合成取数
    max_stage_retries: int = MAX_STAGE_RETRIES
    gate_retries: int = GATE_RETRIES
    max_tool_rounds: int = 24
    request_timeout: "int | None" = 300
    stop_limits: "dict | None" = None                # 收工守卫上限（测试收紧用）
    methodology_dir: "str | Path | None" = None      # 测试注入方法论目录
    knowledge_dir: "str | Path | None" = None        # 知识档案目录（None = 不归档不召回）


@dataclass
class StageAttempt:
    attempt: int
    outcome: "TurnOutcome | None"
    errors: list = field(default_factory=list)
    upstream: list = field(default_factory=list)     # 上游契约错误（不补跑）


@dataclass
class StageResult:
    stage: str
    status: str                  # completed | partial | failed
    attempts: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    error: str = ""


@dataclass
class PipelineResult:
    status: str                  # completed | failed | cancelled
    stages: dict = field(default_factory=dict)       # stage -> StageResult
    report_path: "str | None" = None
    error: str = ""
    started_at: str = field(default_factory=now_iso)
    finished_at: "str | None" = None


class _Events:
    """运行事件：append 到 events.jsonl 并旁路 emit（显示层永不影响运行）。"""

    def __init__(self, run_dir: "str | Path", emit: "Callable[[dict], None] | None"):
        self.path = Path(run_dir) / "events.jsonl"
        self.emit = emit

    def write(self, type_: str, **payload) -> None:
        ev = {"ts": now_iso(), "type": type_, **payload}
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass
        if self.emit is not None:
            try:
                self.emit(ev)
            except Exception:  # noqa: BLE001
                pass


def _protected_hashes(run_dir: Path) -> "dict[str, str]":
    out: dict[str, str] = {}
    for name in _PROTECTED_FILES:
        p = run_dir / name
        if p.is_file():
            out[name] = sha256_text(p.read_text(encoding="utf-8", errors="replace"))
    return out


def _stage_prompt(plugin: ResearchPlugin, cfg: PipelineConfig, stage: str,
                  attempt_feedback: "list[str] | None",
                  knowledge: "KnowledgeRecall | None" = None) -> str:
    """方法论 + 历史知识档案（如有）+ 插件施工单 +（补跑时）上一轮校验错误。"""
    methodology = methodology_block(stage, cfg.methodology_dir)
    kblock = knowledge_block(knowledge)
    sheet = plugin.build_stage_prompt(stage, {
        "code": cfg.code,
        "trade_date": cfg.trade_date,
        "run_dir": str(cfg.run_dir),
    })
    feedback = ""
    if attempt_feedback:
        feedback = ("\n\n# 上一轮校验未通过，逐条修复（不要重跑全流程）：\n- "
                    + "\n- ".join(attempt_feedback))
    return f"{methodology}\n---\n\n{kblock}{sheet}{feedback}"


def _fetch_stage_datasets(cfg: PipelineConfig, ledger: Ledger, stage: str,
                          events: _Events) -> "tuple[list[str], list[str]]":
    """取本阶段数据集（账本已记则跳过）。返回 (failed_required, gaps)。"""
    datasets = cfg.plugin.stage_datasets.get(stage)
    if datasets is None:
        return [], []
    failed: list[str] = []
    gaps: list[str] = []
    for ds in list(datasets.required) + list(datasets.optional):
        if ledger.has(ds):
            entry = ledger.get(ds)
        else:
            rows, error = fetch_dataset(cfg.store, ds, cfg.code, cfg.trade_date,
                                        registry=cfg.fetch_registry)
            entry = write_fetch(cfg.run_dir, ds, {"code": cfg.code,
                                                  "trade_date": cfg.trade_date},
                                rows, error, stage)
            ledger.record(entry)
            events.write("pipeline_dataset_fetched", dataset=ds, status=entry.status,
                         rows=entry.rows, stage=stage)
        if entry.status == "error":
            failed.append(f"fetch/{ds}.json 不符契约: {entry.error}")
        elif entry.status == "empty":
            gaps.append(f"{ds}: 无数据")
            if ds in datasets.required:
                failed.append(f"fetch/{ds}.json 不符契约: 必需数据集无数据")
    return failed, gaps  # failed 仅供事件与诊断；attempt 循环里的 validator 才是裁判


def _attempt_loop(cfg: PipelineConfig, stage: str, events: _Events,
                  knowledge: "KnowledgeRecall | None" = None) -> StageResult:
    """attempt 循环：跑 turn → validator 判定 → 带错误补跑（最多 max_stage_retries 次）。"""
    result = StageResult(stage=stage, status="failed")
    feedback: "list[str] | None" = None
    prev_upstream: list[str] = []

    for attempt in range(1, cfg.max_stage_retries + 1):
        if cfg.cancel is not None and cfg.cancel():
            result.status = "failed"
            result.error = "已取消"
            return result

        ctx = TurnContext(run_dir=str(cfg.run_dir), stage=stage, plugin=cfg.plugin)
        prompt = _stage_prompt(cfg.plugin, cfg, stage, feedback, knowledge)
        events.write("pipeline_stage_attempt_started", stage=stage, attempt=attempt)
        outcome = run_stage_turn(cfg.llm, ctx, prompt,
                                 max_tool_rounds=cfg.max_tool_rounds,
                                 timeout=cfg.request_timeout,
                                 stop_limits=cfg.stop_limits,
                                 logger=lambda t, p: events.write(f"pipeline_{t}", **p))
        events.write("pipeline_stage_attempt_finished", stage=stage, attempt=attempt,
                     ok=outcome.ok, rounds=outcome.rounds,
                     stop_terminated=outcome.stop_terminated, error=outcome.error)

        validation = validate_stage(stage, cfg.plugin, load_run_view(cfg.run_dir))
        upstream = upstream_contract_errors(validation.errors)
        rec = StageAttempt(attempt=attempt, outcome=outcome,
                           errors=validation.errors, upstream=upstream)
        result.attempts.append(rec)
        result.gaps = validation.gaps

        if not validation.errors:
            result.status = "completed" if not validation.gaps else "partial"
            return result

        # 上游契约错误补跑也没用：立即停，把这一轮交给调用方判断
        if upstream and set(upstream) == set(validation.errors):
            result.status = "failed"
            result.error = "上游数据契约错误: " + "; ".join(upstream[:3])
            return result

        # 还有 attempt 余量才组补跑反馈（只喂模型修得了的：非上游契约错误）
        if attempt < cfg.max_stage_retries:
            feedback = [e for e in validation.errors if e not in upstream][:12]
            if outcome.stop_terminated:
                feedback.insert(0, f"收工检查终止: {outcome.stop_terminated[:300]}")

    last = result.attempts[-1] if result.attempts else None
    result.status = "failed"
    if last is not None:
        result.error = "; ".join(last.errors[:3]) or \
            (last.outcome.error if last.outcome else "") or "阶段校验未通过"
    else:
        result.error = "阶段校验未通过"
    return result


def _gate_rewrite_loop(cfg: PipelineConfig, stage_results: "dict[str, StageResult]",
                       events: _Events) -> "tuple[str, list[str]]":
    """报告阶段写完后：合规 gate + 章节完整性 + 首行状态档，违规带命中清单重写。
    全过之后编排器**确定性归一**首行状态档（complete/incomplete 按阶段状态推导，
    不以模型自报为准）。"""
    for attempt in range(1, cfg.gate_retries + 1):
        report = (Path(cfg.run_dir) / "report.md")
        text = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
        if not text.strip():
            return "缺产物: report.md", []

        gate = compliance_gate(text)
        sections_missing = missing_sections(text, list(cfg.plugin.report_sections))
        problems = ([f"第 {h.line} 行命中「{h.pattern}」" for h in gate.hits]
                    + [f"缺章节「{s}」" for s in sections_missing])
        if report_status_token(text) is None:
            problems.append("首行缺状态档标记（状态: complete|incomplete|failed|stale）")
        if not problems:
            expected = ("complete" if all(r.status == "completed" for r in stage_results.values())
                        else "incomplete")
            normalized, _ = normalize_report_status(text, expected)
            if normalized != text:
                (Path(cfg.run_dir) / "report.md").write_text(normalized, encoding="utf-8")
            return "", []

        if attempt >= cfg.gate_retries:
            return "报告合规检查未通过", problems

        hits_detail = "\n".join(f"- 第 {h.line} 行命中「{h.pattern}」: {h.text[:80]}"
                                for h in gate.hits[:10])
        rewrite_prompt = (
            "你刚写的报告未通过合规检查，必须重写并重新调用 write_report 提交全文。\n"
            "问题清单（逐条修掉，其余内容保持不变；不要改数字与证据引用）：\n"
            f"{hits_detail}\n" + ("\n".join(f"- 缺章节「{s}」" for s in sections_missing)) + "\n"
            "- 首行必须有状态档标记（状态: complete|incomplete|failed|stale）\n"
            "⛔ 不得给出任何买卖建议、目标价、止损位；改写建议类表述为事实陈述。")
        ctx = TurnContext(run_dir=str(cfg.run_dir), stage=cfg.plugin.report_stage, plugin=cfg.plugin)
        events.write("pipeline_gate_rewrite", attempt=attempt, problems=problems[:8])
        run_stage_turn(cfg.llm, ctx, rewrite_prompt,
                       max_tool_rounds=cfg.max_tool_rounds, timeout=cfg.request_timeout)
    return "报告合规检查未通过（重写次数用尽）", []


def run_pipeline(cfg: PipelineConfig) -> PipelineResult:
    """六阶段研究管线主入口。"""
    run_dir = Path(cfg.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "fetch").mkdir(exist_ok=True)
    (run_dir / "calcs").mkdir(exist_ok=True)
    (run_dir / "stages").mkdir(exist_ok=True)

    events = _Events(run_dir, cfg.emit)
    result = PipelineResult(status="failed")
    events.write("pipeline_started", task_id=cfg.task_id, code=cfg.code,
                 plugin=cfg.plugin.id, stages=list(cfg.plugin.stages))

    # 方法论检查：缺文件拒跑（不是降级）
    missing = methodology_missing(cfg.methodology_dir)
    if missing:
        result.error = f"方法论文件缺失，拒跑: {missing}"
        events.write("pipeline_failed", error=result.error)
        result.finished_at = now_iso()
        return result

    ledger = Ledger()

    # 召回历史研究结论（同标的上次已校验档案）；召回失败按无档案处理，不破运行
    knowledge: "KnowledgeRecall | None" = None
    if cfg.knowledge_dir:
        try:
            knowledge = recall(cfg.knowledge_dir, cfg.code)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("知识档案召回失败 code=%s", cfg.code, exc_info=True)

    for stage in cfg.plugin.stages:
        if cfg.cancel is not None and cfg.cancel():
            result.status = "cancelled"
            result.error = "已取消"
            events.write("pipeline_cancelled", stage=stage)
            break

        events.write("pipeline_stage_started", stage=stage)
        failed_fetch, gaps = _fetch_stage_datasets(cfg, ledger, stage, events)
        ledger.save_audit(run_dir)

        # critical 数据集全失败 → 整个运行 failed（拿不到可用研究）
        critical_failed = [c for c in cfg.plugin.critical_datasets
                           if ledger.get(c) is not None and ledger.get(c).status != "ok"]
        if critical_failed:
            stage_res = StageResult(stage=stage, status="failed",
                                    error="关键数据集取数失败: " + ", ".join(critical_failed))
            result.stages[stage] = stage_res
            result.error = stage_res.error
            events.write("pipeline_stage_failed", stage=stage, error=stage_res.error)
            break

        stage_res = _attempt_loop(cfg, stage, events, knowledge)
        result.stages[stage] = stage_res
        if stage_res.status == "completed":
            events.write("pipeline_stage_completed", stage=stage)
        elif stage_res.status == "partial":
            events.write("pipeline_stage_completed", stage=stage, partial=True,
                         gaps=stage_res.gaps[:5])
        else:
            events.write("pipeline_stage_failed", stage=stage, error=stage_res.error)
            result.error = f"阶段 {stage} 失败: {stage_res.error}"
            break

    # 报告阶段合格后跑 gate 重写循环
    report_stage = cfg.plugin.report_stage
    report_res = result.stages.get(report_stage)
    if report_res is not None and report_res.status in ("completed", "partial") \
            and result.status != "cancelled":
        gate_error, problems = _gate_rewrite_loop(cfg, result.stages, events)
        if gate_error:
            report_res.status = "failed"
            report_res.error = gate_error + ("; " + "; ".join(problems[:3]) if problems else "")
            result.error = f"报告阶段失败: {report_res.error}"
            events.write("pipeline_gate_failed", error=report_res.error)
        else:
            result.report_path = str(run_dir / "report.md")

    # 终检：manifest + 受保护产物 hash。事件先写完再算 hash、manifest 最后落盘
    # （events.jsonl 在受保护清单里，写完 manifest 后再 append 会让 hash 永远对不上）
    if not result.error:
        events.write("pipeline_completed",
                     stages={s: r.status for s, r in result.stages.items()})
        protected = _protected_hashes(run_dir)
        write_json(run_dir / "manifest.json", {
            "task_id": cfg.task_id,
            "code": cfg.code,
            "plugin": cfg.plugin.id,
            "trade_date": cfg.trade_date,
            "stages": {s: r.status for s, r in result.stages.items()},
            "protected": protected,
            "ledger": ledger.snapshot(),
            "finished_at": now_iso(),
        })
        result.status = "completed"

        # 知识归档：manifest 之后、不 emit 事件也不进受保护清单（破不了 hash）；
        # 归档失败只记日志——研究已完成，档案是副产品
        if cfg.knowledge_dir:
            try:
                archive_run(load_run_view(run_dir), cfg.plugin, code=cfg.code,
                            trade_date=cfg.trade_date, run_id=cfg.task_id,
                            knowledge_dir=cfg.knowledge_dir)
            except Exception:  # noqa: BLE001
                _LOGGER.warning("知识归档失败 run=%s", cfg.task_id, exc_info=True)

    result.finished_at = now_iso()
    return result


def verify_protected(run_dir: "str | Path") -> "list[str]":
    """终检受保护产物是否被改过（manifest 存逐文件 hash，重算比对）。"""
    root = Path(run_dir)
    manifest = read_json_if_exists(root / "manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("protected"), dict):
        return ["manifest.json 缺失或没有 protected hash 表"]
    problems: list[str] = []
    current = _protected_hashes(root)
    for name, want in manifest["protected"].items():
        if current.get(name) != want:
            problems.append(f"受保护产物 {name} 与 manifest 记录不一致（运行目录被改过）")
    return problems
