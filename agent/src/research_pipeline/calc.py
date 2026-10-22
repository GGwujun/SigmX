# -*- coding: utf-8 -*-
"""calc 确定性计算核心（语义移植自 vibe-astock calc/cli.py）。

- ``calculation_id``：内容寻址（sha256(fn + calc_version + 规范化实参) 前 16 hex）——
  同实参必同 id，agent 改写结果骗不过 validator 的同实参复算。
- 信封：``{calculation_id, fn, args, status, value, unit, reason, details, calc_version}``，
  status ∈ ok | error | not_meaningful（error 记录也是审计痕迹，validator 不把它当有效计算）。
- 函数注册表：内置通用算术/统计，插件可注册垂类函数；``list`` 是元命令（返回清单不落盘）。
- ``verify_calc``：同实参进程内重调比对（status/value 数值容差/unit）；calc_version
  不同跳过（旧版本记录是正常的历史，不是缺陷）。

纯计算、无 IO；落盘由调用方（run_tools / orchestrator）负责。
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

CALC_VERSION = "1"


# ---------------------------------------------------------------------------
# calculation_id 与信封
# ---------------------------------------------------------------------------

def _canonical(value: Any) -> Any:
    """实参规范化：保证 calculation_id 确定性（1.0 与 1 同 id、dict 键序无关）。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return int(value) if value.is_integer() else round(value, 10)
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    return value


def calculation_id(fn: str, args: dict, calc_version: str = CALC_VERSION) -> str:
    payload = json.dumps({"fn": fn, "args": _canonical(args), "version": calc_version},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "calc-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def make_envelope(fn: str, args: dict, *, status: str, value: Any = None, unit: str = "",
                  reason: str = "", details: "dict | None" = None,
                  calc_version: str = CALC_VERSION) -> dict:
    return {
        "calculation_id": calculation_id(fn, args, calc_version),
        "fn": fn,
        "args": _canonical(args),
        "status": status,
        "value": value,
        "unit": unit,
        "reason": reason,
        "details": details or {},
        "calc_version": calc_version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# 函数注册表
# ---------------------------------------------------------------------------

@dataclass
class CalcFunction:
    name: str
    fn: Callable[[dict], tuple[Any, str]]  # args -> (value, unit)
    doc: str = ""


_REGISTRY: dict[str, CalcFunction] = {}


def register_calc(name: str, fn: "Callable[[dict], tuple[Any, str]] | None" = None, *, doc: str = ""):
    """注册 calc 函数（装饰器或直接调用）。返回 (value, unit) 二元组。"""
    if fn is None:
        def deco(f: Callable[[dict], tuple[Any, str]]) -> Callable[[dict], tuple[Any, str]]:
            _REGISTRY[name] = CalcFunction(name=name, fn=f, doc=doc or (f.__doc__ or ""))
            return f
        return deco
    _REGISTRY[name] = CalcFunction(name=name, fn=fn, doc=doc)
    return fn


def list_functions(registry: "dict[str, CalcFunction] | None" = None) -> list[dict]:
    reg = registry if registry is not None else _REGISTRY
    return [{"name": f.name, "doc": f.doc} for f in sorted(reg.values(), key=lambda x: x.name)]


def _series(args: dict, key: str = "series") -> "list[float] | None":
    v = args.get(key)
    if not isinstance(v, (list, tuple)) or not v:
        return None
    try:
        return [float(x) for x in v]
    except (TypeError, ValueError):
        return None


def _num(args: dict, key: str) -> "float | None":
    v = args.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _register_builtins() -> None:
    @register_calc("pct_change", doc="(a, b) -> (a-b)/b 的百分比")
    def _pct_change(args: dict):
        a, b = _num(args, "a"), _num(args, "b")
        if a is None or b is None:
            raise ValueError("需要数值参数 a、b")
        if b == 0:
            raise ZeroDivisionError("b 为 0")
        return (a - b) / b * 100.0, "%"

    @register_calc("ratio", doc="(a, b) -> a/b")
    def _ratio(args: dict):
        a, b = _num(args, "a"), _num(args, "b")
        if a is None or b is None:
            raise ValueError("需要数值参数 a、b")
        if b == 0:
            raise ZeroDivisionError("除数为 0")
        return a / b, ""

    @register_calc("diff", doc="(a, b) -> a-b")
    def _diff(args: dict):
        a, b = _num(args, "a"), _num(args, "b")
        if a is None or b is None:
            raise ValueError("需要数值参数 a、b")
        return a - b, ""

    @register_calc("mean", doc="(series) -> 均值")
    def _mean(args: dict):
        s = _series(args)
        if s is None:
            raise ValueError("需要非空数值列表 series")
        return statistics.fmean(s), ""

    @register_calc("median", doc="(series) -> 中位数")
    def _median(args: dict):
        s = _series(args)
        if s is None:
            raise ValueError("需要非空数值列表 series")
        return statistics.median(s), ""

    @register_calc("std", doc="(series) -> 标准差（总体）")
    def _std(args: dict):
        s = _series(args)
        if s is None or len(s) < 2:
            raise ValueError("需要长度≥2 的数值列表 series")
        return statistics.pstdev(s), ""

    @register_calc("zscore", doc="(value, series) -> (value-mean)/std")
    def _zscore(args: dict):
        s = _series(args)
        v = _num(args, "value")
        if s is None or len(s) < 2 or v is None:
            raise ValueError("需要 value 与长度≥2 的 series")
        sd = statistics.pstdev(s)
        if sd == 0:
            raise ZeroDivisionError("series 无离散度")
        return (v - statistics.fmean(s)) / sd, ""

    @register_calc("percentile_rank", doc="(value, series) -> 历史分位百分比")
    def _percentile_rank(args: dict):
        s = _series(args)
        v = _num(args, "value")
        if s is None or v is None:
            raise ValueError("需要 value 与非空 series")
        below = sum(1 for x in s if x <= v)
        return below / len(s) * 100.0, "%"

    @register_calc("max_drawdown", doc="(series) -> 最大回撤百分比（绝对值）")
    def _max_drawdown(args: dict):
        s = _series(args)
        if s is None or len(s) < 2:
            raise ValueError("需要长度≥2 的 series")
        peak = -math.inf
        mdd = 0.0
        for x in s:
            peak = max(peak, x)
            if peak > 0:
                mdd = max(mdd, (peak - x) / peak)
        return mdd * 100.0, "%"

    @register_calc("volatility", doc="(series, periods_per_year=252) -> 年化波动率%")
    def _volatility(args: dict):
        s = _series(args)
        if s is None or len(s) < 2:
            raise ValueError("需要长度≥2 的 series")
        ppy = _num(args, "periods_per_year") or 252.0
        rets = [(s[i] / s[i - 1] - 1.0) for i in range(1, len(s)) if s[i - 1] != 0]
        if len(rets) < 2:
            raise ValueError("有效收益率不足")
        return statistics.pstdev(rets) * math.sqrt(ppy) * 100.0, "%"

    @register_calc("sum", doc="(series) -> 合计")
    def _sum(args: dict):
        s = _series(args)
        if s is None:
            raise ValueError("需要非空数值列表 series")
        return math.fsum(s), ""

    @register_calc("latest", doc="(series) -> 末值")
    def _latest(args: dict):
        s = _series(args)
        if s is None:
            raise ValueError("需要非空数值列表 series")
        return s[-1], ""


_register_builtins()


# ---------------------------------------------------------------------------
# 运行与复算
# ---------------------------------------------------------------------------

def run_calc(fn_name: str, args: dict, *,
             registry: "dict[str, CalcFunction] | None" = None,
             calc_version: str = CALC_VERSION) -> dict:
    """执行一个 calc 函数并返回信封。``list`` 是元命令（返回函数清单，不落盘）。"""
    if fn_name == "list":
        return {"functions": list_functions(registry)}
    reg = registry if registry is not None else _REGISTRY
    f = reg.get(fn_name)
    if f is None:
        return make_envelope(fn_name, args, status="error",
                             reason=f"未知函数: {fn_name}（可用 list 查看）",
                             calc_version=calc_version)
    if not isinstance(args, dict):
        return make_envelope(fn_name, args, status="error", reason="args 必须是对象",
                             calc_version=calc_version)
    try:
        value, unit = f.fn(args)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, IndexError) as exc:
        return make_envelope(fn_name, args, status="error", reason=f"{type(exc).__name__}: {exc}",
                             calc_version=calc_version)
    if isinstance(value, float) and not math.isfinite(value):
        return make_envelope(fn_name, args, status="not_meaningful",
                             reason="结果非有限数（NaN/Inf）", value=value,
                             calc_version=calc_version)
    return make_envelope(fn_name, args, status="ok", value=value, unit=unit,
                         calc_version=calc_version)


