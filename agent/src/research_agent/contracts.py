from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ResearchEvidence:
    id: str
    run_id: str
    source: str
    field: str
    value: Any
    as_of: str | None = None
    url: str | None = None


@dataclass
class ResearchRuntimeState:
    run_id: str
    max_iterations: int = 50
    iterations: int = 0
    phase: str = "queued"
    granted_tools: list[str] = field(default_factory=list)
    called_tools: list[str] = field(default_factory=list)
    loaded_skills: list[str] = field(default_factory=list)
    used_skills: list[str] = field(default_factory=list)
    agents: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ResearchOutputV2:
    run_id: str
    mode: Literal["ai", "rules_degraded"]
    summary: str
    conclusions: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[ResearchEvidence] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    model: str | None = None
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 50
    artifacts: list[dict[str, Any]] = field(default_factory=list)
