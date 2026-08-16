"""Strict evidence audit for the SigmX product architecture requirements."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EvidenceStatus(StrEnum):
    COMPLETE = "complete"
    INDIRECT = "indirect"
    MISSING = "missing"


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    requirement: Requirement
    status: EvidenceStatus
    reason: str


def load_requirements(path: Path) -> list[Requirement]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    requirements: list[Requirement] = []
    seen: set[str] = set()
    for item in raw:
        requirement_id = str(item["id"])
        if requirement_id in seen:
            raise ValueError(f"duplicate requirement id: {requirement_id}")
        seen.add(requirement_id)
        requirements.append(
            Requirement(
                id=requirement_id,
                title=str(item["title"]),
                evidence=tuple(str(value) for value in item.get("evidence", [])),
            )
        )
    return requirements


def audit_requirement(requirement: Requirement, root: Path) -> AuditResult:
    if not requirement.evidence:
        return AuditResult(requirement, EvidenceStatus.MISSING, "no evidence declared")

    existing: set[str] = set()
    for value in requirement.evidence:
        kind, separator, relative_path = value.partition(":")
        if separator and (root / relative_path).is_file():
            existing.add(kind)

    if "test" in existing and "runtime" in existing:
        return AuditResult(requirement, EvidenceStatus.COMPLETE, "test and runtime evidence exist")
    if existing == {"file"}:
        return AuditResult(
            requirement,
            EvidenceStatus.INDIRECT,
            "only implementation-file evidence exists",
        )
    if existing:
        return AuditResult(requirement, EvidenceStatus.INDIRECT, "declared evidence is incomplete")
    return AuditResult(requirement, EvidenceStatus.MISSING, "declared evidence does not exist")
