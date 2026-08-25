from __future__ import annotations

from src.product.research_plans import ResearchPlanService


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
