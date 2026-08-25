"""Explainable capability preflight for Web research questions."""

from __future__ import annotations

import re
import json
import uuid
from dataclasses import dataclass
from typing import Any


ConditionStatus = str


@dataclass(frozen=True)
class MetricCapability:
    metric: str
    label: str
    aliases: tuple[str, ...]
    operators: tuple[str, ...]
    dataset: str


@dataclass(frozen=True)
class ResearchConditionAlternative:
    label: str
    question: str


@dataclass(frozen=True)
class ResearchCondition:
    id: str
    metric: str
    label: str
    operator: str | None
    value: float | str | None
    period: str | None
    benchmark: str | None
    status: ConditionStatus
    reason: str | None
    alternatives: tuple[ResearchConditionAlternative, ...] = ()


@dataclass(frozen=True)
class ResearchDataset:
    key: str
    name: str
    status: ConditionStatus
    as_of: str | None = None
    coverage: str | None = None


@dataclass(frozen=True)
class ResearchPlanStep:
    key: str
    label: str
    status: str = "pending"


@dataclass(frozen=True)
class ResearchPlan:
    id: str
    question: str
    template_id: str | None
    scope: dict[str, Any]
    conditions: tuple[ResearchCondition, ...]
    ranking: tuple[dict[str, Any], ...]
    datasets: tuple[ResearchDataset, ...]
    steps: tuple[ResearchPlanStep, ...]
    executable: bool
    suggested_question: str | None
    execution_mode: str = "rules_fallback"
    model: str | None = None
    skills: tuple[str, ...] = ()

    def to_constraints(self, use_alternatives: bool = False) -> list[dict[str, Any]]:
        del use_alternatives  # Alternatives are converted into a new plan, never trusted in-place.
        return [
            {"field": item.metric, "op": item.operator, "value": item.value}
            for item in self.conditions
            if item.status == "supported"
            and item.operator in {">", ">=", "<", "<=", "=", "=="}
            and isinstance(item.value, (int, float))
        ]


METRICS: dict[str, MetricCapability] = {
    "pe_ttm": MetricCapability("pe_ttm", "市盈率（TTM）", ("市盈率", "PE", "低估值"), ("<=", ">=", "<", ">"), "估值快照"),
    "dividend_yield": MetricCapability("dividend_yield", "股息率（TTM）", ("股息率", "高股息"), ("<=", ">=", "<", ">"), "分红与估值快照"),
    "total_market_value": MetricCapability("total_market_value", "总市值", ("总市值", "小市值"), ("<=", ">=", "<", ">", "sort"), "行情快照"),
}

EXECUTABLE_FIELDS = frozenset(METRICS)

_STEPS = (
    ResearchPlanStep("interpret", "解析问题与指标口径"),
    ResearchPlanStep("scan", "扫描市场与基本面数据"),
    ResearchPlanStep("calculate", "计算筛选指标与排序"),
    ResearchPlanStep("verify", "核验证据与数据完整性"),
    ResearchPlanStep("persist", "保存研究结果快照"),
)