def _values_equal(a: Any, b: Any) -> bool:
    """数值按相对容差 1e-9 比对，其余精确相等。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b:
            return True
        scale = max(abs(float(a)), abs(float(b)))
        return abs(float(a) - float(b)) <= max(scale * 1e-9, 1e-12)
    return a == b


def verify_calc(record: dict, *,
                registry: "dict[str, CalcFunction] | None" = None) -> "bool | None":
    """同实参复算一条 calc 记录：status/value/unit 一致为 True，不一致为 False。

    calc_version 不同的记录跳过（返回 None，视为不适用）；error/not_meaningful 记录
    复算后仍是同 status 即一致（错误记录也是审计痕迹，改写才算篡改）。
    """
    if record.get("calc_version") != CALC_VERSION:
        return None
    again = run_calc(record.get("fn", ""), record.get("args", {}), registry=registry)
    if again.get("status") == "error" and record.get("status") == "error":
        # 双方都 error：同样炸即一致（args 未被篡改的前提下 error 确定性成立）
        return again.get("args") == record.get("args")
    if again.get("status") != record.get("status"):
        return False
    if not _values_equal(again.get("value"), record.get("value")):
        return False
    return again.get("unit") == record.get("unit")


def verify_calcs(records: "list[dict]", *,
                 registry: "dict[str, CalcFunction] | None" = None) -> list[dict]:
    """批量复算，返回不一致清单 [{calculation_id, fn, reason}]。"""
    bad = []
    for rec in records:
        ok = verify_calc(rec, registry=registry)
        if ok is False:
            bad.append({"calculation_id": rec.get("calculation_id"), "fn": rec.get("fn"),
                        "reason": "同实参复算不一致（记录可能被改写）"})
    return bad
