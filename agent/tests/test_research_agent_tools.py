from src.research_agent.tools import ResearchTool, build_research_tools


def test_research_tool_allowlist_excludes_every_account_and_trading_capability() -> None:
    tools = build_research_tools(
        data_search=lambda query: {"items": [], "source": "data_hub"},
        skill_loader=lambda name: {"name": name},
    )
    names = {tool.name for tool in tools}
    assert names == {"search_market_data", "load_research_skill"}
    forbidden = ("account", "portfolio", "position", "broker", "order", "trade", "mandate", "shadow", "live")
    assert not any(marker in name for name in names for marker in forbidden)
    assert all(isinstance(tool, ResearchTool) for tool in tools)
