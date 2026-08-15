"""Stable product-facing Financial Harness models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GovernanceLevel(StrEnum):
    READ = "read"
    PROPOSE = "propose"
    SIMULATE = "simulate"
    APPROVE = "approve"
    EXECUTE = "execute"


class DataLocality(StrEnum):
    LOCAL = "local"
    DATA_HUB = "data_hub"
    NETWORK = "network"
    MIXED = "mixed"


class ToolCategory(StrEnum):
    DATA = "data"
    RESEARCH = "research"
    QUANT = "quant"
    CONTEXT = "context"
    GOVERNANCE = "governance"
    SYSTEM = "system"


class CostDimension(StrEnum):
    RESEARCH_CREDIT = "research_credit"
    DATA_CREDIT = "data_credit"
    LOCAL_COMPUTE = "local_compute"
    NONE = "none"


@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    name: str
    category: ToolCategory
    input_schema: dict[str, Any]
    output_kind: str
    data_locality: DataLocality
    governance_level: GovernanceLevel
    requires_confirmation: bool
    cost_dimensions: tuple[CostDimension, ...]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("tool id is required")
        if self.governance_level == GovernanceLevel.EXECUTE:
            raise ValueError("execute tools are not supported by the current research Harness")
        if not self.cost_dimensions:
            raise ValueError("at least one cost dimension is required")
