# -*- coding: utf-8 -*-
"""受控工具运行时（Core）：一次运行里模型能做的全部动作就这五件。

列产物 / 读产物 / 调确定性计算 / 写当前阶段 / 写报告 —— 没有 Shell、没有网络、
没有任意文件访问。换个垂类这五件事一行都不用重写。

**当前阶段来自编排器传入的 TurnContext 对象**（同进程，VA 的 hook-context.json
文件桥接不需要）：模型无法自称在别的阶段——它连"我是哪个阶段"都不是自己说了算。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .calc import list_functions, run_calc
from .fsutil import atomic_write_text, read_json_if_exists, write_json
from .plugin import ResearchPlugin
from .validator import validate_stage_output_shape

MAX_READ_CHARS = 1_000_000
TOOL_RESULT_CAP = 24_000

_READABLE_RE = re.compile(r"^(fetch|calcs|stages)/[A-Za-z0-9._-]+\.json$")
_CALC_FILE_RE = re.compile(r"^\d{2}_[a-z0-9][a-z0-9_]{0,80}\.json$")
_CALC_FUNCTION_RE = re.compile(r"^[a-z][a-z0-9_]{0,80}$")
_REF_RE = re.compile(r"^(?:ev|calc)-[0-9A-Za-z_-]+$")


class RunToolsError(Exception):
    """工具层拒绝（参数/越权/状态不对）。code 给模型看，让它换招。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class TurnContext:
    """一个 turn 的受控上下文：run_dir + 当前阶段 + 插件。编排器每 turn 前设置一次。"""

    run_dir: str
    stage: str
    plugin: ResearchPlugin


def _run_path(ctx: TurnContext, rel: str) -> Path:
    """白名单外的路径一律拒；反斜杠统一、剥 RUN/ 前缀（施工单里常这么写）。"""
    normalized = str(rel or "").replace("\\", "/").strip()
    if normalized.upper().startswith("RUN/"):
        normalized = normalized[4:]
    allowed = normalized in ("report.md",) or bool(_READABLE_RE.fullmatch(normalized))
    if not allowed or ".." in normalized:
        raise RunToolsError("path_not_allowed", f"不允许访问: {rel}")
    return Path(ctx.run_dir) / normalized


def _require(args: dict, key: str, typ: type):
    v = args.get(key)
    if not isinstance(v, typ) or (typ is str and not v):
        raise RunToolsError("bad_arguments", f"参数 {key} 缺失或类型不是 {typ.__name__}")
    return v


def _tool_list_run_files(ctx: TurnContext, args: dict) -> dict:
    files = []
    root = Path(ctx.run_dir)
    for sub in ("fetch", "calcs", "stages"):
        d = root / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            if f.is_file():
                files.append({"path": f"{sub}/{f.name}", "bytes": f.stat().st_size})
    report = root / "report.md"
    if report.is_file():
        files.append({"path": "report.md", "bytes": report.stat().st_size})
    return {"files": files, "stage": ctx.stage}


def _tool_read_run_file(ctx: TurnContext, args: dict) -> dict:
    target = _run_path(ctx, _require(args, "path", str))
    if not target.is_file():
        raise RunToolsError("file_unavailable", f"文件不存在: {args.get('path')}")
    text = target.read_text(encoding="utf-8", errors="replace")
    offset = args.get("offset") or 0
    limit = args.get("limit_chars") or 200_000
    if not isinstance(offset, int) or not isinstance(limit, int) or offset < 0 or limit < 1:
        raise RunToolsError("bad_arguments", "offset/limit_chars 必须是非负/正整数")
    limit = min(limit, MAX_READ_CHARS)
    chunk = text[offset: offset + limit]
    return {"path": str(args.get("path")), "text": chunk, "offset": offset,
            "next_offset": offset + len(chunk) if offset + len(chunk) < len(text) else None,
            "total_chars": len(text)}


def _tool_calculate(ctx: TurnContext, args: dict) -> dict:
    fn = _require(args, "function", str)
    fn_args = args.get("args")
    if not isinstance(fn_args, dict):
        raise RunToolsError("bad_arguments", "args 必须是对象")
    output_file = _require(args, "output_file", str)
    if not _CALC_FUNCTION_RE.fullmatch(fn):
        raise RunToolsError("bad_function", "计算函数名格式非法")
    if fn == "list":
        # list 是元命令：打印函数清单，不产生计算记录、不落盘
        names = ", ".join(f["name"] for f in list_functions())
        raise RunToolsError(
            "not_a_calculation",
            "list 是计算器的元命令，不产生计算记录，不会写入 calcs/。"
            f"可用的计算函数: {names}。请改用其中一个具体函数。")
    if not _CALC_FILE_RE.fullmatch(output_file):
        raise RunToolsError("bad_output_file", "output_file 必须形如 NN_name.json（两位数字_小写标识符）")

    refs = {"evidence_ids": [], "calculation_ids": []}
    for key in ("evidence_ids", "calculation_ids"):
        raw = args.get(key) or []
        if not isinstance(raw, list):
            raise RunToolsError("bad_arguments", f"{key} 必须是数组")
        for r in raw:
            if not isinstance(r, str) or not _REF_RE.fullmatch(r):
                raise RunToolsError("bad_arguments", f"{key} 里的 {r!r} 不是合法引用 id")
        refs[key] = raw

    # 跨阶段 owner 保护：别的阶段写过的 calc 文件不许覆盖
    owners_file = Path(ctx.run_dir) / ".calc_owners.json"
    owners = read_json_if_exists(owners_file) or {}
    target = Path(ctx.run_dir) / "calcs" / output_file
    if target.exists() and owners.get(output_file) not in (None, ctx.stage):
        raise RunToolsError("calc_owned_by_other_stage",
                            f"{output_file} 已由 {owners.get(output_file)} 阶段创建，当前 {ctx.stage} 阶段不得覆盖")

    record = run_calc(fn, fn_args)
    record["refs"] = refs
    write_json(target, record)
    owners[output_file] = ctx.stage
    write_json(owners_file, owners)
    return record


