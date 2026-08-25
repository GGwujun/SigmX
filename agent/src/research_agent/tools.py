"""Explicit research tool allowlist.

This module intentionally does not import the application's global tool registry.
That makes trading/account capabilities impossible to inherit accidentally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ResearchTool:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[[dict[str, Any]], dict[str, Any]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


def build_research_tools(*, data_search: Callable[[str], dict], skill_loader: Callable[[str], dict]) -> list[ResearchTool]:
    return [
        ResearchTool(
            name="search_market_data",
            description="通过 Data Hub 优先的数据路由检索市场、财务和情报证据。",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            execute=lambda args: data_search(str(args["query"])),
        ),
        ResearchTool(
            name="load_research_skill",
            description="加载一个投研 Skill 的方法、数据要求与风险说明。",
            parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            execute=lambda args: skill_loader(str(args["name"])),
        ),
    ]
