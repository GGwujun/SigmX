# -*- coding: utf-8 -*-
"""阶段校验器（Core）：产物合格不合格由它说了算，不以 agent 自报为准。

手写轻量 schema 校验器（type/enum/minItems/items/pattern/required），
不引 jsonschema。上游契约错误（``fetch/<x>.json 不符契约:`` 前缀）不补跑——
补跑也修不了数据层的问题，编排器把它与"模型没写好"分开处理。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.compliance.gate import compliance_gate
from src.compliance.gate_rules import gate_stage_patterns

from .calc import verify_calcs
from .fsutil import read_json_if_exists
from .plugin import ResearchPlugin, merged_stage_schema

_EV_ID_RE = re.compile(r"^ev-[0-9A-Za-z_-]+$")
_CALC_ID_RE = re.compile(r"^calc-[0-9a-f]{16}$")


# ---------------------------------------------------------------------------
# 轻量 schema 校验
# ---------------------------------------------------------------------------

def _type_ok(value: Any, t: str) -> bool:
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return False


def validate_against_schema(obj: Any, schema: dict, where: str = "") -> "list[str]":
    """按 {properties, required} 片段校验；只认注册期声明过的关键字。"""
    if not isinstance(obj, dict):
        return [f"{where or '产物'}必须是对象"]
    errors: list[str] = []
    properties: dict = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in obj:
            errors.append(f"{where}缺必填字段 {k}")
    for k, spec in properties.items():
        if k not in obj:
            continue
        v = obj[k]
        at = f"{where}{k}" if not where else f"{where}.{k}"
        t = spec.get("type")
        if t and not _type_ok(v, t):
            errors.append(f"{at} 类型应为 {t}")
            continue
        if "enum" in spec and v not in spec["enum"]:
            errors.append(f"{at} 的取值 {v!r} 不在枚举 {spec['enum']} 内")
        if "pattern" in spec and isinstance(v, str) and not re.search(spec["pattern"], v):
            errors.append(f"{at} 不匹配要求的格式 {spec['pattern']}")
        if isinstance(v, list):
            if "minItems" in spec and len(v) < spec["minItems"]:
                errors.append(f"{at} 至少要有 {spec['minItems']} 项（现 {len(v)}）")
            items = spec.get("items")
            if items and items.get("type"):
                bad = sum(1 for x in v if not _type_ok(x, items["type"]))
                if bad:
                    errors.append(f"{at} 有 {bad} 项不是 {items['type']} 类型")
    return errors


def validate_stage_output_shape(plugin: ResearchPlugin, stage: str, output: Any) -> "list[str]":
    """write_stage 工具路径的 schema 校验（骨架 + 插件扩展合并后整体校）。"""
    return validate_against_schema(output, merged_stage_schema(plugin, stage))


# ---------------------------------------------------------------------------
# 运行视图（磁盘审计副本：fetch / calcs / stages）
# ---------------------------------------------------------------------------

@dataclass
class RunView:
    evidence_ids: frozenset = field(default_factory=frozenset)
    calc_records: list = field(default_factory=list)
    fetch: dict = field(default_factory=dict)        # dataset -> envelope
    stage_outputs: dict = field(default_factory=dict)  # stage -> dict

    @property
    def calc_ids(self) -> frozenset:
        return frozenset(str(r.get("calculation_id")) for r in self.calc_records
                         if r.get("calculation_id"))


def load_run_view(run_dir: "str | Path") -> RunView:
    """从磁盘读运行视图（守卫/校验/报告阶段共用；账本内存态是编排器的，这里读审计副本）。"""
    root = Path(run_dir)
    view = RunView()
    fetch_dir = root / "fetch"
    if fetch_dir.is_dir():
        for f in sorted(fetch_dir.glob("*.json")):
            env = read_json_if_exists(f)
            if isinstance(env, dict) and env.get("dataset"):
                view.fetch[str(env["dataset"])] = env
                for ev in env.get("evidence") or []:
                    if isinstance(ev, dict) and ev.get("id"):
                        view.evidence_ids = view.evidence_ids | {str(ev["id"])}
    calcs_dir = root / "calcs"
    if calcs_dir.is_dir():
        for f in sorted(calcs_dir.glob("*.json")):
            rec = read_json_if_exists(f)
            if isinstance(rec, dict) and rec.get("calculation_id"):
                view.calc_records.append(rec)
    stages_dir = root / "stages"
    if stages_dir.is_dir():
        for f in sorted(stages_dir.glob("*.json")):
            data = read_json_if_exists(f)
            if isinstance(data, dict):
                view.stage_outputs[f.stem] = data
    return view


# ---------------------------------------------------------------------------
# 阶段校验
# ---------------------------------------------------------------------------

@dataclass
class StageValidationResult:
    errors: list = field(default_factory=list)
    gaps: list = field(default_factory=list)


def validate_stage(stage: str, plugin: ResearchPlugin, view: RunView) -> StageValidationResult:
    """校验一个阶段的产物。errors 非空 = 不合格；gaps 只记录 optional 缺失。"""
    res = StageValidationResult()

    datasets = plugin.stage_datasets.get(stage)
    if datasets is not None:
        for ds in datasets.required:
            env = view.fetch.get(ds)
            if env is None:
                res.errors.append(f"必需数据集 {ds} 没有取数记录")
            elif env.get("status") == "error":
                res.errors.append(f"必需数据集 {ds} 取数失败: {str(env.get('error'))[:120]}")
            elif env.get("status") == "empty":
                res.errors.append(f"必需数据集 {ds} 无数据（0 行）")
        for ds in datasets.optional:
            env = view.fetch.get(ds)
            if env is None or env.get("status") != "ok":
                why = "无记录" if env is None else str(env.get("error") or "无数据")[:80]
                res.gaps.append(f"{ds}: {why}")

    output = view.stage_outputs.get(stage)
    if output is None:
        res.errors.append(f"缺产物: stages/{stage}.json")
        return res

    res.errors.extend(validate_against_schema(output, merged_stage_schema(plugin, stage)))

    # 引用存在性：stage 产物与 calc 记录里引用的 id 必须真的存在
    for key, pattern, pool in (
        ("evidence_ids", _EV_ID_RE, view.evidence_ids),
        ("calculation_ids", _CALC_ID_RE, view.calc_ids),
    ):
        for ref in output.get(key) or []:
            if not isinstance(ref, str):
                res.errors.append(f"{key} 里有非字符串引用 {ref!r}")
            elif not pattern.fullmatch(ref):
                res.errors.append(f"{key} 里的 {ref} 格式不合法")
            elif ref not in pool:
                res.errors.append(f"{key} 里的 {ref} 不存在（未取数/未计算）")

    # calc 记录的 refs 同样要存在；error 记录也是审计痕迹，但引用错仍是引用错
    for rec in view.calc_records:
        refs = rec.get("refs") or {}
        for ref in refs.get("evidence_ids") or []:
            if isinstance(ref, str) and ref not in view.evidence_ids:
                res.errors.append(f"计算 {rec.get('calculation_id')} 引用的证据 {ref} 不存在")
        for ref in refs.get("calculation_ids") or []:
            if isinstance(ref, str) and ref not in view.calc_ids:
                res.errors.append(f"计算 {rec.get('calculation_id')} 引用的上游计算 {ref} 不存在")

    # 同实参复算：记录被改写在写入时就该拦住，这里是终检
    bad = verify_calcs(view.calc_records)
    for b in bad:
        res.errors.append(f"计算 {b['calculation_id']}({b['fn']}) {b['reason']}")

    # 阶段自由文本过收窄 gate（提及语境放行，建议语境照拦）
    summary = output.get("summary")
    if isinstance(summary, str) and summary.strip():
        gate = compliance_gate(summary, patterns=gate_stage_patterns())
        if not gate.ok:
            res.errors.append(f"阶段摘要含建议类表述: 第 {gate.hits[0].line} 行命中「{gate.hits[0].pattern}」")

    # 插件阶段校验器
    custom = plugin.stage_validators.get(stage)
    if custom is not None:
        from .plugin import StageValidationContext  # 局部导入避免循环
        ctx = StageValidationContext(
            stage=stage, output=output, evidence_ids=view.evidence_ids,
            calc_ids=view.calc_ids,
            ledger_status={d: e.get("status", "?") for d, e in view.fetch.items()},
            run_dir="",
        )
        try:
            res.errors.extend(str(e) for e in custom(ctx))
        except Exception as exc:  # noqa: BLE001 —— 校验器炸了当该阶段不合格，不当运行崩溃
            res.errors.append(f"阶段校验器异常: {type(exc).__name__}: {exc}")
    return res


def upstream_contract_errors(errors: "list[str]") -> "list[str]":
    """从错误清单里挑出上游契约错误（数据层问题）：这些不该让模型补跑。"""
    return [e for e in errors if "取数失败" in e or "没有取数记录" in e or "无数据" in e]