class ResearchPlanService:
    def create(self, question: str, template_id: str | None, scope: dict[str, Any]) -> ResearchPlan:
        normalized = " ".join(question.strip().split())
        if not normalized:
            raise ValueError("研究问题不能为空")

        conditions = self._supported_conditions(normalized, template_id)
        conditions.extend(self._unavailable_conditions(normalized))
        if not conditions:
            conditions.append(self._condition(
                "unresolved_research_goal",
                "当前无法将该目标转换成可验证的数据条件",
                status="unavailable",
                reason="请使用具体财务指标、估值指标或分红条件描述研究目标。",
            ))

        executable = all(item.status != "unavailable" for item in conditions)
        suggested_question = None if executable else self._suggested_question(conditions)
        dataset_names = {METRICS[item.metric].dataset for item in conditions if item.metric in METRICS}
        datasets = tuple(
            ResearchDataset(key=self._dataset_key(name), name=name, status="supported")
            for name in sorted(dataset_names)
        )
        ranking = tuple(
            {"field": item.metric, "direction": str(item.value)}
            for item in conditions
            if item.operator == "sort" and item.status == "supported"
        )
        return ResearchPlan(
            id=uuid.uuid4().hex,
            question=normalized,
            template_id=template_id,
            scope={"market": "A股", "exclude_st": True, **scope},
            conditions=tuple(conditions),
            ranking=ranking,
            datasets=datasets,
            steps=_STEPS,
            executable=executable,
            suggested_question=suggested_question,
        )

    def _supported_conditions(self, question: str, template_id: str | None) -> list[ResearchCondition]:
        conditions: list[ResearchCondition] = []
        pe = self._threshold(question, r"(?:市盈率|PE)(?:（?TTM）?)?[^\d]{0,8}?(不高于|不低于|低于|小于|高于|大于)?\s*(\d+(?:\.\d+)?)")
        dividend = self._threshold(question, r"股息率(?:（?TTM）?)?[^\d]{0,8}?(不高于|不低于|低于|小于|高于|大于)?\s*(\d+(?:\.\d+)?)\s*%?")

        if pe:
            op, value = pe
            conditions.append(self._condition("pe_ttm", f"市盈率（TTM）{self._operator_label(op)} {value:g} 倍", op, value))
        elif "低估值" in question or template_id in {"dividend", "small_value"}:
            conditions.append(self._condition("pe_ttm", "市盈率（TTM）不高于 20 倍", "<=", 20.0))

        if dividend:
            op, value = dividend
            conditions.append(self._condition("dividend_yield", f"股息率（TTM）{self._operator_label(op)} {value:g}%", op, value))
        elif "高股息" in question or template_id in {"dividend", "small_dividend"}:
            conditions.append(self._condition("dividend_yield", "股息率（TTM）不低于 3%", ">=", 3.0))

        if "小市值" in question or template_id in {"small_value", "small_dividend"}:
            conditions.append(self._condition("total_market_value", "按总市值从小到大排序", "sort", "asc"))
        return conditions

    def _unavailable_conditions(self, question: str) -> list[ResearchCondition]:
        conditions: list[ResearchCondition] = []
        if any(marker in question for marker in ("经营现金流", "现金流持续改善")):
            conditions.append(self._condition(
                "operating_cashflow_trend",
                "经营现金流持续改善",
                period="多期财报",
                status="unavailable",
                reason="多期经营现金流序列尚未接入 Web 研究执行器。",
                alternative="改用低估值与高股息筛选",
            ))
        if "盈利质量" in question or ("现金流" in question and "行业中位数" in question):
            conditions.append(self._condition(
                "cashflow_profit_ratio_industry",
                "盈利质量高于行业中位数",
                benchmark="申万行业中位数",
                status="unavailable",
                reason="现金流利润比与行业基准计算尚未接入。",
                alternative="改用低估值与高股息筛选",
            ))
        if ("估值" in question and any(marker in question for marker in ("近五年", "历史分位", "较低分位"))):
            conditions.append(self._condition(
                "pe_historical_percentile",
                "估值处于近五年较低分位",
                period="近五年",
                benchmark="自身历史",
                status="unavailable",
                reason="历史估值序列与分位计算尚未接入。",
                alternative="改用市盈率不高于 20 倍",
            ))
        if any(marker in question.upper() for marker in ("ROE", "净资产收益率", "营收增长", "利润增长", "毛利率")):
            conditions.append(self._condition(
                "financial_growth_quality",
                "多期成长与盈利质量",
                period="多期财报",
                status="unavailable",
                reason="多期成长与盈利质量指标尚未接入。",
                alternative="改用低估值与高股息筛选",
            ))
        return conditions

    @staticmethod
    def _threshold(question: str, pattern: str) -> tuple[str, float] | None:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if not match:
            return None
        word, raw = match.groups()
        operator = {"不高于": "<=", "低于": "<", "小于": "<", "不低于": ">=", "高于": ">", "大于": ">"}.get(word or "", "<=")
        return operator, float(raw)

    @staticmethod
    def _condition(
        metric: str,
        label: str,
        operator: str | None = None,
        value: float | str | None = None,
        *,
        period: str | None = None,
        benchmark: str | None = None,
        status: ConditionStatus = "supported",
        reason: str | None = None,
        alternative: str | None = None,
    ) -> ResearchCondition:
        alternatives = () if alternative is None else (ResearchConditionAlternative(alternative, "寻找低估值且高股息的A股公司"),)
        return ResearchCondition(uuid.uuid4().hex, metric, label, operator, value, period, benchmark, status, reason, alternatives)

    @staticmethod
    def _suggested_question(conditions: list[ResearchCondition]) -> str | None:
        if any(item.alternatives for item in conditions):
            return "寻找低估值且高股息的A股公司"
        return None

    @staticmethod
    def _dataset_key(name: str) -> str:
        return {"估值快照": "valuation", "分红与估值快照": "dividend", "行情快照": "market"}[name]

    @staticmethod
    def _operator_label(operator: str) -> str:
        return {"<=": "不高于", "<": "低于", ">=": "不低于", ">": "高于"}[operator]


