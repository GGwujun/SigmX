from src.research_agent.policy import FORBIDDEN_RESEARCH_TOOLS, ResearchToolPolicy


def test_policy_never_allows_trading_shadow_shell_or_skill_writes() -> None:
    requested = ["web_search", "load_skill", "bash", "trading_place_order", "shadow_scan", "save_skill", "read_file"]
    allowed = ResearchToolPolicy().allowed_names(requested)
    assert allowed == ["web_search", "load_skill"]
    assert FORBIDDEN_RESEARCH_TOOLS.isdisjoint(allowed)


def test_policy_has_explicit_research_capabilities() -> None:
    allowed = ResearchToolPolicy().allowed_names()
    assert "web_search" in allowed
    assert "load_skill" in allowed
    assert "factor_analysis" in allowed
