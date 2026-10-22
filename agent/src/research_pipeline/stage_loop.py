# -*- coding: utf-8 -*-
"""阶段执行循环（Core）：一个 turn = 一个阶段的一次尝试 = 一段 function calling 循环。

发提示词 → 模型要工具 → 执行受控工具 → 结果喂回 → …… → 模型不再要工具 =
想收工 → 收工检查 → 放行 / 拦下接着修（同一段对话里）/ 终止。

上下文策略 = 每阶段独立会话：阶段之间靠**已校验的磁盘产物**传状态，
模型用 read_run_file 自取（长线程在无状态 provider 上不成立，磁盘产物
本来就是 validator 校验的那份真理源）。

工具参数解析失败**不静默换成 {}**：回喂 invalid_arguments 并保留 call id
让模型改。工具结果不按字符硬截：截断的 JSON 是坏 JSON，给结构化说明。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .run_tools import (RunToolsError, TurnContext, call_run_tool,
                        run_tools_as_specs, tool_result_text)
from .stop_guard import MAX_STOP_BLOCKS, MAX_TOTAL_STOP_BLOCKS, StopGuard

MAX_TOOL_ROUNDS_DEFAULT = 24
REQUEST_TIMEOUT_DEFAULT = 300


@dataclass
class TurnOutcome:
    ok: bool                              # 自然收尾（收工检查放行或守卫自身出错放行）
    stop_terminated: "str | None" = None  # 收工检查终止原因（非 None = 本轮失败）
    stop_blocks: int = 0
    rounds: int = 0
    error: "str | None" = None            # 传输/模型层错误
    log: list = field(default_factory=list)


def _assistant_message(content: "str | None", tool_calls: list) -> dict:
    """OpenAI 格式 assistant 消息（带 tool_calls 回喂）。"""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name,
                          "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
            for tc in tool_calls
        ],
    }


def run_stage_turn(
    llm: Any,
    ctx: TurnContext,
    prompt: str,
    *,
    max_tool_rounds: int = MAX_TOOL_ROUNDS_DEFAULT,
    timeout: "int | None" = REQUEST_TIMEOUT_DEFAULT,
    stop_limits: "dict | None" = None,
    logger: "Callable[[str, dict], None] | None" = None,
) -> TurnOutcome:
    """跑一个阶段的 function calling 循环。产物合格与否由编排器事后用 validator 判定，
    这里只负责：循环有界、工具受控、收工检查、错误如实上报。"""
    log: list[dict] = []

    def emit(type_: str, payload: dict) -> None:
        log.append({"stage": ctx.stage, "type": type_, **payload})
        if logger is not None:
            try:
                logger(type_, {"stage": ctx.stage, **payload})
            except Exception:  # noqa: BLE001 —— 观察者出问题不能影响运行
                pass

    guard = StopGuard(ctx.run_dir, ctx.stage, ctx.plugin,
                      limits=stop_limits or {"max_idle": MAX_STOP_BLOCKS,
                                             "max_total": MAX_TOTAL_STOP_BLOCKS})
    messages: list[dict] = [{"role": "user", "content": prompt}]
    tools = run_tools_as_specs()
    outcome = TurnOutcome(ok=False)
    rounds = 0
    tool_rounds = 0

    emit("turn_start", {"max_tool_rounds": max_tool_rounds})

    while tool_rounds < max_tool_rounds:
        rounds += 1
        try:
            response = llm.chat(messages, tools=tools, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 —— 传输层错误如实上报，由编排器决定重试
            outcome.error = f"{type(exc).__name__}: {exc}"
            emit("request_failed", {"round": rounds, "error": outcome.error})
            outcome.rounds = rounds
            return outcome

        tool_calls = list(response.tool_calls or [])
        messages.append(_assistant_message(response.content, tool_calls))
        emit("model_reply", {"round": rounds, "tool_calls": len(tool_calls),
                             "finish_reason": response.finish_reason})

        if not tool_calls:
            # 模型想收工：先过收工检查
            verdict = guard.check()
            if verdict["decision"] == "block":
                emit("stop_guard_block", {"idle_streak": verdict["idle_streak"],
                                          "blocks": verdict["blocks"],
                                          "problems": verdict["problems"]})
                messages.append({"role": "user", "content": verdict["message"]})
                continue
            if verdict["decision"] == "terminate":
                outcome.stop_terminated = verdict["reason"]
                emit("stop_guard_terminate", {"reason": verdict["reason"],
                                              "blocks": verdict["blocks"]})
            elif verdict["decision"] == "error":
                emit("stop_guard_error", {"error": verdict["error"]})
            outcome.ok = outcome.stop_terminated is None
            break

        tool_rounds += 1
        for call in tool_calls:
            if not isinstance(call.arguments, dict):
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": json.dumps({"error": "invalid_arguments",
                                                        "message": "参数不是合法对象，请重给这次调用。"},
                                                       ensure_ascii=False)})
                continue
            args = call.arguments
            try:
                value = call_run_tool(ctx, call.name, args)
                emit("tool_ok", {"tool": call.name})
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": tool_result_text(value)})
            except RunToolsError as exc:
                emit("tool_error", {"tool": call.name, "code": exc.code})
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": json.dumps({"error": exc.code, "message": str(exc)},
                                                       ensure_ascii=False)})
            except Exception as exc:  # noqa: BLE001 —— 内部错误也回喂，模型换招继续
                emit("tool_error", {"tool": call.name, "code": "internal"})
                messages.append({"role": "tool", "tool_call_id": call.id, "name": call.name,
                                 "content": json.dumps({"error": "internal",
                                                        "message": f"{type(exc).__name__}: {exc}"},
                                                       ensure_ascii=False)})
    else:
        # 撞了轮数上限：不再要最终回复（产物落盘与否由 validator 判定），
        # 把这轮交回编排器带校验错误补跑
        outcome.error = f"工具调用轮数已达上限 {max_tool_rounds}"
        emit("tool_rounds_exhausted", {"rounds": max_tool_rounds})

    outcome.rounds = rounds
    outcome.stop_blocks = guard.blocks
    outcome.log = log
    if outcome.error is None and outcome.stop_terminated is None:
        outcome.ok = True
    return outcome