AI_RESEARCH_METRICS = frozenset({
    *METRICS.keys(),
    "operating_cashflow_trend",
    "cashflow_profit_ratio_industry",
    "pe_historical_percentile",
    "roe_trend",
    "revenue_growth",
    "profit_growth",
    "gross_margin_stability",
    "debt_ratio",
    "rd_intensity",
    "institutional_holding",
    "news_sentiment",
    "announcement_event",
})


class AIResearchPlanService:
    """Use an LLM for semantic planning, then validate every executable field."""

    def __init__(self, llm_factory, *, timeout_seconds: int = 90) -> None:
        self.llm_factory = llm_factory
        self.timeout_seconds = timeout_seconds

    def create(self, question: str, template_id: str | None, scope: dict[str, Any]) -> ResearchPlan:
        normalized = " ".join(question.strip().split())
        if not normalized:
            raise ValueError("研究问题不能为空")
        llm = self.llm_factory()
        response = llm.chat([
            {"role": "system", "content": self._prompt()},
            {"role": "user", "content": json.dumps({"question": normalized, "template_id": template_id, "scope": scope}, ensure_ascii=False)},
        ], timeout=self.timeout_seconds)
        payload = self._parse(response.content or "")
        conditions = tuple(self._condition(item) for item in payload.get("conditions", []))
        if not conditions:
            raise ValueError("AI research plan contains no conditions")
        datasets = tuple(
            ResearchDataset(str(item.get("key") or "dataset"), str(item.get("name") or "研究数据"), "supported")
            for item in payload.get("datasets", []) if isinstance(item, dict)
        )
        return ResearchPlan(
            id=uuid.uuid4().hex,
            question=normalized,
            template_id=template_id,
            scope={"market": "A股", "exclude_st": True, **scope, **(payload.get("scope") or {})},
            conditions=conditions,
            ranking=tuple(item for item in payload.get("ranking", []) if isinstance(item, dict)),
            datasets=datasets,
            steps=_STEPS,
            executable=all(item.status == "supported" for item in conditions),
            suggested_question=None,
            execution_mode="agent",
            model=getattr(llm, "model_name", None),
            skills=tuple(str(item) for item in payload.get("skills", []) if item),
        )

    @staticmethod
    def _parse(content: str) -> dict[str, Any]:
        value = content.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("AI research plan is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("AI research plan must be an object")
        return payload

    @staticmethod
    def _condition(item: dict[str, Any]) -> ResearchCondition:
        metric = str(item.get("metric") or "")
        if metric not in AI_RESEARCH_METRICS:
            raise ValueError(f"unsupported AI research metric: {metric}")
        return ResearchCondition(
            id=uuid.uuid4().hex,
            metric=metric,
            label=str(item.get("label") or metric),
            operator=str(item["operator"]) if item.get("operator") is not None else None,
            value=item.get("value"),
            period=str(item["period"]) if item.get("period") is not None else None,
            benchmark=str(item["benchmark"]) if item.get("benchmark") is not None else None,
            status="supported",
            reason=None,
        )

    @staticmethod
    def _prompt() -> str:
        metrics = ", ".join(sorted(AI_RESEARCH_METRICS))
        return (
            "你是 SigmX 投研规划器。把问题转换为严格 JSON，不输出解释。"
            f"metric 只能从以下列表选择：{metrics}。"
            "结构为 scope、conditions、ranking、datasets、skills。"
            "conditions 每项包含 metric,label,operator,value,period,benchmark。"
            "不要承诺交易、账户、持仓或影子账户能力。"
        )
