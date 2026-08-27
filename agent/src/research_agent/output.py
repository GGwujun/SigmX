from __future__ import annotations

from src.research_agent.contracts import ResearchOutputV2, ResearchRuntimeState


class EvidenceValidator:
    @staticmethod
    def validate(output: ResearchOutputV2, state: ResearchRuntimeState) -> None:
        if output.run_id != state.run_id:
            raise ValueError("research output belongs to another run")
        known = {item.id for item in output.evidence if item.run_id == state.run_id}
        for conclusion in output.conclusions:
            references = {str(item) for item in conclusion.get("evidence_ids", [])}
            if not references.issubset(known):
                raise ValueError("research conclusion references unknown evidence")
