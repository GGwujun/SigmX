"""AlphaForge 报告输出验证和填充管线。

从 report_writer 的输出中提取结构化 JSON，验证必填字段，
缺失字段填充安全默认值。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DASHBOARD_RE = re.compile(
    r"<!--\s*ALPHA_FORGE_DASHBOARD:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def extract_dashboard(raw_text: str) -> tuple[dict[str, Any] | None, str]:
    """从报告文本中提取 ALPHA_FORGE_DASHBOARD JSON。

    Returns:
        (parsed_dict_or_None, cleaned_text)
    """
    match = _DASHBOARD_RE.search(raw_text)
    if not match:
        return None, raw_text

    raw = match.group(1)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.warning("output_validator: failed to parse dashboard JSON")
        return None, raw_text

    cleaned = _DASHBOARD_RE.sub("", raw_text).strip()
    return data, cleaned


def validate_and_fill(data: dict[str, Any]) -> dict[str, Any]:
    """验证并填充缺失字段。

    确保返回的 dict 始终包含完整的 schema 结构。
    """
    result = dict(data)

    # 顶层字段
    result.setdefault("symbol", "")
    if result.get("decision") not in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
        result["decision"] = "hold"
    conf = result.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        result["confidence"] = 0.5

    # dashboard
    dashboard = result.setdefault("dashboard", {})

    # core_conclusion
    cc = dashboard.setdefault("core_conclusion", {})
    cc.setdefault("one_sentence", "（分析完成，详情请查看完整报告）")
    if cc.get("signal_type") not in ("🟢买入信号", "🟡持有观望", "🔴卖出信号", "⚠️风险警告"):
        decision = result.get("decision", "hold")
        cc["signal_type"] = {"strong_buy": "🟢买入信号", "buy": "🟢买入信号",
                             "hold": "🟡持有观望",
                             "sell": "🔴卖出信号", "strong_sell": "🔴卖出信号"}.get(decision, "🟡持有观望")
    cc.setdefault("bull_bear_summary", "")

    # technical
    tech = dashboard.setdefault("technical", {})
    tech.setdefault("trend", "")
    tech.setdefault("support", 0)
    tech.setdefault("resistance", 0)
    tech.setdefault("ma_alignment", "")
    tech.setdefault("trend_score", 50)

    # fundamental
    fund = dashboard.setdefault("fundamental", {})
    fund.setdefault("valuation", "")
    fund.setdefault("growth", "")
    fund.setdefault("quality_score", 50)

    # capital_flow
    cf = dashboard.setdefault("capital_flow", {})
    cf.setdefault("main_net", 0)
    cf.setdefault("northbound", "")
    cf.setdefault("sentiment", "")

    # battle_plan
    bp = dashboard.setdefault("battle_plan", {})
    bp.setdefault("entry_price", 0)
    bp.setdefault("stop_loss", 0)
    bp.setdefault("target_1", 0)
    bp.setdefault("target_2", 0)
    bp.setdefault("risk_reward", 0)

    # arrays
    dashboard.setdefault("risk_factors", [])
    dashboard.setdefault("catalysts", [])

    return result


def stabilize_decision(data: dict[str, Any], current_price: float = 0,
                       capital_flow_bias: float = 0) -> dict[str, Any]:
    """根据真实行情数据校准 LLM 决策。

    防止看多但资金大幅流出、或看空但价格在支撑位等矛盾情况。
    """
    result = dict(data)
    decision = result.get("decision", "hold")
    dashboard = result.get("dashboard", {})

    # 看多但资金大幅流出 → 降级为持有
    if decision in ("strong_buy", "buy") and capital_flow_bias < -0.5:
        bp = dashboard.get("battle_plan", {})
        entry = bp.get("entry_price", 0)
        if current_price > 0 and entry > 0 and current_price > entry * 1.05:
            result["decision"] = "hold"
            cc = dashboard.get("core_conclusion", {})
            cc["one_sentence"] = cc.get("one_sentence", "") + "（资金面不支持激进做多，降级为观望）"

    # 看空但在支撑位附近 → 降级为持有
    if decision in ("strong_sell", "sell"):
        tech = dashboard.get("technical", {})
        support = tech.get("support", 0)
        if support > 0 and current_price > 0:
            distance = (current_price - support) / current_price
            if distance < 0.03:  # 3% 内
                result["decision"] = "hold"
                cc = dashboard.get("core_conclusion", {})
                cc["one_sentence"] = cc.get("one_sentence", "") + "（接近支撑位，不建议追空）"

    return result
