"""Authoritative SQLite store for Financial Harness runs and observability."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InvalidRunTransition(Exception):
    pass


@dataclass(frozen=True)
class HarnessStep:
    id: str
    title: str
    status: str
    created_at: str


@dataclass(frozen=True)
class HarnessToolCall:
    id: str
    step_id: str | None
    tool_id: str
    status: str
    duration_ms: int
    input_data: dict[str, Any]
    output_ref: str | None


@dataclass(frozen=True)
class HarnessEvidence:
    id: str
    kind: str
    title: str
    ref: str
    source: str
    data_version: str | None


@dataclass(frozen=True)
class HarnessArtifact:
    id: str
    kind: str
    name: str
    ref: str


@dataclass(frozen=True)
class HarnessDegradation:
    id: str
    code: str
    message: str


@dataclass(frozen=True)
class HarnessGovernanceEvent:
    id: str
    level: str
    decision: str
    reason: str


@dataclass(frozen=True)
class HarnessRun:
    id: str
    user_id: str
    run_type: str
    title: str
    goal: str
    status: str
    context_manifest: dict[str, Any]
    result_ref: str | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    steps: tuple[HarnessStep, ...] = ()
    tool_calls: tuple[HarnessToolCall, ...] = ()
    evidence: tuple[HarnessEvidence, ...] = ()
    artifacts: tuple[HarnessArtifact, ...] = ()
    costs: dict[str, float] | None = None
    degradations: tuple[HarnessDegradation, ...] = ()
    governance_events: tuple[HarnessGovernanceEvent, ...] = ()


class HarnessStore:
    def __init__(self, db_path: Path, now: Callable[[], str] = _now_iso) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS harness_runs (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, run_type TEXT NOT NULL, title TEXT NOT NULL, goal TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled')),
            context_json TEXT NOT NULL, result_ref TEXT, error TEXT,
            created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_harness_runs_created ON harness_runs(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_harness_runs_user_created ON harness_runs(user_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS harness_steps (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, FOREIGN KEY(run_id) REFERENCES harness_runs(id)
        );
        CREATE TABLE IF NOT EXISTS harness_tool_calls (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, step_id TEXT, tool_id TEXT NOT NULL,
            status TEXT NOT NULL, duration_ms INTEGER NOT NULL, input_json TEXT NOT NULL,
            output_ref TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_evidence (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
            ref TEXT NOT NULL, source TEXT NOT NULL, data_version TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_artifacts (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
            ref TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_costs (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, dimension TEXT NOT NULL, amount REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_degradations (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, code TEXT NOT NULL, message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS harness_governance_events (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, level TEXT NOT NULL, decision TEXT NOT NULL,
            reason TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)
        self._conn.commit()

    def create_run(self, *, user_id: str, run_type: str, title: str, goal: str, context_manifest: dict[str, Any] | None = None) -> HarnessRun:
        run_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO harness_runs (id,user_id,run_type,title,goal,status,context_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, user_id, run_type, title, goal, "queued", json.dumps(context_manifest or {}, ensure_ascii=False), self._now()),
            )
            self._conn.commit()
        return self.get_run(run_id)

    def start_run(self, run_id: str) -> HarnessRun:
        return self._transition(run_id, {"queued"}, "running", started_at=self._now())

    def finish_run(self, run_id: str, *, result_ref: str) -> HarnessRun:
        return self._transition(run_id, {"running"}, "succeeded", result_ref=result_ref, finished_at=self._now())

    def fail_run(self, run_id: str, *, error: str) -> HarnessRun:
        return self._transition(run_id, {"queued", "running"}, "failed", error=error, finished_at=self._now())

    def cancel_run(self, run_id: str) -> HarnessRun:
        return self._transition(run_id, {"queued", "running"}, "cancelled", finished_at=self._now())

    def add_step(self, run_id: str, *, title: str, status: str) -> HarnessStep:
        item_id = self._insert("harness_steps", run_id, {"title": title, "status": status})
        row = self._conn.execute("SELECT * FROM harness_steps WHERE id=?", (item_id,)).fetchone()
        return HarnessStep(row["id"], row["title"], row["status"], row["created_at"])

    def add_tool_call(self, run_id: str, *, step_id: str | None, tool_id: str, status: str, duration_ms: int, input_data: dict[str, Any], output_ref: str | None) -> None:
        self._insert("harness_tool_calls", run_id, {"step_id": step_id, "tool_id": tool_id, "status": status, "duration_ms": duration_ms, "input_json": json.dumps(input_data, ensure_ascii=False), "output_ref": output_ref})

    def add_evidence(self, run_id: str, *, kind: str, title: str, ref: str, source: str, data_version: str | None) -> None:
        self._insert("harness_evidence", run_id, {"kind": kind, "title": title, "ref": ref, "source": source, "data_version": data_version})

    def add_artifact(self, run_id: str, *, kind: str, name: str, ref: str) -> None:
        self._insert("harness_artifacts", run_id, {"kind": kind, "name": name, "ref": ref})

    def add_cost(self, run_id: str, *, dimension: str, amount: float) -> None:
        self._insert("harness_costs", run_id, {"dimension": dimension, "amount": amount})

    def add_degradation(self, run_id: str, *, code: str, message: str) -> None:
        self._insert("harness_degradations", run_id, {"code": code, "message": message})

    def add_governance_event(self, run_id: str, *, level: str, decision: str, reason: str) -> None:
        self._insert("harness_governance_events", run_id, {"level": level, "decision": decision, "reason": reason})

    def get_run(self, run_id: str, *, user_id: str | None = None) -> HarnessRun | None:
        row = self._conn.execute("SELECT * FROM harness_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        if user_id is not None and row["user_id"] != user_id:
            return None
        return self._hydrate(row)

    def list_runs(self, *, user_id: str, run_type: str | None = None, status: str | None = None, limit: int = 100) -> list[HarnessRun]:
        clauses, params = ["user_id=?"], [user_id]
        if run_type:
            clauses.append("run_type=?"); params.append(run_type)
        if status:
            clauses.append("status=?"); params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM harness_runs {where} ORDER BY created_at DESC,id DESC LIMIT ?",
            (*params, max(1, min(limit, 500))),
        ).fetchall()
        return [self._hydrate(row) for row in rows]

    def _insert(self, table: str, run_id: str, values: dict[str, Any]) -> str:
        self.get_run(run_id)
        item_id = uuid.uuid4().hex
        columns = ["id", "run_id", *values, "created_at"]
        placeholders = ",".join("?" for _ in columns)
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
                (item_id, run_id, *values.values(), self._now()),
            )
            self._conn.commit()
        return item_id

    def _transition(self, run_id: str, allowed: set[str], target: str, **values: str) -> HarnessRun:
        current = self.get_run(run_id)
        if current.status not in allowed:
            raise InvalidRunTransition(f"cannot transition run from {current.status} to {target}")
        assignments = ["status=?", *(f"{key}=?" for key in values)]
        placeholders = ",".join("?" for _ in allowed)
        with self._lock:
            cursor = self._conn.execute(
                f"UPDATE harness_runs SET {','.join(assignments)} WHERE id=? AND status IN ({placeholders})",
                (target, *values.values(), run_id, *sorted(allowed)),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                raise InvalidRunTransition("run state changed concurrently")
            self._conn.commit()
        return self.get_run(run_id)

    def _hydrate(self, row) -> HarnessRun:
        run_id = row["id"]
        steps = tuple(HarnessStep(r["id"], r["title"], r["status"], r["created_at"]) for r in self._rows("harness_steps", run_id))
        tools = tuple(HarnessToolCall(r["id"], r["step_id"], r["tool_id"], r["status"], int(r["duration_ms"]), json.loads(r["input_json"]), r["output_ref"]) for r in self._rows("harness_tool_calls", run_id))
        evidence = tuple(HarnessEvidence(r["id"], r["kind"], r["title"], r["ref"], r["source"], r["data_version"]) for r in self._rows("harness_evidence", run_id))
        artifacts = tuple(HarnessArtifact(r["id"], r["kind"], r["name"], r["ref"]) for r in self._rows("harness_artifacts", run_id))
        degradations = tuple(HarnessDegradation(r["id"], r["code"], r["message"]) for r in self._rows("harness_degradations", run_id))
        governance = tuple(HarnessGovernanceEvent(r["id"], r["level"], r["decision"], r["reason"]) for r in self._rows("harness_governance_events", run_id))
        costs = {r["dimension"]: float(r["amount"]) for r in self._conn.execute("SELECT dimension,SUM(amount) amount FROM harness_costs WHERE run_id=? GROUP BY dimension", (run_id,)).fetchall()}
        return HarnessRun(
            id=run_id, user_id=row["user_id"], run_type=row["run_type"], title=row["title"], goal=row["goal"], status=row["status"],
            context_manifest=json.loads(row["context_json"]), result_ref=row["result_ref"], error=row["error"],
            created_at=row["created_at"], started_at=row["started_at"], finished_at=row["finished_at"],
            steps=steps, tool_calls=tools, evidence=evidence, artifacts=artifacts, costs=costs,
            degradations=degradations, governance_events=governance,
        )

    def _rows(self, table: str, run_id: str):
        return self._conn.execute(f"SELECT * FROM {table} WHERE run_id=? ORDER BY created_at,id", (run_id,)).fetchall()