def _tool_write_stage(ctx: TurnContext, args: dict) -> dict:
    output = args.get("stage_output")
    if not isinstance(output, dict):
        raise RunToolsError("bad_arguments", "stage_output 必须是对象")
    if output.get("stage") != ctx.stage:
        raise RunToolsError("wrong_stage", f"当前阶段是 {ctx.stage}，不能写 {output.get('stage')!r}")
    errors = validate_stage_output_shape(ctx.plugin, ctx.stage, output)
    if errors:
        raise RunToolsError("stage_schema_invalid", "; ".join(errors[:8]))
    write_json(Path(ctx.run_dir) / "stages" / f"{ctx.stage}.json", output)
    return {"written": f"stages/{ctx.stage}.json", "stage": ctx.stage}


def _tool_write_report(ctx: TurnContext, args: dict) -> dict:
    if ctx.stage != ctx.plugin.report_stage:
        raise RunToolsError("wrong_stage", f"只有 {ctx.plugin.report_stage} 阶段可以写报告")
    markdown = _require(args, "markdown", str)
    if not markdown.strip() or len(markdown) > 2_000_000:
        raise RunToolsError("bad_report", "报告为空或超过 2,000,000 字符")
    stage_output = args.get("stage_output")
    written = ["report.md"]
    if isinstance(stage_output, dict):
        _tool_write_stage(ctx, {"stage_output": stage_output})
        written.append(f"stages/{ctx.plugin.report_stage}.json")
    else:
        stage_file = Path(ctx.run_dir) / "stages" / f"{ctx.plugin.report_stage}.json"
        if not read_json_if_exists(stage_file):
            raise RunToolsError("report_stage_missing", "首次写报告必须同时提交 stage_output")
    atomic_write_text(Path(ctx.run_dir) / "report.md",
                      markdown if markdown.endswith("\n") else markdown + "\n")
    return {"written": written}


_TOOL_IMPLEMENTATIONS = {
    "list_run_files": _tool_list_run_files,
    "read_run_file": _tool_read_run_file,
    "calculate": _tool_calculate,
    "write_stage": _tool_write_stage,
    "write_report": _tool_write_report,
}

_TOOL_SPECS: "list[dict]" = [
    {"name": "list_run_files", "title": "列出本次运行文件",
     "description": "列出本次运行可读的 fetch/calcs/stages JSON 与报告。",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_run_file", "title": "读取本次运行文件",
     "description": "只读本次运行的 JSON 或报告；大文件用 offset/limit_chars 分段。",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "offset": {"type": "integer"},
         "limit_chars": {"type": "integer"}}, "required": ["path"]}},
    {"name": "calculate", "title": "确定性计算",
     "description": "调用 calc 纯函数并把结果写入 calcs/。输入证据与上游计算 id 必须完整列出。",
     "parameters": {"type": "object", "properties": {
         "function": {"type": "string"}, "args": {"type": "object"},
         "evidence_ids": {"type": "array", "items": {"type": "string"}},
         "calculation_ids": {"type": "array", "items": {"type": "string"}},
         "output_file": {"type": "string"}},
         "required": ["function", "args", "output_file"]}},
    {"name": "write_stage", "title": "写当前阶段产物",
     "description": "按当前阶段 schema 写 stages/<stage>.json；不能写别的阶段。",
     "parameters": {"type": "object", "properties": {
         "stage_output": {"type": "object"}}, "required": ["stage_output"]}},
    {"name": "write_report", "title": "写研究报告",
     "description": "只在报告阶段写 report.md；首次调用同时提交报告阶段 JSON，重写时可只传 markdown。",
     "parameters": {"type": "object", "properties": {
         "markdown": {"type": "string"}, "stage_output": {"type": "object"}},
         "required": ["markdown"]}},
]


def run_tools_as_specs() -> "list[dict]":
    """OpenAI function calling 工具表（入参 schema 的唯一真理源就是 _TOOL_SPECS）。"""
    return [{"type": "function", "function": spec} for spec in _TOOL_SPECS]


def call_run_tool(ctx: TurnContext, name: str, args: Any) -> Any:
    """唯一调用入口：不在这张表里的工具不存在，绕不开校验。"""
    impl = _TOOL_IMPLEMENTATIONS.get(name)
    if impl is None:
        raise RunToolsError("unknown_tool",
                            f"没有这个工具: {name}（可用: {', '.join(_TOOL_IMPLEMENTATIONS)}）")
    if not isinstance(args, dict):
        raise RunToolsError("bad_arguments", f"{name} 的参数必须是对象")
    return impl(ctx, args)


def tool_result_text(value: Any) -> str:
    """工具返回值 → 喂给模型的文本；过大给结构化说明，不截断 JSON（坏 JSON 只会更糊涂）。"""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= TOOL_RESULT_CAP:
        return text
    return json.dumps({"error": "result_too_large", "bytes": len(text), "cap": TOOL_RESULT_CAP,
                       "hint": "结果过大。请改用 read_run_file 的 offset 与 limit_chars 分段读取。"},
                      ensure_ascii=False)
