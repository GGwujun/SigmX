# -*- coding: utf-8 -*-
"""插件契约 —— Core 与垂类之间的那条缝（移植自 vibe-astock plugin.ts，裁剪到 SigmX 场景）。

判断一样东西放哪边，只问一句：**换个垂类它要不要重写？**

- 要重写 → 进插件（阶段名、每阶段取哪些数据集、产物 schema、阶段校验器、提示词施工单）
- 不用重写 → 留 Core（状态机、校验骨架、受控五工具、收工守卫、数字忠实度、编排）

注册期校验（``validate_plugin``）替代编译期穷尽性检查：键集与 stages 一致、
report_stage 必须末位、required ⊆ properties、schema 片段试校验、gate 规则 probe 自检。
不合格在**注册那一刻**被拒，而不是等跑到该阶段才炸（Kubernetes CRD 的做法）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from src.compliance.gate import validate_gate_rules
from src.compliance.gate_rules import GATE_RULES

# 阶段名会拼进文件路径（stages/<stage>.json），必须是安全路径段
_STAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

# schema 片段里受支持的类型关键字（validator 的手写校验器认这些，多了不认）
_SUPPORTED_TYPES = {"string", "number", "integer", "boolean", "array", "object"}


@dataclass(frozen=True)
class StageDatasets:
    """每阶段的取数计划：required 全失败 → 阶段不完整；optional 缺失只记 gap。"""

    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageSchema:
    """阶段产物在通用骨架之外的扩展字段（properties 片段 + 必填名单）。"""

    properties: dict = field(default_factory=dict)
    required: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageValidationContext:
    """传给插件阶段校验器的只读上下文：Core 不知道插件要看什么，整个给它。"""

    stage: str
    output: dict                                  # 该阶段产物（已过 schema）
    evidence_ids: frozenset                       # 账本里的全部证据 id
    calc_ids: frozenset                           # 合法计算记录的 id 集
    ledger_status: dict                           # dataset -> ok|empty|error
    run_dir: str


# (stage, cfg) -> 提示词施工单；cfg 携带 code/trade_date/run_dir/attempt_feedback 等
PromptBuilder = Callable[[str, dict], str]
# 插件阶段校验器：返回错误清单（空 = 通过）
StageValidator = Callable[[StageValidationContext], "list[str]"]


@dataclass
class ResearchPlugin:
    id: str
    stages: tuple[str, ...]
    report_stage: str
    stage_datasets: "dict[str, StageDatasets]"
    critical_datasets: tuple[str, ...] = ()
    stage_schemas: "dict[str, StageSchema]" = field(default_factory=dict)
    stage_validators: "dict[str, StageValidator]" = field(default_factory=dict)
    report_sections: tuple[str, ...] = ()
    build_stage_prompt: PromptBuilder = lambda stage, cfg: ""  # noqa: E731
    gate_rules: dict = field(default_factory=lambda: dict(GATE_RULES))


def _check_schema_shape(stage: str, schema: StageSchema) -> "list[str]":
    """schema 片段本身是不是受支持的形状（注册期试校验，运行期校验器只认这些关键字）。"""
    errors: list[str] = []
    for name, spec in schema.properties.items():
        where = f"stage_schemas.{stage}.{name}"
        if not _FIELD_NAME_RE.fullmatch(name):
            errors.append(f"{where} 字段名不合法（字母开头、字母数字下划线、≤64 字符）")
            continue
        if not isinstance(spec, dict):
            errors.append(f"{where} 必须是对象")
            continue
        t = spec.get("type")
        if t not in _SUPPORTED_TYPES:
            errors.append(f"{where}.type 必须是 {_SUPPORTED_TYPES} 之一，收到 {t!r}")
        if "enum" in spec and (not isinstance(spec["enum"], list) or not spec["enum"]):
            errors.append(f"{where}.enum 必须是非空数组")
        if "minItems" in spec and (not isinstance(spec["minItems"], int) or spec["minItems"] < 0):
            errors.append(f"{where}.minItems 必须是非负整数")
        if "items" in spec:
            if not isinstance(spec["items"], dict):
                errors.append(f"{where}.items 必须是对象")
            elif spec["items"].get("type") not in _SUPPORTED_TYPES:
                errors.append(f"{where}.items.type 必须是 {_SUPPORTED_TYPES} 之一")
        for pattern_key in ("pattern",):
            if pattern_key in spec:
                try:
                    re.compile(spec[pattern_key])
                except re.error as exc:
                    errors.append(f"{where}.{pattern_key} 不是合法正则: {exc}")
    return errors


def validate_plugin(plugin: ResearchPlugin) -> "list[str]":
    """注册期校验，返回错误清单（空 = 通过）。语义关系是 JSON Schema 表达不了的，
    只能手写：键集与 stages 一致、子集关系、跨表引用。"""
    errors: list[str] = []
    if not (plugin.id or "").strip():
        errors.append("id 不能为空")

    stages = list(plugin.stages or [])
    if not stages:
        errors.append("stages 不能为空")
    bad_names = [s for s in stages if not _STAGE_NAME_RE.fullmatch(s)]
    if bad_names:
        errors.append(f"阶段名必须是安全路径段（小写字母开头、≤32 字符）: {bad_names}")
    if len(set(stages)) != len(stages):
        errors.append("stages 有重复")

    stage_set = set(stages)
    if plugin.report_stage not in stage_set:
        errors.append(f"report_stage {plugin.report_stage!r} 不是已声明的阶段")
    elif stages and stages[-1] != plugin.report_stage:
        errors.append(f"report_stage 必须是 stages 的最后一个阶段（末位是 {stages[-1]!r}）")

    # stage_datasets 的键必须与 stages 完全一致：缺一个 = 该阶段没人管；多一个 = 拼错了没人说
    for table_name in ("stage_datasets",):
        table: dict = getattr(plugin, table_name)
        extra = sorted(set(table) - stage_set)
        missing = sorted(stage_set - set(table))
        if missing:
            errors.append(f"{table_name} 缺少阶段: {missing}")
        if extra:
            errors.append(f"{table_name} 多出未声明阶段: {extra}")

    for table_name in ("stage_schemas", "stage_validators"):
        table = getattr(plugin, table_name)
        extra = sorted(set(table) - stage_set)
        if extra:
            errors.append(f"{table_name} 多出未声明阶段: {extra}")

    # critical_datasets 拼错时"关键数据集全失败 → 运行 failed"永远匹配不上，静默降级
    planned: set[str] = set()
    for sd in plugin.stage_datasets.values():
        planned |= set(sd.required) | set(sd.optional)
    for c in plugin.critical_datasets:
        if c not in planned:
            errors.append(f"critical_datasets 里的 {c} 没出现在任何阶段的取数计划里（拼错了？）")

    for st, schema in plugin.stage_schemas.items():
        for k in schema.required:
            if k not in schema.properties:
                errors.append(f"stage_schemas.{st}.required 的 {k} 没有对应的 properties 定义")
        errors.extend(_check_schema_shape(st, schema))

    for st, fn in plugin.stage_validators.items():
        if not callable(fn):
            errors.append(f"stage_validators.{st} 必须是可调用对象")

    if not plugin.report_sections:
        errors.append("report_sections 不能为空")
    if not callable(plugin.build_stage_prompt):
        errors.append("build_stage_prompt 必须是可调用对象")

    # gate 规则 probe 自检：中性对照不触发 + 真探针必被拦（同一个判官跑）
    gate = plugin.gate_rules or {}
    probe_errors = validate_gate_rules(
        patterns=list(gate.get("patterns", [])),
        exempt_lines=list(gate.get("exempt_lines", [])),
        regexps=list(gate.get("regexps", [])),
        probe_line=str(gate.get("probe_line", "")),
    )
    errors.extend(probe_errors or [])
    return errors


def register_plugin(plugin: ResearchPlugin) -> ResearchPlugin:
    """校验并注册：不合格当场抛 ValueError。"""
    errors = validate_plugin(plugin)
    if errors:
        raise ValueError(f"插件 {plugin.id!r} 注册期校验失败:\n- " + "\n- ".join(errors))
    return plugin


def merged_stage_schema(plugin: ResearchPlugin, stage: str) -> dict:
    """通用骨架 + 插件扩展合并出的完整 schema（Core 只做合并，不认识任何具体字段名）。"""
    properties: dict[str, Any] = {
        "stage": {"type": "string"},
        "summary": {"type": "string", "description": "本阶段结论摘要（纯陈述，无建议）"},
        "evidence_ids": {"type": "array", "items": {"type": "string"},
                         "description": "支撑本阶段结论的证据 id 清单"},
        "calculation_ids": {"type": "array", "items": {"type": "string"},
                            "description": "本阶段引用的计算记录 id 清单"},
        "gaps": {"type": "array", "items": {"type": "string"},
                 "description": "optional 数据集缺失清单"},
    }
    required = ["stage", "summary"]
    ext = plugin.stage_schemas.get(stage)
    if ext is not None:
        properties.update(ext.properties)
        for k in ext.required:
            if k not in required:
                required.append(k)
    return {"properties": properties, "required": required}
