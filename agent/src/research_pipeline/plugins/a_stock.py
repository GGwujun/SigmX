# -*- coding: utf-8 -*-
"""A 股个股深研插件 —— Core 之外的行业知识全部在这里。

五阶段（无一致预期数据源，不设 estimates 段）：

1. ``profile``        公司画像：档案 + 90 日行情趋势/波动 + 估值/换手快照新鲜度
2. ``valuation``      估值水平：pe/pb 在 90 日窗口内的历史分位（calc: percentile_rank）
3. ``funds_sentiment`` 资金与情绪：近 20 日资金流 + 今日池归属（zt/zb/dt/yzt）+ 短线主题
4. ``risk``           风险与反证：近 90 日公告 + 反证清单 + 决策要点 + 数据矛盾
5. ``report``         成文：固定章节 + 状态档 + 合规 gate

数据集名是 fetchers.py 的注册表键。critical 三件套（档案/行情/估值快照）拿不到
就不存在可用研究，整个运行 failed；资金流/池归属/公告缺数据是常态，进 gaps。
"""

from __future__ import annotations

import json

from ..plugin import ResearchPlugin, StageDatasets, StageSchema, StageValidationContext

# plan["pipeline"] 的分流键（research_task_routes → runner_adapter 认这个值）
A_STOCK_DEEP_RESEARCH = "a_stock_deep_research"

_STAGE_ORDER = ("profile", "valuation", "funds_sentiment", "risk", "report")

REPORT_SECTIONS = ("公司画像", "估值水平", "资金与情绪", "风险与反证", "结论")

# 产物 schema 扩展（骨架之外的字段；write_stage 与 validator 共用同一份）
_STAGE_SCHEMAS = {
    "profile": StageSchema(
        properties={
            "trend": {"type": "string", "enum": ["up", "down", "range"],
                      "description": "90 日区间趋势：上行/下行/震荡"},
            "volatility_pct": {"type": "number", "description": "年化波动率%（calc volatility）"},
            "max_drawdown_pct": {"type": "number", "description": "90 日最大回撤%（calc max_drawdown）"},
            "data_freshness": {"type": "string", "enum": ["fresh", "stale"],
                               "description": "行情快照新鲜度：fresh=近 3 个交易日内"},
        },
        required=("trend", "volatility_pct", "data_freshness"),
    ),
    "valuation": StageSchema(
        properties={
            "pe_ttm_percentile": {"type": "number",
                                  "description": "市盈率 TTM 在 90 日窗口的历史分位%（calc percentile_rank）"},
            "pb_percentile": {"type": "number",
                              "description": "市净率在 90 日窗口的历史分位%（calc percentile_rank）"},
            "total_mv_note": {"type": "string", "description": "总市值规模描述（纯陈述）"},
        },
        required=("pe_ttm_percentile", "pb_percentile"),
    ),
    "funds_sentiment": StageSchema(
        properties={
            "capital_direction": {"type": "string",
                                  "enum": ["net_inflow", "net_outflow", "flat", "unknown"],
                                  "description": "近 20 日主力资金方向"},
            "pool_membership": {"type": "array", "items": {"type": "string"},
                                "description": "今日池归属：zt/zb/dt/yzt，不在任何池给空数组"},
            "theme_exposure": {"type": "array", "items": {"type": "string"},
                               "description": "短线主题归属清单"},
        },
        required=("capital_direction", "pool_membership"),
    ),
    "risk": StageSchema(
        properties={
            "counter_evidence": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                                 "description": "反证清单：与看多叙事相反的事实（≥1 条）"},
            "decision_points": {"type": "array", "items": {"type": "string"}, "minItems": 3,
                                "description": "后续应跟踪验证的决策要点（≥3 条）"},
            "source_conflicts": {"type": "array", "items": {"type": "string"},
                                 "description": "数据源之间的矛盾陈述，没有给空数组"},
        },
        required=("counter_evidence", "decision_points", "source_conflicts"),
    ),
}


def _profile_validator(ctx: StageValidationContext) -> "list[str]":
    """波动/回撤不可能是负数——schema 表达不了数值下界，插件校验器补。"""
    out: list[str] = []
    for key in ("volatility_pct", "max_drawdown_pct"):
        v = ctx.output.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
            out.append(f"{key} 为负数（{v}），波动率/回撤不可能为负")
    return out


_PROMPT_HEAD = """你是 A 股个股深度研究员。标的：{code}（交易日：{trade_date}）。
可用工具：list_run_files / read_run_file / calculate / write_stage / write_report。
工作方式：先用 read_run_file 读指定数据，需要任何数字结论就用 calculate 算并记
calculation_id，最后用 write_stage 写本阶段产物（schema 见下）。禁止心算。"""


def _sheet(stage: str, goal: str, files: str, calcs: str, schema_hint: str) -> str:
    return (
        f"## 阶段任务：{stage}\n\n目标：{goal}\n\n"
        f"### 读数据\n{files}\n\n### 计算（calculate 工具）\n{calcs}\n\n"
        f"### 产物（write_stage，stage 字段必须为 \"{stage}\"）\n{schema_hint}\n\n"
        "骨架通用字段：stage/summary 必填；结论引用的 evidence_ids 与 calculation_ids "
        "如实列出。summary 是纯事实陈述，不得含买卖建议。"
    )


def _json_block(obj) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


