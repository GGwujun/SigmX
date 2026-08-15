"""Read-only adapters that normalize existing run stores for the Desktop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HarnessRunEnvelope:
    run_id: str
    run_type: str
    status: str
    started_at: str | None
    finished_at: str | None
    context_manifest: dict[str, Any] = field(default_factory=dict)
    tool_calls: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    costs: dict[str, int | float] = field(default_factory=dict)
    degradations: tuple[str, ...] = ()
    result_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HarnessRunAdapter:
    def __init__(self, session_store, swarm_store) -> None:
        self.session_store = session_store
        self.swarm_store = swarm_store

    def list(self, limit: int = 50) -> list[HarnessRunEnvelope]:
        envelopes: list[HarnessRunEnvelope] = []
        degradations: list[str] = []
        try:
            envelopes.extend(self._sessions(limit))
        except Exception:
            degradations.append("session adapter unavailable")
        try:
            envelopes.extend(self._swarms(limit))
        except Exception:
            degradations.append("swarm adapter unavailable")
        if degradations:
            envelopes.append(HarnessRunEnvelope(
                run_id="harness-adapter-status", run_type="system", status="partial",
                started_at=None, finished_at=None, degradations=tuple(degradations),
            ))
        envelopes.sort(key=lambda item: item.started_at or "", reverse=True)
        return envelopes[:limit]

    def _sessions(self, limit: int) -> list[HarnessRunEnvelope]:
        result: list[HarnessRunEnvelope] = []
        for session in self.session_store.list_sessions(limit=limit):
            if not session.last_attempt_id:
                continue
            attempt = self.session_store.get_attempt(session.session_id, session.last_attempt_id)
            if attempt is None:
                continue
            traces = attempt.react_trace or []
            tools = tuple(dict.fromkeys(str(row.get("tool") or row.get("action") or "") for row in traces if row.get("tool") or row.get("action")))
            evidence = tuple(dict.fromkeys(str(row["evidence_ref"]) for row in traces if row.get("evidence_ref")))
            costs = {
                key: value for key, value in (attempt.metrics or {}).items()
                if key in {"research_credits", "data_credits", "input_tokens", "output_tokens", "duration_ms"}
                and isinstance(value, (int, float))
            }
            degradations = (attempt.error,) if attempt.error else ()
            result.append(HarnessRunEnvelope(
                run_id=attempt.attempt_id, run_type="session", status=attempt.status.value,
                started_at=attempt.created_at, finished_at=attempt.completed_at,
                context_manifest={"session_id": session.session_id, "title": session.title},
                tool_calls=tools, evidence_refs=evidence, costs=costs,
                degradations=degradations,
                result_ref=f"session://{session.session_id}/attempt/{attempt.attempt_id}",
            ))
        return result

    def _swarms(self, limit: int) -> list[HarnessRunEnvelope]:
        result: list[HarnessRunEnvelope] = []
        for run in self.swarm_store.list_runs(limit=limit):
            tools = tuple(dict.fromkeys(tool for agent in run.agents for tool in agent.tools))
            artifacts = tuple(
                f"artifact://{run.id}/{Path(path).name}"
                for task in run.tasks for path in task.artifacts
            )
            degradations = tuple(
                f"{task.id}: {task.error or task.status.value}"
                for task in run.tasks if task.status.value in {"failed", "blocked", "cancelled"}
            )
            result.append(HarnessRunEnvelope(
                run_id=run.id, run_type="swarm", status=run.status.value,
                started_at=run.created_at, finished_at=run.completed_at,
                context_manifest={"preset": run.preset_name, "variables": dict(run.user_vars)},
                tool_calls=tools, evidence_refs=artifacts,
                costs={"input_tokens": run.total_input_tokens, "output_tokens": run.total_output_tokens},
                degradations=degradations, result_ref=f"swarm://{run.id}/report",
            ))
        return result
