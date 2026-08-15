"""Adapter from the existing agent ToolRegistry to Harness descriptors."""

from __future__ import annotations

from src.agent.tools import BaseTool, ToolRegistry
from src.harness.models import (
    CostDimension,
    DataLocality,
    GovernanceLevel,
    ToolCategory,
    ToolDescriptor,
)


class HarnessToolRegistry:
    def __init__(self, descriptors: list[ToolDescriptor]) -> None:
        self._descriptors = tuple(sorted(descriptors, key=lambda item: item.id))

    @classmethod
    def from_tool_registry(cls, source: ToolRegistry) -> "HarnessToolRegistry":
        return cls([cls.describe(source.get(name)) for name in source.tool_names if source.get(name) is not None])

    @staticmethod
    def describe(tool: BaseTool) -> ToolDescriptor:
        name = tool.name.lower()
        governance = HarnessToolRegistry._governance(tool, name)
        locality = HarnessToolRegistry._locality(name)
        return ToolDescriptor(
            id=tool.name,
            name=tool.description.strip() or tool.name,
            category=HarnessToolRegistry._category(name),
            input_schema=dict(tool.parameters or {"type": "object", "properties": {}}),
            output_kind="json",
            data_locality=locality,
            governance_level=governance,
            requires_confirmation=not tool.is_readonly,
            cost_dimensions=HarnessToolRegistry._costs(name, locality, governance),
        )

    def list(self) -> list[ToolDescriptor]:
        return list(self._descriptors)

    @staticmethod
    def _governance(tool: BaseTool, name: str) -> GovernanceLevel:
        if "propose" in name or "proposal" in name:
            return GovernanceLevel.PROPOSE
        if any(token in name for token in ("backtest", "shadow", "simulate", "pricing")):
            return GovernanceLevel.SIMULATE
        return GovernanceLevel.READ if tool.is_readonly else GovernanceLevel.PROPOSE

    @staticmethod
    def _category(name: str) -> ToolCategory:
        if any(token in name for token in ("mandate", "goal", "halt", "approval")):
            return ToolCategory.GOVERNANCE
        if any(token in name for token in ("backtest", "factor", "alpha", "shadow", "pricing")):
            return ToolCategory.QUANT
        if any(token in name for token in ("remember", "session", "file", "document")):
            return ToolCategory.CONTEXT
        if any(token in name for token in ("market", "quote", "news", "search", "data", "fund")):
            return ToolCategory.DATA
        if any(token in name for token in ("bash", "edit", "write", "compact")):
            return ToolCategory.SYSTEM
        return ToolCategory.RESEARCH

    @staticmethod
    def _locality(name: str) -> DataLocality:
        if "datahub" in name:
            return DataLocality.DATA_HUB
        if any(token in name for token in ("web", "news", "mcp", "connector")):
            return DataLocality.NETWORK
        if any(token in name for token in ("market", "quote", "fund")):
            return DataLocality.MIXED
        return DataLocality.LOCAL

    @staticmethod
    def _costs(name: str, locality: DataLocality, governance: GovernanceLevel) -> tuple[CostDimension, ...]:
        if locality == DataLocality.DATA_HUB:
            return (CostDimension.DATA_CREDIT,)
        if "swarm" in name or "agent" in name:
            return (CostDimension.RESEARCH_CREDIT,)
        if governance == GovernanceLevel.SIMULATE:
            return (CostDimension.LOCAL_COMPUTE,)
        return (CostDimension.NONE,)