_PROFILE_SHEET = _sheet(
    "profile", "建立公司画像：主营与行业、90 日趋势、波动与回撤、快照新鲜度。",
    "- fetch/security_profile.json（公司档案）\n"
    "- fetch/bars_daily_90d.json（90 日日线）\n"
    "- fetch/daily_basic_90d.json（估值/换手快照）",
    "收盘价序列 → volatility（年化波动率%）、max_drawdown（最大回撤%）；"
    "首尾收盘 → pct_change 得区间涨跌幅。",
    _json_block({"stage": "profile", "summary": "（事实摘要）",
                "trend": "up|down|range", "volatility_pct": 0.0,
                "max_drawdown_pct": 0.0, "data_freshness": "fresh|stale",
                "evidence_ids": [], "calculation_ids": []}),
)

_VALUATION_SHEET = _sheet(
    "valuation", "给估值定位：pe/pb 在近 90 日窗口的历史分位（不是绝对高低，是相对位置）。",
    "- fetch/daily_basic_90d.json（pe_ttm/pb/total_mv 序列）",
    "pe_ttm 最新值 + 90 日序列 → percentile_rank；pb 同理。两个分位各算一条。",
    _json_block({"stage": "valuation", "summary": "（事实摘要）",
                 "pe_ttm_percentile": 0.0, "pb_percentile": 0.0,
                 "total_mv_note": "（市值规模陈述）",
                 "evidence_ids": [], "calculation_ids": []}),
)

_FUNDS_SHEET = _sheet(
    "funds_sentiment", "看清资金与情绪：近 20 日主力资金方向、今日池归属、短线主题暴露。",
    "- fetch/capital_flow_20d.json（资金流，缺数据记 gaps）\n"
    "- fetch/pool_zt_today.json / pool_zb_today.json / pool_dt_today.json / pool_yzt_today.json\n"
    "- fetch/shortline_themes.json（当日主题）",
    "主力净流入合计 → sum（序列）；方向判断写进 capital_direction。",
    _json_block({"stage": "funds_sentiment", "summary": "（事实摘要）",
                 "capital_direction": "net_inflow|net_outflow|flat|unknown",
                 "pool_membership": [], "theme_exposure": [],
                 "evidence_ids": [], "calculation_ids": []}),
)

_RISK_SHEET = _sheet(
    "risk", "找反证：不利公告、异常量价、与主叙事矛盾的数据。没有反证的研究不是研究。",
    "- fetch/announcements_90d.json（近 90 日公告，缺数据记 gaps）\n"
    "- 本运行目录此前阶段的产物（read_run_file stages/*.json）",
    "回撤/放量幅度类数字必须 calculate，禁止心算。",
    _json_block({"stage": "risk", "summary": "（事实摘要）",
                 "counter_evidence": ["（≥1 条反证事实）"],
                 "decision_points": ["（≥3 条后续跟踪要点）"],
                 "source_conflicts": [],
                 "evidence_ids": [], "calculation_ids": []}),
)

_REPORT_SHEET = (
    "## 阶段任务：report\n\n"
    "目标：把前四个阶段的已校验产物整合成一份完整的个股深度研究报告。\n\n"
    "### 读数据\n此前全部阶段产物：read_run_file stages/profile.json、stages/valuation.json、"
    "stages/funds_sentiment.json、stages/risk.json（列表用 list_run_files）。\n\n"
    "### 成文（write_report）\n"
    f"Markdown 报告，必须包含以下章节（# 一级标题）：{'、'.join(REPORT_SECTIONS)}。\n"
    "首行必须是状态档：`状态: incomplete`（有 gaps/阶段 partial）或 `状态: complete`（全部完成），"
    "编排器会按事实复核归一。\n\n"
    "⛔ 铁律：\n"
    "- 每个数字要么标注证据 id（ev-…），要么标注 calculation_id（calc-…），要么写进 gaps——三选一\n"
    "- 不得给出任何买卖建议、目标价、止损位；建议类表述一律改写为事实陈述\n"
    "- write_report 需同时给 stage_output（stage=\"report\" + summary）"
)


def _build_prompt(stage: str, cfg: dict) -> str:
    head = _PROMPT_HEAD.format(code=cfg.get("code"), trade_date=cfg.get("trade_date") or "最新")
    sheets = {
        "profile": _PROFILE_SHEET,
        "valuation": _VALUATION_SHEET,
        "funds_sentiment": _FUNDS_SHEET,
        "risk": _RISK_SHEET,
        "report": _REPORT_SHEET,
    }
    return f"{head}\n\n{sheets[stage]}"


a_stock_plugin = ResearchPlugin(
    id="a_stock",
    stages=_STAGE_ORDER,
    report_stage="report",
    stage_datasets={
        "profile": StageDatasets(
            required=("security_profile", "bars_daily_90d", "daily_basic_90d")),
        "valuation": StageDatasets(),   # 复用 profile 已取的 daily_basic_90d（账本去重）
        "funds_sentiment": StageDatasets(
            optional=("capital_flow_20d", "pool_zt_today", "pool_zb_today",
                      "pool_dt_today", "pool_yzt_today", "shortline_themes")),
        "risk": StageDatasets(optional=("announcements_90d",)),
        "report": StageDatasets(),
    },
    critical_datasets=("security_profile", "bars_daily_90d", "daily_basic_90d"),
    stage_schemas=_STAGE_SCHEMAS,
    stage_validators={"profile": _profile_validator},
    report_sections=REPORT_SECTIONS,
    build_stage_prompt=_build_prompt,
)
