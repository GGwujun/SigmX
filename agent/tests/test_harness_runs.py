from __future__ import annotations

from pathlib import Path

from src.harness.runs import HarnessRunAdapter
from src.session.models import Attempt, AttemptStatus, Session
from src.session.store import SessionStore
from src.swarm.models import RunStatus, SwarmAgentSpec, SwarmRun, SwarmTask, TaskStatus
from src.swarm.store import SwarmStore


def test_session_and_swarm_runs_share_one_envelope(tmp_path: Path) -> None:
    sessions = SessionStore(tmp_path / "sessions")
    session = Session(session_id="s1", title="研究银行", last_attempt_id="a1")
    sessions.create_session(session)
    sessions.create_attempt(Attempt(
        attempt_id="a1", session_id="s1", status=AttemptStatus.COMPLETED,
        prompt="研究银行", summary="完成", created_at="2026-08-15T10:00:00",
        completed_at="2026-08-15T10:05:00",
        react_trace=[{"tool": "market_snapshot", "status": "ok", "evidence_ref": "market:20260815"}],
        metrics={"research_credits": 5}, run_dir=str(tmp_path / "private-run"),
    ))
    swarms = SwarmStore(tmp_path / "swarms")
    run = SwarmRun(
        id="w1", preset_name="alpha_forge", status=RunStatus.completed,
        user_vars={"target": "600519.SH"}, created_at="2026-08-15T11:00:00",
        completed_at="2026-08-15T11:20:00", total_input_tokens=100,
        total_output_tokens=20, final_report="private full report",
        agents=[SwarmAgentSpec(id="analyst", role="分析", system_prompt="x", tools=["market_snapshot"])],
        tasks=[SwarmTask(id="t1", agent_id="analyst", prompt_template="x", status=TaskStatus.completed, artifacts=[str(tmp_path / "report.md")])],
    )
    swarms.create_run(run)

    envelopes = HarnessRunAdapter(sessions, swarms).list(limit=10)
    assert [item.run_type for item in envelopes] == ["swarm", "session"]
    session_envelope = next(item for item in envelopes if item.run_type == "session")
    assert session_envelope.tool_calls == ("market_snapshot",)
    assert session_envelope.evidence_refs == ("market:20260815",)
    assert session_envelope.costs["research_credits"] == 5
    assert str(tmp_path) not in str(session_envelope.to_dict())
    swarm_envelope = next(item for item in envelopes if item.run_type == "swarm")
    assert swarm_envelope.result_ref == "swarm://w1/report"
    assert "private full report" not in str(swarm_envelope.to_dict())
    assert swarm_envelope.costs == {"input_tokens": 100, "output_tokens": 20}


def test_one_adapter_failure_returns_partial_degradation(tmp_path: Path) -> None:
    class BrokenSessions:
        def list_sessions(self, limit=50):
            raise RuntimeError("session store down")

    envelopes = HarnessRunAdapter(BrokenSessions(), SwarmStore(tmp_path / "empty")).list()
    assert len(envelopes) == 1
    assert envelopes[0].status == "partial"
    assert envelopes[0].degradations == ("session adapter unavailable",)
