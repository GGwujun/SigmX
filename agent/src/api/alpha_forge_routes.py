"""AlphaForge 投研报告 HTTP routes for the Web UI.

Mounted by ``agent/api_server.py`` via ``register_alpha_forge_routes(app, ...)``.

Routes:
- ``GET  /alpha-forge/reports``                  — list saved reports
- ``GET  /alpha-forge/reports/{report_id}``       — report detail (MD + metadata)
- ``GET  /alpha-forge/reports/{report_id}/download`` — download MD or PDF
- ``POST /alpha-forge/runs``                      — create a new AlphaForge run
- ``GET  /alpha-forge/runs/{run_id}``             — get run status
- ``GET  /alpha-forge/runs/{run_id}/events``      — SSE live progress

Report storage: ``~/.vibe-trading/alpha_forge_reports/``
Each report: ``{report_id}/report.md`` + ``{report_id}/meta.json``
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from src.api.auth_routes import require_user  # JWT validator → returns user dict
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Report storage
# ---------------------------------------------------------------------------

REPORTS_ROOT = Path.home() / ".vibe-trading" / "alpha_forge_reports"


def _get_store():
    """Return a SwarmStore pointing at the SAME base_dir the runtime uses.

    The runtime (api_server._get_swarm_runtime) builds SwarmStore from
    ``swarm_runs_root()`` (agent/.swarm/runs). SwarmStore has NO default
    base_dir — ``SwarmStore()`` raises TypeError. We must reuse the exact
    same root so runs created by the runtime are visible here.
    """
    from src.swarm.store import SwarmStore, swarm_runs_root
    return SwarmStore(base_dir=swarm_runs_root())

# SSE manager singleton — populated by register_alpha_forge_routes
_sse_manager: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AlphaForgeRunRequest(BaseModel):
    target: str = Field(..., description="目标股票代码，如 300253.SZ")
    market: str = Field(default="A-shares", description="市场")

class AlphaForgeRunResponse(BaseModel):
    run_id: str
    status: str
    target: str
    market: str
    created_at: str

class ReportMeta(BaseModel):
    report_id: str
    target: str
    stock_name: str = ""
    market: str
    analysis_date: str
    created_at: str
    signal: str = ""  # BUY / SELL / HOLD
    rating: str = ""  # Overweight / Equal-weight / Underweight
    report_quality: str = "unknown"
    quality_warnings: list[str] = Field(default_factory=list)
    decision_warnings: list[str] = Field(default_factory=list)

class ReportListItem(BaseModel):
    report_id: str
    target: str
    stock_name: str
    market: str
    analysis_date: str
    created_at: str
    signal: str
    rating: str
    report_quality: str = "unknown"
    quality_warnings: list[str] = Field(default_factory=list)
    decision_warnings: list[str] = Field(default_factory=list)

class ReportDetail(BaseModel):
    report_id: str
    target: str
    stock_name: str
    market: str
    analysis_date: str
    created_at: str
    signal: str
    rating: str
    content_md: str
    report_quality: str = "unknown"
    quality_warnings: list[str] = Field(default_factory=list)
    decision_warnings: list[str] = Field(default_factory=list)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_reports_root() -> None:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    """Remove dangerous characters from filenames."""
    return re.sub(r"[<>:\"/\\|?*]", "_", name)


def _extract_metadata_from_md(content: str) -> dict[str, str]:
    """Extract metadata from AlphaForge markdown report.

    Prefers machine-readable blocks (``<!-- DECISION: {json} -->`` from the
    trader, ``<!-- VERDICT: {json} -->`` from the PM) for the structured
    fields (signal/rating/prices); falls back to frontmatter regex scraping so
    older reports without blocks still work.
    """
    meta: dict[str, str] = {}
    decision = _parse_decision_block(content, "DECISION")
    verdict = _parse_decision_block(content, "VERDICT")

    lines = content.split("\n")
    for line in lines[:20]:
        line = line.strip()
        if line.startswith("- **股票代码**") or line.startswith("- **股票代码**："):
            m = re.search(r"[：:]\s*(\S+)", line)  # 只匹配冒号后的值
            if m: meta["target"] = m.group(1)
        elif line.startswith("- **股票名称**") or line.startswith("- **股票名称**："):
            m = re.search(r"[：:]\s*([^*\s]+)", line)
            if m: meta["stock_name"] = m.group(1).strip()
        elif "**分析日期**" in line:
            m = re.search(r"[：:]\s*(\S+)", line)  # 只匹配冒号后的值
            if m: meta["analysis_date"] = m.group(1)
        elif "**生成时间**" in line:
            m = re.search(r"[-：:]\s*(\S+)", line)
            if m: meta["created_at"] = m.group(1)
        elif "**交易信号**" in line:
            # Match both pure keywords (卖出) and compound forms (卖出（减仓规避）)
            m = re.search(r"\*\*(卖出|买入|持有|BUY|SELL|HOLD|减持|减仓)[^\*]*\*\*", line)
            if m:
                # Extract the core signal (first matched keyword)
                core = m.group(1)
                # Normalize: 减仓/减持 → 卖出
                if core in ("减仓", "减持"):
                    core = "卖出"
                meta.setdefault("signal", core)
        elif "FINAL TRANSACTION PROPOSAL" in line:
            m = re.search(r"\*\*(SELL|BUY|HOLD)\*\*", line)
            if m: meta.setdefault("signal", m.group(1))
        elif "**投资评级" in line or "最终投资评级" in line:
            m = re.search(r"[：:]\s*\**(\S+)\**", line)
            if m: meta.setdefault("rating", m.group(1).strip("*"))

    # Machine-readable blocks override the regex scraping when present.
    # VERDICT (PM, final) wins over DECISION (trader) for action/rating.
    src = {**(decision or {}), **(verdict or {})}
    if src:
        action = src.get("action", "").upper()
        # Map action variants to standard Chinese signals
        action_map = {
            "BUY": "买入",
            "SELL": "卖出",
            "HOLD": "持有",
            "REDUCE": "卖出",  # 减仓/减持 → 卖出
            "ACCUMULATE": "买入",  # 加仓 → 买入
        }
        action_cn = action_map.get(action, action)
        if action_cn:
            meta["signal"] = action_cn
        rating = src.get("rating")
        if rating:
            meta["rating"] = rating
        for field, key in (("entry", "entry"), ("target", "target"), ("stop", "stop_loss"), ("size_pct", "size_pct")):
            val = src.get(field)
            if val not in (None, 0, "0", ""):
                meta[key] = str(val)
    return meta


def _normalize_a_share_code(raw: str) -> str:
    value = (raw or "").strip().upper()
    m = re.fullmatch(r"(\d{6})(?:\.(SZ|SH|BJ))?", value)
    if not m:
        return value
    code, suffix = m.group(1), m.group(2)
    if suffix:
        return f"{code}.{suffix}"
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    if code.startswith(("43", "83", "87", "92")):
        return f"{code}.BJ"
    return code


def _resolve_stock_identity(raw: str, market: str) -> tuple[str, str]:
    """Resolve stock code/name from structured stock-basic data, not report text."""
    value = (raw or "").strip()
    if not value:
        return "", ""
    if market != "A-shares":
        return value, ""

    try:
        from src.api import position_routes as pr

        # Ensure the stock-basic cache is loaded once, then use both directions.
        if not getattr(pr, "_STOCK_NAMES_LOADED", False):
            pr._load_stock_names_batch()
        names: dict[str, str] = getattr(pr, "_STOCK_NAMES", {}) or {}

        code = _normalize_a_share_code(value)
        if re.fullmatch(r"\d{6}\.(SZ|SH|BJ)", code):
            name = pr._get_stock_name(code)
            return code, "" if name == code else name

        for ts_code, name in names.items():
            if name == value:
                return ts_code, name
    except Exception:
        logger.debug("AlphaForge stock identity lookup failed for %s", raw, exc_info=True)

    return _normalize_a_share_code(value), ""


def _assess_report_quality(content: str) -> dict[str, Any]:
    """Flag reports that are visibly data-incomplete or internally inconsistent."""
    text = content or ""
    checks = [
        ("数据管道未执行", "数据管道未执行"),
        ("数据状态：完全缺失", "存在完全缺失的数据模块"),
        ("完全缺失", "存在完全缺失的数据模块"),
        ("上游未提供", "部分关键字段由上游缺失"),
        ("无法计算", "部分指标无法计算"),
        ("数据一致性说明", "报告包含数据一致性说明"),
        ("可信度存疑", "报告自行标注可信度存疑"),
        ("数据冲突", "报告存在数据冲突"),
        ("FINAL TRANSACTION PROPOSAL", "报告泄露上游交易员过程文本"),
        ("让我计算", "报告泄露 Agent 计算过程文本"),
        ("现在我来", "报告泄露 Agent 写作过程文本"),
        ("我将整理", "报告泄露 Agent 写作过程文本"),
        ("从数据中提取", "报告泄露 Agent 数据处理过程文本"),
        ("必涨", "报告包含夸张荐股式表达"),
        ("稳赚", "报告包含夸张荐股式表达"),
        ("无脑买", "报告包含夸张荐股式表达"),
        ("满仓", "报告包含高风险荐股式表达"),
    ]
    warnings: list[str] = []
    for needle, warning in checks:
        if needle in text and warning not in warnings:
            warnings.append(warning)
    quality = "ok"
    if warnings:
        quality = "degraded"
    process_warnings = {
        "报告泄露上游交易员过程文本",
        "报告泄露 Agent 计算过程文本",
        "报告泄露 Agent 写作过程文本",
        "报告泄露 Agent 数据处理过程文本",
        "报告包含夸张荐股式表达",
        "报告包含高风险荐股式表达",
    }
    if any(w in warnings for w in ("数据管道未执行", "存在完全缺失的数据模块")) and len(warnings) >= 3:
        quality = "unreliable"
    elif any(w in process_warnings for w in warnings):
        quality = "degraded"
    return {"report_quality": quality, "quality_warnings": warnings[:6]}


def _merge_quality_checks(*checks: dict[str, Any]) -> dict[str, Any]:
    rank = {"ok": 0, "unknown": 0, "degraded": 1, "unreliable": 2}
    quality = "ok"
    warnings: list[str] = []
    for check in checks:
        candidate = str(check.get("report_quality") or "ok")
        if rank.get(candidate, 0) > rank.get(quality, 0):
            quality = candidate
        for warning in check.get("quality_warnings") or []:
            text = str(warning).strip()
            if text and text not in warnings:
                warnings.append(text)
    return {"report_quality": quality, "quality_warnings": warnings[:12]}


def _read_agent_report(run_dir: Path, agent_id: str) -> str:
    artifacts_dir = run_dir / "artifacts" / agent_id
    for filename in ("report.md", "summary.md"):
        path = artifacts_dir / filename
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8").strip()
            except Exception:
                logger.debug("Failed to read AlphaForge artifact %s", path, exc_info=True)
    return ""


def _extract_gate_decision(text: str) -> str:
    if not text:
        return ""
    machine = re.search(r"<!--\s*QUALITY_GATE:\s*(\{.*?\})\s*-->", text, re.IGNORECASE | re.DOTALL)
    if machine:
        try:
            payload = json.loads(machine.group(1))
            decision = str(payload.get("decision") or "").strip().upper().replace("_", " ")
            if decision in {"PASS", "CONDITIONAL PASS", "FAIL"}:
                return decision
        except Exception:
            logger.debug("Failed to parse AlphaForge QUALITY_GATE block", exc_info=True)
    patterns = [
        r"Gate\s*Decision\s*[:：\-]?\s*(CONDITIONAL\s+PASS|FAIL|PASS)",
        r"门控(?:结论|决定)?\s*[:：\-]?\s*(CONDITIONAL\s+PASS|FAIL|PASS|有条件通过|失败|通过)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().upper()
            if "FAIL" in value or "失败" in value:
                return "FAIL"
            if "CONDITIONAL" in value or "有条件" in value:
                return "CONDITIONAL PASS"
            if "PASS" in value or "通过" in value:
                return "PASS"
    return ""


def _parse_quality_gate_block(text: str) -> dict[str, Any]:
    if not text:
        return {}
    machine = re.search(r"<!--\s*QUALITY_GATE:\s*(\{.*?\})\s*-->", text, re.IGNORECASE | re.DOTALL)
    if not machine:
        return {}
    try:
        payload = json.loads(machine.group(1))
    except Exception:
        logger.debug("Failed to parse AlphaForge QUALITY_GATE payload", exc_info=True)
        return {}
    return payload if isinstance(payload, dict) else {}


_AGENT_DATA_CHECKLISTS: dict[str, list[tuple[str, str]]] = {
    "technical_analyst": [
        ("最新收盘价/权威价格", r"最新收盘价|latest\s+close|收盘价"),
        ("近30日涨跌幅", r"近\s*30\s*日|30-day"),
        ("5日/20日均量或量比", r"近\s*5\s*日.*近\s*20\s*日|量比|5d/20d"),
        ("MACD", r"MACD|DIF|DEA"),
        ("RSI", r"RSI"),
        ("支撑/阻力位", r"支撑|阻力"),
    ],
    "sentiment_analyst": [
        ("新闻/讨论样本数量", r"新闻.*条|样本|来源数量|source"),
        ("时间范围", r"时间范围|近\s*\d+\s*(天|日|周)|start|end"),
        ("正负中性分类", r"正面|负面|中性"),
        ("Top舆情主题", r"Top\s*3|舆情主题|主题"),
        ("情绪评分/趋势", r"情绪评分|极度乐观|乐观|悲观|升温|降温|平稳"),
    ],
    "news_analyst": [
        ("新闻数量/时间范围", r"新闻.*条|时间范围|近一个月|近\s*\d+\s*(天|日|周)"),
        ("事件时间线", r"时间线|日期.*事件|关键事件"),
        ("利好/利空/中性统计", r"利好|利空|中性"),
        ("风险事件清单", r"风险事件|风险清单"),
        ("新闻来源", r"来源|http|证券|公告|财联社|东方财富|同花顺"),
    ],
    "fundamental_analyst": [
        ("PE/PB/市值", r"PE|PB|市值"),
        ("营收/收入", r"营收|收入|revenue"),
        ("归母净利润", r"归母|净利润|net profit"),
        ("ROE/盈利能力", r"ROE|净资产收益率|盈利能力"),
        ("资产负债率/杠杆", r"资产负债率|负债|杠杆"),
        ("经营现金流", r"经营.*现金流|operating\s+CF|OCF"),
    ],
    "policy_analyst": [
        ("政策事件清单", r"政策事件|政策.*清单|发布"),
        ("发布机构/来源", r"国务院|证监会|发改委|央行|财政部|工信部|医保局|发布机构|来源"),
        ("政策方向", r"扶持|限制|压制|中性|利好|利空"),
        ("影响力度", r"强|中|弱|影响力度"),
        ("时间窗口", r"短期|中期|长期|时间窗口"),
    ],
    "capital_flow_analyst": [
        ("5日成交量趋势", r"近\s*5\s*日|5日.*成交量"),
        ("主力资金", r"主力|超大单|大单"),
        ("北向资金", r"北向|沪股通|深股通"),
        ("龙虎榜", r"龙虎榜|席位"),
        ("概念/行业板块", r"概念|板块|行业"),
        ("资金面总体判断", r"资金面总体|资金.*判断|主力流入|主力流出"),
    ],
    "global_market_analyst": [
        ("美股指数", r"道琼|纳指|标普|美股|S&P|NASDAQ|Dow"),
        ("大宗商品", r"原油|黄金|铜|大宗"),
        ("汇率/人民币", r"美元|人民币|USD|CNY|汇率"),
        ("传导路径", r"传导|影响判断|利好|利空|中性"),
    ],
    "lockup_analyst": [
        ("股本结构", r"股本|流通股|总股本"),
        ("未来90天解禁", r"未来\s*90\s*天|90天|解禁计划"),
        ("内部人/大股东交易", r"内部人|高管|大股东|减持|增持"),
        ("前十大股东", r"前十大股东|十大股东"),
        ("减持压力评级", r"减持压力|无压力|轻微压力|中等压力|严重压力"),
    ],
}


def _agent_data_coverage_check(run_dir: Path) -> dict[str, Any]:
    warnings: list[str] = []
    quality = "ok"
    total_missing = 0
    critical_agents = {"technical_analyst", "fundamental_analyst", "capital_flow_analyst", "lockup_analyst"}

    for agent_id, checklist in _AGENT_DATA_CHECKLISTS.items():
        report = _read_agent_report(run_dir, agent_id)
        if not report:
            continue
        missing = [
            label
            for label, pattern in checklist
            if not re.search(pattern, report, re.IGNORECASE)
        ]
        explicit_missing = re.findall(r"\[数据缺失[:：]\s*([^\]\n]+)\]", report)
        if missing:
            total_missing += len(missing)
            shown = "、".join(missing[:4])
            suffix = "等" if len(missing) > 4 else ""
            warnings.append(f"{agent_id} 缺少关键数据项：{shown}{suffix}")
            if agent_id in critical_agents and len(missing) >= 2:
                quality = "unreliable"
            elif quality != "unreliable":
                quality = "degraded"
        if len(explicit_missing) >= 3 and quality != "unreliable":
            warnings.append(f"{agent_id} 显式标注 {len(explicit_missing)} 个数据缺失项")
            quality = "degraded"

    if total_missing >= 10:
        quality = "unreliable"
    return {"report_quality": quality, "quality_warnings": warnings[:10]}


def _artifact_quality_check(run_dir: Path, *, content_source: str) -> dict[str, Any]:
    warnings: list[str] = []
    quality = "ok"

    data_report = _read_agent_report(run_dir, "data_collector")
    if not data_report:
        warnings.append("共享事实表缺失，无法确认权威价格/成交量/估值基线")
        quality = "unreliable"
    else:
        missing_count = data_report.count("数据缺失") + data_report.lower().count("n/a")
        if missing_count >= 5:
            warnings.append("共享事实表存在大量数据缺失")
            quality = "unreliable"
        elif missing_count > 0:
            warnings.append("共享事实表存在部分数据缺失")
            quality = "degraded"
        if not re.search(r"(最新收盘价|latest\s+close)[^\n\r]{0,40}\d+(?:\.\d+)?", data_report, re.IGNORECASE):
            warnings.append("共享事实表缺少可识别的权威最新收盘价")
            quality = "unreliable"
        evidence_sections = [
            ("技术原始数据摘要", r"技术原始数据|OHLCV|最近5日"),
            ("财务与估值基线", r"财务与估值|营收|归母|ROE|经营现金流"),
            ("新闻与政策证据", r"新闻与政策|新闻检索|政策事件|Top事件"),
            ("资金与板块证据", r"资金与板块|主力资金|北向|龙虎榜|概念板块"),
            ("解禁与内部人证据", r"解禁与内部人|未来90天|内部人|回购"),
            ("国际市场快照", r"国际市场|美股|原油|黄金|汇率|人民币"),
            ("数据缺口清单", r"数据缺口清单|缺失字段"),
        ]
        missing_sections = [
            label for label, pattern in evidence_sections
            if not re.search(pattern, data_report, re.IGNORECASE)
        ]
        if missing_sections:
            warnings.append("共享证据包缺少章节：" + "、".join(missing_sections[:5]))
            if len(missing_sections) >= 3:
                quality = "unreliable"
            elif quality != "unreliable":
                quality = "degraded"

    gate_report = _read_agent_report(run_dir, "quality_gate")
    gate_decision = _extract_gate_decision(gate_report)
    gate_payload = _parse_quality_gate_block(gate_report)
    if not gate_report:
        warnings.append("质量门控报告缺失")
        quality = "unreliable"
    elif gate_decision == "FAIL":
        warnings.append("质量门控结论为 FAIL")
        quality = "unreliable"
    elif gate_decision == "CONDITIONAL PASS":
        warnings.append("质量门控结论为 CONDITIONAL PASS")
        if quality != "unreliable":
            quality = "degraded"
    elif not gate_decision:
        warnings.append("质量门控未给出可解析的 PASS/FAIL 结论")
        if quality != "unreliable":
            quality = "degraded"
    if gate_payload:
        critical_missing = int(gate_payload.get("critical_missing_count") or 0)
        moderate_missing = int(gate_payload.get("moderate_missing_count") or 0)
        low_confidence_agents = gate_payload.get("low_confidence_agents") or []
        process_leakage_agents = gate_payload.get("process_leakage_agents") or []
        blocking_issues = gate_payload.get("blocking_issues") or []
        if critical_missing > 0:
            warnings.append(f"质量门控识别 {critical_missing} 个关键缺失项")
            quality = "unreliable"
        elif moderate_missing > 0 and quality != "unreliable":
            warnings.append(f"质量门控识别 {moderate_missing} 个中等缺失项")
            quality = "degraded"
        if low_confidence_agents:
            warnings.append("低可信 Agent：" + "、".join(map(str, low_confidence_agents[:5])))
            if quality != "unreliable":
                quality = "degraded"
        if process_leakage_agents:
            warnings.append("存在过程文本泄露 Agent：" + "、".join(map(str, process_leakage_agents[:5])))
            if quality != "unreliable":
                quality = "degraded"
        if blocking_issues:
            warnings.append("质量门控阻塞问题：" + "；".join(map(str, blocking_issues[:3])))
            quality = "unreliable"

    expected_agents = [agent_id for agent_id, _, _ in _AGENT_SECTIONS] + ["report_writer"]
    missing_agents = [agent_id for agent_id in expected_agents if not _read_agent_report(run_dir, agent_id)]
    if missing_agents:
        sample = "、".join(missing_agents[:5])
        suffix = "等" if len(missing_agents) > 5 else ""
        warnings.append(f"{len(missing_agents)} 个 Agent 缺少可归档产物：{sample}{suffix}")
        if len(missing_agents) >= 3:
            quality = "unreliable"
        elif quality != "unreliable":
            quality = "degraded"

    if content_source != "report_writer":
        warnings.append("最终报告未使用 report_writer 统一报告，而是由上游片段拼接生成")
        if quality != "unreliable":
            quality = "degraded"

    return {"report_quality": quality, "quality_warnings": warnings}


def _decision_quality_check(decision_warnings: list[str]) -> dict[str, Any]:
    if not decision_warnings:
        return {"report_quality": "ok", "quality_warnings": []}
    severe_markers = ("方向与价位", "超过 100%", "单位错误", "无保护")
    quality = "unreliable" if any(any(marker in w for marker in severe_markers) for w in decision_warnings) else "degraded"
    return {
        "report_quality": quality,
        "quality_warnings": [f"交易决策硬校验告警：{w}" for w in decision_warnings[:4]],
    }


def _content_with_quality_notice(content: str, meta: dict[str, Any]) -> str:
    quality = str(meta.get("report_quality") or "unknown")
    warnings = [str(w) for w in (meta.get("quality_warnings") or []) if str(w).strip()]
    decision_warnings = [str(w) for w in (meta.get("decision_warnings") or []) if str(w).strip()]
    if quality == "ok" and not decision_warnings:
        return content

    label = {
        "unreliable": "数据质量不可信，不建议直接作为投研结论使用",
        "degraded": "数据质量存疑，阅读时需核对关键数据",
        "unknown": "数据质量未校验",
    }.get(quality, "数据质量需复核")
    lines = [
        "> [!WARNING]",
        f"> **报告质量提示**：{label}",
    ]
    for warning in warnings[:8]:
        lines.append(f"> - {warning}")
    for warning in decision_warnings[:4]:
        lines.append(f"> - 交易决策校验：{warning}")
    return "\n".join(lines) + "\n\n" + content


def _parse_decision_block(content: str, tag: str) -> dict | None:
    """Parse a ``<!-- {tag}: {json} -->`` machine-readable block.

    Returns the parsed JSON dict, or None if absent/malformed. The block is
    emitted by the trader (DECISION) and PM (VERDICT) agents so downstream code
    can rely on structured fields instead of scraping free-text markdown.
    """
    # Take the last occurrence (most final).
    matches = list(re.finditer(rf"<!--\s*{tag}\s*:\s*(\{{.*?\}})\s*-->", content, re.S))
    if not matches:
        return None
    try:
        return json.loads(matches[-1].group(1))
    except (ValueError, json.JSONDecodeError):
        return None


def _list_report_dirs() -> list[Path]:
    """List all report directories sorted by creation time (newest first)."""
    _ensure_reports_root()
    dirs = [d for d in REPORTS_ROOT.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs


def _load_report_meta(report_id: str) -> dict[str, Any] | None:
    """Load report metadata from meta.json."""
    meta_path = REPORTS_ROOT / report_id / "meta.json"
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text(encoding="utf-8-sig"))


def _load_report_md(report_id: str) -> str | None:
    """Load report markdown content."""
    md_path = REPORTS_ROOT / report_id / "report.md"
    if not md_path.exists():
        return None
    return md_path.read_text(encoding="utf-8")


def _save_report(report_id: str, content_md: str, meta: dict[str, Any]) -> Path:
    """Save a report to disk. Returns the report directory path."""
    _ensure_reports_root()
    report_dir = REPORTS_ROOT / report_id
    report_dir.mkdir(parents=True, exist_ok=True)

    (report_dir / "report.md").write_text(content_md, encoding="utf-8")
    (report_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _task_display_status(task: Any) -> dict[str, str]:
    """Return user-facing task status while preserving scheduler status.

    The swarm scheduler uses ``blocked`` for two different states:
    1. waiting for upstream dependencies at run start;
    2. truly blocked because an upstream task failed or is missing.

    The UI should not show the first state as a failure.
    """
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    blocked_by = list(getattr(task, "blocked_by", []) or [])
    error = getattr(task, "error", None)
    if status == "blocked" and blocked_by and not error:
        return {"display_status": "waiting", "display_status_label": "等待上游"}
    labels = {
        "pending": "等待中",
        "in_progress": "执行中",
        "completed": "已完成",
        "failed": "失败",
        "blocked": "已阻塞",
        "cancelled": "已取消",
    }
    return {"display_status": status, "display_status_label": labels.get(status, status or "暂无状态")}


# Pipeline order for assembling the full report. Each entry maps an agent_id
# to (display section title, layer label). Ordered top-to-bottom = how the
# final report reads.
_AGENT_SECTIONS: list[tuple[str, str, str]] = [
    # Layer 1 — parallel research (8 analysts)
    ("technical_analyst", "技术分析", "第一部分：多维度研究"),
    ("sentiment_analyst", "情绪分析", "第一部分：多维度研究"),
    ("news_analyst", "新闻舆情", "第一部分：多维度研究"),
    ("fundamental_analyst", "基本面分析", "第一部分：多维度研究"),
    ("policy_analyst", "政策分析", "第一部分：多维度研究"),
    ("capital_flow_analyst", "资金面分析", "第一部分：多维度研究"),
    ("lockup_analyst", "解禁 / 减持监控", "第一部分：多维度研究"),
    ("global_market_analyst", "国际市场影响", "第一部分：多维度研究"),
    # Layer 2 — quality gate
    ("quality_gate", "质量门控结论", "第二部分：质量门控"),
    # Layer 3 — debate
    ("bull_case", "多方论证", "第三部分：多空辩论"),
    ("bear_case", "空方论证", "第三部分：多空辩论"),
    ("bull_rebuttal", "多方反驳（第二轮）", "第三部分：多空辩论"),
    ("bear_rebuttal", "空方反驳（第二轮）", "第三部分：多空辩论"),
    ("neutral_synthesis", "中性综合", "第三部分：多空辩论"),
    # Layer 4-6 — decision chain
    ("trader", "交易决策", "第四部分：交易决策"),
    ("aggressive_risk_analyst", "激进风险分析", "第五部分：三方风险辩论"),
    ("neutral_risk_analyst", "中性风险分析", "第五部分：三方风险辩论"),
    ("conservative_risk_analyst", "保守风险分析", "第五部分：三方风险辩论"),
    ("risk_officer", "风控裁决", "第六部分：风控裁决"),
    ("portfolio_manager", "最终决策", "第七部分：最终决策"),
]


def _assemble_full_report(run_dir: Path, target: str, stock_name: str) -> str:
    """Assemble the complete report by concatenating every agent's report.md.

    Walks ``run_dir/artifacts/<agent_id>/report.md`` in pipeline order and
    stitches them under structured section headers. Agents that produced no
    report.md (failed / produced text only) are noted as "（无输出）" so the
    reader can see what evidence was actually gathered.

    Args:
        run_dir: The swarm run directory (.swarm/runs/<run_id>).
        target: Stock code (e.g. "300253.SZ").
        stock_name: Resolved stock name (e.g. "卫宁健康").

    Returns:
        The full markdown report string.
    """
    artifacts_dir = run_dir / "artifacts"
    parts: list[str] = []

    # --- Header ---
    display_name = f"{target}" + (f"（{stock_name}）" if stock_name else "")
    header = [
        "# AlphaForge 投研分析报告",
        "",
        f"- **股票代码**：{target}",
    ]
    if stock_name:
        header.append(f"- **股票名称**：{stock_name}")
    header.extend([
        f"- **分析日期**：{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "- **报告类型**：AI 多 Agent 全流程投研报告（14 Agent / 6 层流水线）",
        "",
        "> ⚠️ 本报告由 AI 多 Agent 系统自动生成，仅供学习研究与技术演示，不构成任何投资建议。"
        "投资决策请咨询持牌专业机构，使用本报告所产生的任何损失由使用者自行承担。",
        "",
        "---",
        "",
    ])
    parts.append("\n".join(header))

    # --- Per-agent sections, grouped by layer ---
    current_layer = None
    for agent_id, title, layer in _AGENT_SECTIONS:
        # Emit a layer header when the layer changes
        if layer != current_layer:
            current_layer = layer
            parts.append(f"\n# {layer}\n")

        report_path = artifacts_dir / agent_id / "report.md"
        if report_path.is_file():
            body = report_path.read_text(encoding="utf-8").strip()
        else:
            # Fall back to summary.md if report.md is missing
            summary_path = artifacts_dir / agent_id / "summary.md"
            if summary_path.is_file():
                body = summary_path.read_text(encoding="utf-8").strip()
            else:
                body = "（该环节未产出可归档内容）"

        parts.append(f"\n## {title}\n")
        parts.append(body)
        parts.append("")  # blank line separator

    return "\n".join(parts).strip() + "\n"

    return report_dir


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_alpha_forge_routes(
    app: FastAPI,
    require_auth: Callable[[Request], Awaitable[None]],
    require_event_stream_auth: Callable[[Request], Awaitable[None]],
    get_swarm_runtime: Callable[[], Any] | None = None,
) -> None:
    """Register AlphaForge routes on the FastAPI app.

    Args:
        get_swarm_runtime: Callable that returns the SwarmRuntime singleton.
            Passed from api_server.py's _get_swarm_runtime().
    """

    # ── List Reports ──────────────────────────────────────────────
    @app.get("/alpha-forge/reports")
    async def list_reports(request: Request, _=Depends(require_auth)):
        """List all saved AlphaForge reports."""
        reports: list[dict] = []
        for d in _list_report_dirs():
            meta = _load_report_meta(d.name)
            if meta:
                reports.append({
                    "report_id": d.name,
                    "target": meta.get("target", d.name),
                    "stock_name": meta.get("stock_name", ""),
                    "market": meta.get("market", "A-shares"),
                    "analysis_date": meta.get("analysis_date", ""),
                    "created_at": meta.get("created_at", ""),
                    "signal": meta.get("signal", ""),
                    "rating": meta.get("rating", ""),
                    "report_quality": meta.get("report_quality", "unknown"),
                    "quality_warnings": meta.get("quality_warnings", []),
                    "decision_warnings": meta.get("decision_warnings", []),
                })
        return reports

    # ── Get Report Detail ─────────────────────────────────────────
    @app.get("/alpha-forge/reports/{report_id}")
    async def get_report(report_id: str, request: Request, _=Depends(require_auth)):
        """Get a full report with markdown content."""
        meta = _load_report_meta(report_id)
        content = _load_report_md(report_id)
        if meta is None or content is None:
            raise HTTPException(status_code=404, detail=f"Report {report_id!r} not found")

        return {
            "report_id": report_id,
            "target": meta.get("target", ""),
            "stock_name": meta.get("stock_name", ""),
            "market": meta.get("market", "A-shares"),
            "analysis_date": meta.get("analysis_date", ""),
            "created_at": meta.get("created_at", ""),
            "signal": meta.get("signal", ""),
            "rating": meta.get("rating", ""),
            "content_md": content,
            "report_quality": meta.get("report_quality", "unknown"),
            "quality_warnings": meta.get("quality_warnings", []),
            "decision_warnings": meta.get("decision_warnings", []),
        }

    # ── Download Report ───────────────────────────────────────────
    @app.get("/alpha-forge/reports/{report_id}/download")
    async def download_report(
        report_id: str,
        request: Request,
        format: str = Query("md", description="Download format: md or pdf"),
        _=Depends(require_auth),
    ):
        """Download a report as MD or PDF."""
        meta = _load_report_meta(report_id)
        content = _load_report_md(report_id)
        if meta is None or content is None:
            raise HTTPException(status_code=404, detail=f"Report {report_id!r} not found")

        target = meta.get("target", report_id)
        filename_base = f"AlphaForge_{target}_{meta.get('analysis_date', 'unknown')}"
        downloadable_content = _content_with_quality_notice(content, meta)

        if format == "md":
            return Response(
                content=downloadable_content,
                media_type="text/markdown; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{_sanitize_filename(filename_base)}.md"',
                },
            )

        if format == "pdf":
            # Check if PDF already exists (cached)
            pdf_path = REPORTS_ROOT / report_id / "report.pdf"
            if pdf_path.exists() and downloadable_content == content:
                return FileResponse(
                    pdf_path,
                    media_type="application/pdf",
                    filename=f"{_sanitize_filename(filename_base)}.pdf",
                )

            # Generate PDF with weasyprint
            try:
                import markdown as md_lib
                from weasyprint import HTML

                # Convert MD to HTML
                md_html = md_lib.markdown(
                    downloadable_content,
                    extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"],
                )

                html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: "Microsoft YaHei", "SimSun", sans-serif; font-size: 13px; line-height: 1.7; max-width: 210mm; margin: auto; padding: 20px; color: #333; }}
  h1 {{ font-size: 22px; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #999; padding-bottom: 4px; margin-top: 28px; }}
  h3 {{ font-size: 15px; margin-top: 20px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 11px; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: bold; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 10px 0; padding: 6px 16px; background: #f9f9f9; }}
  code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-size: 12px; }}
  pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 20px 0; }}
</style>
</head>
<body>{md_html}</body>
</html>"""

                pdf_bytes = HTML(string=html_template).write_pdf()
                # Cache PDF
                pdf_path.write_bytes(pdf_bytes)

                return Response(
                    content=pdf_bytes,
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f'attachment; filename="{_sanitize_filename(filename_base)}.pdf"',
                    },
                )
            except ImportError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF generation dependency missing: {e}. Install weasyprint and markdown.",
                )
            except Exception as e:
                logger.error("PDF generation failed for %s: %s", report_id, e, exc_info=True)
                raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

        raise HTTPException(status_code=400, detail=f"Unknown format: {format!r}. Use 'md' or 'pdf'.")

    # ── Create AlphaForge Run ─────────────────────────────────────
    @app.post("/alpha-forge/runs")
    async def create_alpha_forge_run(
        body: AlphaForgeRunRequest,
        request: Request,
        user=Depends(require_user),
    ):
        """Create a new AlphaForge analysis run using the swarm preset."""
        from src.swarm.presets import build_run_from_preset
        from src.swarm.store import SwarmStore

        if get_swarm_runtime is None:
            raise HTTPException(
                status_code=503,
                detail="Swarm runtime not available. The server was started without swarm support.",
            )

        swarm_runtime = get_swarm_runtime()

        try:
            swarm_run = swarm_runtime.start_run(
                preset_name="alpha_forge",
                user_vars={"target": body.target, "market": body.market},
            )
        except Exception as e:
            logger.error("Failed to start alpha_forge run: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to start run: {e}")

        # ── Credits: consume after the run is created (so run_id is the ref) ──
        from src.credits.store import CreditStore
        from src.credits.constants import COST_ALPHA_FORGE
        credits = CreditStore()
        if not credits.consume(user["id"], COST_ALPHA_FORGE, swarm_run.id, f"AlphaForge {body.target}"):
            # Couldn't bill — cancel the just-started run and refuse.
            try:
                swarm_runtime.cancel_run(swarm_run.id)
            except Exception:
                pass
            raise HTTPException(
                status_code=402,
                detail=f"积分不足，本次分析需要 {COST_ALPHA_FORGE} 积分",
            )
        billing_user_id = user["id"]

        # Register a completion callback to save the report
        def _on_run_complete(run_id: str) -> None:
            """Save the full assembled report when the swarm run completes."""
            try:
                store = _get_store()
                run_dir = store.run_dir(run_id)
                completed_run = store.load_run(run_id)

                resolved_target, stock_name = _resolve_stock_identity(body.target, body.market)
                target_for_report = resolved_target or body.target

                # Choose the final report content.
                # Preferred: the report_writer agent's unified report (ONE coherent
                # document, written per the strict skeleton). Falls back to the
                # multi-agent assembly only if report_writer produced nothing.
                writer_path = run_dir / "artifacts" / "report_writer" / "report.md"
                if writer_path.is_file():
                    writer_content = writer_path.read_text(encoding="utf-8").strip()
                    if len(writer_content) > 500:  # sanity: real report, not a stub
                        content = writer_content
                        content_source = "report_writer"
                        logger.info("Using report_writer unified report for %s", body.target)
                    else:
                        content = _assemble_full_report(run_dir, target_for_report, stock_name)
                        content_source = "assembly"
                        logger.info("report_writer output too short, falling back to assembly for %s", body.target)
                else:
                    content = _assemble_full_report(run_dir, target_for_report, stock_name)
                    content_source = "assembly"
                    logger.info("No report_writer output, using assembly for %s", body.target)

                # Generate report ID
                now = datetime.now(timezone.utc)
                ts = now.strftime("%Y%m%d-%H%M%S")
                report_id = f"af_{body.target.replace('.', '_')}_{ts}"

                meta = {
                    "target": target_for_report,
                    "stock_name": stock_name,
                    "market": body.market,
                    "analysis_date": now.strftime("%Y-%m-%d"),
                    "created_at": now.isoformat(),
                    "run_id": run_id,
                }
                # Extract signal and rating from the PM section
                extra = _extract_metadata_from_md(content)
                extra.pop("stock_name", None)
                meta.update(extra)
                if body.market == "A-shares":
                    meta["target"], meta["stock_name"] = _resolve_stock_identity(str(meta.get("target") or target_for_report), body.market)

                # Validate the LLM decision against hard A-share rules (stop
                # ordering, position bounds, daily-limit sanity). Warnings are
                # surfaced in metadata; nothing is auto-corrected.
                decision_warnings: list[str] = []
                try:
                    from src.analysis.decision_validator import fetch_latest_price, validate_stock_decision
                    price = fetch_latest_price(body.target)
                    decision_warnings = validate_stock_decision(meta, latest_price=price)
                    if decision_warnings:
                        meta["decision_warnings"] = decision_warnings
                        logger.warning("AlphaForge %s decision warnings: %s", body.target, decision_warnings)
                except Exception as exc:  # noqa: BLE001 — validation must never block save
                    logger.debug("decision validation skipped: %s", exc)

                meta.update(_merge_quality_checks(
                    _assess_report_quality(content),
                    _artifact_quality_check(run_dir, content_source=content_source),
                    _agent_data_coverage_check(run_dir),
                    _decision_quality_check(decision_warnings),
                ))

                _save_report(report_id, content, meta)
                logger.info("Saved AlphaForge report %s for %s", report_id, body.target)
            except Exception as e:
                logger.error("Failed to save AlphaForge report for run %s: %s", run_id, e, exc_info=True)

        # Register callback with the runtime
        swarm_runtime._live_callbacks[swarm_run.id] = lambda event: None  # placeholder
        # Poll for completion in a background thread, then save the report.
        import threading
        def _poll_completion():
            import time as time_mod
            store_obj = _get_store()
            while True:
                time_mod.sleep(5)
                try:
                    r = store_obj.load_run(swarm_run.id)
                    if r and r.status.value in ("completed", "failed", "cancelled"):
                        if r.status.value == "completed":
                            _on_run_complete(swarm_run.id)
                        else:
                            # Run failed/cancelled → refund (idempotent per run_id).
                            from src.credits.store import CreditStore
                            from src.credits.constants import COST_ALPHA_FORGE
                            CreditStore().refund(billing_user_id, COST_ALPHA_FORGE, swarm_run.id, f"AlphaForge 失败退还 {body.target}")
                        break
                except Exception:
                    break
        threading.Thread(target=_poll_completion, daemon=True).start()

        return AlphaForgeRunResponse(
            run_id=swarm_run.id,
            status=swarm_run.status.value,
            target=body.target,
            market=body.market,
            created_at=swarm_run.created_at,
        )

    # ── Get Run Status ────────────────────────────────────────────
    # ── List Runs ─────────────────────────────────────────────────
    @app.get("/alpha-forge/runs")
    async def list_alpha_forge_runs(request: Request, _=Depends(require_auth)):
        """List all AlphaForge swarm runs (filtered to alpha_forge preset)."""
        store = _get_store()
        all_runs = store.list_runs(limit=100)

        from src.swarm.task_store import TaskStore

        af_runs = []
        for r in all_runs:
            if r.preset_name != "alpha_forge":
                continue
            # Live completed count from per-task files (run.json is stale mid-layer)
            completed_count = 0
            task_count = len(r.tasks)
            try:
                task_store = TaskStore(store.run_dir(r.id))
                live_tasks = task_store.load_all()
                task_count = len(live_tasks)
                completed_count = sum(1 for t in live_tasks if t.status.value == "completed")
            except Exception:
                completed_count = sum(1 for t in r.tasks if t.status.value == "completed")

            af_runs.append({
                "run_id": r.id,
                "status": r.status.value,
                "target": (r.user_vars or {}).get("target", ""),
                "market": (r.user_vars or {}).get("market", "A-shares"),
                "preset_name": r.preset_name,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "total_input_tokens": getattr(r, "total_input_tokens", 0),
                "total_output_tokens": getattr(r, "total_output_tokens", 0),
                "task_count": task_count,
                "completed_count": completed_count,
            })
        return af_runs

    @app.get("/alpha-forge/runs/{run_id}")
    async def get_alpha_forge_run(run_id: str, request: Request, _=Depends(require_auth)):
        """Get the status of an AlphaForge swarm run.

        Reads live per-task status from the TaskStore (tasks/*.json), NOT the
        run.json snapshot — run.json is only refreshed at layer boundaries, so
        mid-layer tasks would otherwise all read "pending" even while running.
        """
        store = _get_store()
        run = store.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # Live task status from individual task files (real-time), falling back
        # to run.json's snapshot if TaskStore cannot load them.
        live_tasks = []
        try:
            from src.swarm.task_store import TaskStore
            run_dir = store.run_dir(run_id)
            task_store = TaskStore(run_dir)
            live_tasks = task_store.load_all()
        except Exception:
            logger.warning("Failed to load live task status for %s", run_id, exc_info=True)
            live_tasks = []

        tasks_source = live_tasks if live_tasks else run.tasks

        return {
            "run_id": run.id,
            "status": run.status.value,
            "preset_name": run.preset_name,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "final_report": run.final_report,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
            "tasks": [
                {
                    "id": t.id,
                    "agent_id": t.agent_id,
                    "status": t.status.value,
                    "blocked_by": list(getattr(t, "blocked_by", []) or []),
                    "error": getattr(t, "error", None),
                    **_task_display_status(t),
                }
                for t in tasks_source
            ],
        }

    # ── Force Cancel Run (disk-level, no runtime memory dependency) ──
    @app.post("/alpha-forge/runs/{run_id}/cancel")
    async def cancel_alpha_forge_run(run_id: str, request: Request, _=Depends(require_auth)):
        """Force-cancel an AlphaForge run by marking it cancelled on disk.

        Unlike ``/swarm/runs/{id}/cancel`` (which needs the run to be active
        in the current runtime's memory), this marks the run + every task as
        cancelled directly in the task files and run.json. Survives server
        restarts and handles already-dead runs. The in-flight worker threads
        (if any are still alive in the old process) will wind down on their
        own next iteration; their writes to already-cancelled task files are
        harmless no-ops.
        """
        store = _get_store()
        run = store.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        # 1. Try the graceful in-memory cancel first (works if run is active).
        cancelled_in_memory = False
        if get_swarm_runtime is not None:
            try:
                cancelled_in_memory = get_swarm_runtime().cancel_run(run_id)
            except Exception:
                cancelled_in_memory = False

        # 2. Force disk-level cancellation regardless.
        from datetime import datetime, timezone
        from src.swarm.models import RunStatus, TaskStatus
        from src.swarm.task_store import TaskStore

        run_dir = store.run_dir(run_id)
        try:
            task_store = TaskStore(run_dir)
            for t in task_store.load_all():
                if t.status not in (TaskStatus.completed, TaskStatus.failed, TaskStatus.cancelled):
                    task_store.update_status(t.id, TaskStatus.cancelled)
        except Exception:
            logger.warning("Failed to cancel task files for %s", run_id, exc_info=True)

        run.status = RunStatus.cancelled
        run.completed_at = datetime.now(timezone.utc).isoformat()
        try:
            store.update_run(run)
        except Exception:
            logger.warning("Failed to write cancelled run.json for %s", run_id, exc_info=True)

        return {
            "status": "cancelled",
            "run_id": run_id,
            "in_memory_cancel": cancelled_in_memory,
            "disk_cancel": True,
        }

    # ── SSE Events Stream ─────────────────────────────────────────
    @app.get("/alpha-forge/runs/{run_id}/events")
    async def stream_alpha_forge_events(
        run_id: str,
        request: Request,
        _=Depends(require_event_stream_auth),
    ):
        """SSE stream for live AlphaForge run progress."""
        store = _get_store()

        # Verify run exists
        run = store.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

        async def event_generator():
            events_file = store.run_dir(run_id) / "events.jsonl"
            last_pos = 0

            # Replay existing events
            if events_file.exists():
                try:
                    existing = events_file.read_text(encoding="utf-8")
                    yield f"data: {json.dumps({'type': 'replay_start', 'count': len(existing.splitlines())})}\n\n"
                    for line in existing.splitlines():
                        if line.strip():
                            yield f"data: {line.strip()}\n\n"
                    last_pos = events_file.stat().st_size
                except Exception:
                    pass

            # Watch for new events
            import time as time_mod
            while True:
                if await request.is_disconnected():
                    break
                try:
                    if events_file.exists():
                        current_size = events_file.stat().st_size
                        if current_size > last_pos:
                            with open(events_file, "r", encoding="utf-8") as f:
                                f.seek(last_pos)
                                new_data = f.read()
                                for line in new_data.splitlines():
                                    if line.strip():
                                        yield f"data: {line.strip()}\n\n"
                            last_pos = current_size
                except Exception:
                    pass

                # Check if run is done
                try:
                    current = store.load_run(run_id)
                    if current and current.status.value in ("completed", "failed", "cancelled"):
                        yield f"data: {json.dumps({'type': 'run_done', 'status': current.status.value})}\n\n"
                        break
                except Exception:
                    pass

                await asyncio.sleep(1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    logger.info("AlphaForge routes registered")
