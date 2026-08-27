from __future__ import annotations


FORBIDDEN_RESEARCH_TOOLS = {
    "bash", "background_run", "check_background", "edit_file", "write_file", "read_file",
    "save_skill", "patch_skill", "delete_skill", "skill_file", "remember",
    "trading_connections", "trading_select_connection", "trading_check", "trading_account",
    "trading_positions", "trading_orders", "trading_history", "trading_place_order", "trading_cancel_order",
    "propose_mandate_profiles", "extract_shadow_strategy", "run_shadow_backtest",
    "render_shadow_report", "scan_shadow_signals", "analyze_trade_journal",
}

DEFAULT_RESEARCH_TOOLS = (
    "web_search", "read_url", "read_document", "load_skill", "factor_analysis",
    "options_pricing", "pattern_analysis", "backtest", "compact",
    "start_research_goal", "get_research_goal", "add_goal_evidence", "update_research_goal_status",
)


class ResearchToolPolicy:
    def allowed_names(self, requested: list[str] | None = None) -> list[str]:
        candidates = requested if requested is not None else list(DEFAULT_RESEARCH_TOOLS)
        allowed_set = set(DEFAULT_RESEARCH_TOOLS)
        return [name for name in candidates if name in allowed_set and name not in FORBIDDEN_RESEARCH_TOOLS]


def build_research_registry(requested: list[str] | None = None):
    from src.tools import build_filtered_registry

    names = ResearchToolPolicy().allowed_names(requested)
    return build_filtered_registry(names, include_shell_tools=False)
