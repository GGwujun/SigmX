from __future__ import annotations

import pytest

from src.product.research_plans import AIResearchPlanService, ResearchPlanService
from src.providers.chat import LLMResponse


def test_plan_parses_low_valuation_and_high_dividend() -> None:
    plan = ResearchPlanService().create(
        "寻找市盈率不高于20且股息率不低于3%的A股",
        None,
        {"market": "A股", "exclude_st": True},
    )

    assert plan.executable is True
    assert [
        (item.metric, item.operator, item.value, item.status)
        for item in plan.conditions
    ] == [
        ("pe_ttm", "<=", 20.0, "supported"),
        ("dividend_yield", ">=", 3.0, "supported"),
    ]
    assert plan.to_constraints() == [
        {"field": "pe_ttm", "op": "<=", "value": 20.0},
        {"field": "dividend_yield", "op": ">=", "value": 3.0},
    ]


def test_plan_uses_executable_defaults_for_product_language() -> None:
    plan = ResearchPlanService().create(
        "寻找低估值、高股息、小市值的A股公司",
        None,
        {"market": "A股"},
    )

    assert [(item.metric, item.operator, item.value) for item in plan.conditions] == [
        ("pe_ttm", "<=", 20.0),
        ("dividend_yield", ">=", 3.0),
        ("total_market_value", "sort", "asc"),
    ]
    assert plan.executable is True


def test_plan_does_not_downgrade_cashflow_quality_to_name_search() -> None:
    plan = ResearchPlanService().create(
        "寻找经营现金流持续改善、盈利质量高于行业中位数，并且估值处于近五年较低分位的A股公司",
        None,
        {"market": "A股"},
    )

    statuses = {item.metric: item.status for item in plan.conditions}
    assert statuses == {
        "operating_cashflow_trend": "unavailable",
        "cashflow_profit_ratio_industry": "unavailable",
        "pe_historical_percentile": "unavailable",
    }
    assert plan.executable is False
    assert plan.suggested_question is not None
    assert "低估值" in plan.suggested_question
    assert plan.to_constraints() == []


def test_plan_marks_unknown_question_unavailable_instead_of_fabricating_filter() -> None:
    plan = ResearchPlanService().create(
        "寻找管理层执行力强并具备品牌护城河的公司",
        None,
        {"market": "A股"},
    )

    assert plan.executable is False
    assert len(plan.conditions) == 1
    assert plan.conditions[0].metric == "unresolved_research_goal"
    assert plan.conditions[0].status == "unavailable"
    assert plan.suggested_question is None


def test_plan_template_defaults_are_full_executable_conditions() -> None:
    plan = ResearchPlanService().create(
        "低估值 高股息",
        "dividend",
        {"market": "A股", "exclude_st": True},
    )

    assert plan.executable is True
    assert [item.label for item in plan.conditions] == [
        "市盈率（TTM）不高于 20 倍",
        "股息率（TTM）不低于 3%",
    ]
    assert {dataset.name for dataset in plan.datasets} == {"估值快照", "分红与估值快照"}


def test_ai_plan_service_calls_model_and_returns_validated_research_plan() -> None:
    class FakeLLM:
        model_name = "test-planner"

        def chat(self, messages, tools=None, timeout=None):
            assert "经营现金流" in messages[-1]["content"]
            return LLMResponse(content='''{
              "scope":{"market":"A股","exclude_st":true},
              "conditions":[
                {"metric":"operating_cashflow_trend","label":"经营现金流连续三期改善","operator":"trend_up","value":3,"period":"三期财报","benchmark":null},
                {"metric":"cashflow_profit_ratio_industry","label":"现金流利润比高于行业中位数","operator":"above_industry_median","value":null,"period":"最新财报","benchmark":"申万行业中位数"}
              ],
              "ranking":[{"field":"cashflow_profit_ratio_industry","direction":"desc"}],
              "datasets":[{"key":"cashflow","name":"现金流量表"},{"key":"industry","name":"行业分类与财务指标"}],
              "skills":["financial-statement","fundamental-filter"]
            }''')

    plan = AIResearchPlanService(lambda: FakeLLM()).create(
        "寻找经营现金流持续改善、盈利质量高于行业中位数的 A 股公司", None, {}
    )

    assert plan.execution_mode == "agent"
    assert plan.model == "test-planner"
    assert plan.executable is True
    assert [item.metric for item in plan.conditions] == [
        "operating_cashflow_trend", "cashflow_profit_ratio_industry"
    ]
    assert plan.skills == ("financial-statement", "fundamental-filter")


def test_ai_plan_rejects_model_invented_metric() -> None:
    class FakeLLM:
        def chat(self, messages, tools=None, timeout=None):
            return LLMResponse(content='{"conditions":[{"metric":"future_stock_price","label":"预测股价","operator":">","value":100}],"datasets":[]}')

    with pytest.raises(ValueError, match="unsupported AI research metric"):
        AIResearchPlanService(lambda: FakeLLM()).create("预测明天股价", None, {})
