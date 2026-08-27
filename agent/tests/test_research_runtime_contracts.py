import pytest

from src.research_agent.contracts import ResearchEvidence, ResearchOutputV2, ResearchRuntimeState
from src.research_agent.output import EvidenceValidator


def test_output_rejects_cross_run_or_unknown_evidence() -> None:
    state = ResearchRuntimeState(run_id="run-1", max_iterations=50)
    output = ResearchOutputV2(
        run_id="run-1", mode="ai", summary="结论", conclusions=[{"text": "盈利改善", "evidence_ids": ["e-2"]}],
        evidence=[ResearchEvidence(id="e-1", run_id="run-1", source="Data Hub", field="roe", value=12.0)],
    )
    with pytest.raises(ValueError, match="unknown evidence"):
        EvidenceValidator.validate(output, state)


def test_rules_mode_is_explicitly_degraded() -> None:
    output = ResearchOutputV2(run_id="run-1", mode="rules_degraded", summary="规则结果")
    assert output.mode == "rules_degraded"
