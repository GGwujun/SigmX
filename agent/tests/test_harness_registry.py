from __future__ import annotations

import pytest

from src.agent.tools import BaseTool, ToolRegistry
from src.harness.models import CostDimension, DataLocality, GovernanceLevel, ToolCategory, ToolDescriptor
from src.harness.registry import HarnessToolRegistry


class FakeTool(BaseTool):
    name = "market_snapshot"
    description = "Read a market snapshot"
    parameters = {"type": "object", "properties": {"code": {"type": "string"}}}
    is_readonly = True

    def execute(self, **kwargs):
        return "{}"


class BacktestTool(FakeTool):
    name = "run_shadow_backtest"
    description = "Simulate a strategy"
    is_readonly = False


class ProposalTool(FakeTool):
    name = "propose_mandate_profiles"
    description = "Propose bounded mandates"
    is_readonly = False


def test_descriptor_rejects_execute_in_current_harness() -> None:
    with pytest.raises(ValueError, match="execute"):
        ToolDescriptor(
            id="order", name="Order", category=ToolCategory.GOVERNANCE,
            input_schema={}, output_kind="json", data_locality=DataLocality.NETWORK,
            governance_level=GovernanceLevel.EXECUTE, requires_confirmation=True,
            cost_dimensions=(CostDimension.NONE,),
        )


def test_existing_tools_map_to_stable_harness_contract() -> None:
    source = ToolRegistry()
    source.register(FakeTool())
    source.register(BacktestTool())
    source.register(ProposalTool())
    descriptors = {item.id: item for item in HarnessToolRegistry.from_tool_registry(source).list()}

    assert descriptors["market_snapshot"].governance_level == GovernanceLevel.READ
    assert descriptors["market_snapshot"].category == ToolCategory.DATA
    assert descriptors["run_shadow_backtest"].governance_level == GovernanceLevel.SIMULATE
    assert descriptors["run_shadow_backtest"].cost_dimensions == (CostDimension.LOCAL_COMPUTE,)
    assert descriptors["propose_mandate_profiles"].governance_level == GovernanceLevel.PROPOSE
    assert all(item.governance_level != GovernanceLevel.EXECUTE for item in descriptors.values())


def test_non_readonly_local_mutation_requires_confirmation() -> None:
    descriptor = HarnessToolRegistry.describe(BacktestTool())
    assert descriptor.requires_confirmation is True
