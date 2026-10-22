# -*- coding: utf-8 -*-
"""收工守卫（Core，移植自 vibe-astock stop_guard.ts）。

语义 = "缺产物 / 阶段校验不过，不许正常收工"：模型不再要工具 = 想收工，先查一次 ——
- 合格 → 放行；
- 不合格 → 拦下，问题清单作为下一条 user 消息喂回同一段对话让它接着修；
- 连续 max_idle 次拦截之间都**没有新增合法计算记录**（空转），或累计拦截达
  max_total 次（兜底硬上限）→ 终止本轮：编排器把这一轮判为失败并带着校验错误补跑。

推进判据是合法 calc 记录集合指纹（sha1），不是 token 也不是拦截次数：
合规工作流是"攒好几轮 calc → 最后一步才写 stage 文件"，只数拦截会在模型还在
攒 calc 时就把预算烧光。点开头文件不算（无意义写盘刷不掉预算）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .plugin import ResearchPlugin
from .validator import load_run_view, validate_stage

MAX_STOP_BLOCKS = 6
MAX_TOTAL_STOP_BLOCKS = 20

_LEDGERISH_RE = re.compile(r"账本|没有取数记录|取数失败")


def stage_problems(run_dir: str, stage: str, plugin: ResearchPlugin) -> "list[str]":
    """阶段想收工时还差什么；空清单 = 可以收工。

    账本类错误（数据层问题）不拿来拦模型——那几条不是它修得了的。
    """
    root = Path(run_dir)
    problems: list[str] = []
    stage_file = root / "stages" / f"{stage}.json"
    if not stage_file.is_file():
        problems.append(f"缺产物: stages/{stage}.json")
    if stage == plugin.report_stage and not (root / "report.md").is_file():
        problems.append("缺产物: report.md")
    if problems:
        return problems
    result = validate_stage(stage, plugin, load_run_view(run_dir))
    return [e for e in result.errors if not _LEDGERISH_RE.search(e)][:8]


def valid_calcs(run_dir: str) -> "dict[str, object]":
    """calcs/ 下合法计算记录：条数 + 全套 calculation_id（排序后）的指纹。

    合法 = JSON 可解析且 calculation_id 是非空字符串。比"能解析就收"严得多：
    按那个口径判推进，写个参数文件也算一次推进。目录不存在与目录空着给同一个
    指纹，否则"刚建好空 calcs/"会被当成一次推进。指纹只用于与上次拦截比对，
    不进产物、不参与安全判定，sha1 足够。
    """
    ids: list[str] = []
    d = Path(run_dir) / "calcs"
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(rec, dict) and isinstance(rec.get("calculation_id"), str) and rec["calculation_id"]:
            ids.append(rec["calculation_id"])
    ids.sort()
    fp = hashlib.sha1("\n".join(ids).encode("utf-8")).hexdigest()[:16]
    return {"count": len(ids), "fp": fp}


def _stop_decision(kind: str, **kw) -> dict:
    return {"decision": kind, **kw}


class StopGuard:
    """一个 (阶段, attempt) 用一个实例。check() 在模型想收工时调用一次。"""

    def __init__(self, run_dir: str, stage: str, plugin: ResearchPlugin,
                 limits: "dict | None" = None):
        self.run_dir = run_dir
        self.stage = stage
        self.plugin = plugin
        lim = limits or {"max_idle": MAX_STOP_BLOCKS, "max_total": MAX_TOTAL_STOP_BLOCKS}
        self.max_idle = int(lim.get("max_idle", MAX_STOP_BLOCKS))
        self.max_total = int(lim.get("max_total", MAX_TOTAL_STOP_BLOCKS))
        self.last_fp: "str | None" = None
        self.last_count: "int | None" = None
        self.streak = 0
        self.blocks = 0
        self.terminated = False

    def check(self) -> dict:
        """返回 {decision: allow|error|block|terminate, ...}。守卫自身出错放行但出声，
        绝不让守卫故障卡死大脑（validator 终检兜底）。"""
        try:
            problems = stage_problems(self.run_dir, self.stage, self.plugin)
        except Exception as exc:  # noqa: BLE001
            return _stop_decision("error", error=f"{type(exc).__name__}: {exc}")
        if not problems:
            return _stop_decision("allow")

        cur = valid_calcs(self.run_dir)
        progressed = (self.last_fp is None or self.last_count is None
                      or (cur["fp"] != self.last_fp and cur["count"] >= self.last_count))
        idle_streak = 1 if progressed else self.streak + 1
        if idle_streak <= self.max_idle and self.blocks < self.max_total:
            self.blocks += 1
            self.streak = idle_streak
            self.last_fp = cur["fp"]
            self.last_count = cur["count"]
            message = (f"【收工检查】本阶段({self.stage})还不能收工"
                       f"(无推进空转 {idle_streak}/{self.max_idle}，本轮累计拦截 {self.blocks}/{self.max_total})，"
                       f"请先修好再结束本轮;有新增计算落盘则空转计数回 1，但累计上限照涨:\n- "
                       + "\n- ".join(problems))[:1800]
            return _stop_decision("block", message=message, problems=problems,
                                  idle_streak=idle_streak, blocks=self.blocks)

        self.terminated = True
        # 两种终止分开说：一直在算却写不出产物(累计上限)≠ 拦下后什么都没做(空转)
        why = (f"本轮累计拦截已达上限 {self.blocks}/{self.max_total} 次"
               + ("(上一次拦截后仍有新计算落盘)" if progressed else "")
               ) if self.blocks >= self.max_total else (
               f"连续 {self.streak} 次拦截后都没有新增计算" if self.streak > 1
               else f"上一次拦截后没有新增计算") + f"(本轮累计拦截 {self.blocks} 次)"
        reason = (f"收工检查终止本轮:{why}，仍不合格: " + "; ".join(problems[:3]))[:1000]
        # idle_streak 是"已经发生过的"连续空转拦截数，不是本次判定值
        return _stop_decision("terminate", reason=reason, problems=problems[:8],
                              idle_streak=self.streak, blocks=self.blocks)
