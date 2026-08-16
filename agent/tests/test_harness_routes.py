from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import src.api.harness_routes as routes
from src.agent.tools import ToolRegistry
from src.harness.registry import HarnessToolRegistry
from src.harness.store import HarnessStore


@pytest.fixture(autouse=True)
def harness_dependencies(monkeypatch, tmp_path: Path):
    routes._registry = HarnessToolRegistry.from_tool_registry(ToolRegistry())
    routes._store = HarnessStore(tmp_path / "harness.db", now=lambda: "2026-08-16T03:00:00+00:00")
    monkeypatch.setattr(routes, "_status", lambda user_id: {
        "runtime_available": True, "cloud_connected": False,
        "local_data_available": True, "data_hub_available": True,
        "research_credits": 50, "data_credits": 1000,
        "governance_ceiling": "simulate", "degradations": ["cloud offline"],
    })
    yield
    routes._registry = None
    routes._store = None


def test_status_and_runs_are_normalized_for_authenticated_user() -> None:
    status = asyncio.run(routes.harness_status(user={"id": "u1"}))
    assert status.governance_ceiling == "simulate"
    assert status.degradations == ["cloud offline"]
    created = asyncio.run(routes.create_harness_run(
        routes.CreateHarnessRunRequest(run_type="research", title="茅台研究", goal="验证盈利质量", context_manifest={"current_symbol": "600519.SH"}),
        user={"id": "u1"},
    ))
    runs = asyncio.run(routes.harness_runs(limit=20, run_type=None, status=None, user={"id": "u1"}))
    assert runs.items[0].run_type == "research"
    assert runs.items[0].title == "茅台研究"
    detail = asyncio.run(routes.harness_run(created.run_id, user={"id": "u1"}))
    assert detail.context_manifest == {"current_symbol": "600519.SH"}
    cancelled = asyncio.run(routes.cancel_harness_run(created.run_id, user={"id": "u1"}))
    assert cancelled.status == "cancelled"


def test_unknown_harness_run_returns_404() -> None:
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.harness_run("missing", user={"id": "u1"}))
    assert error.value.status_code == 404


def test_harness_runs_are_private_to_current_user() -> None:
    created = asyncio.run(routes.create_harness_run(
        routes.CreateHarnessRunRequest(run_type="backtest", title="私有回测", goal="验证"),
        user={"id": "u1"},
    ))
    with pytest.raises(routes.HTTPException) as error:
        asyncio.run(routes.harness_run(created.run_id, user={"id": "u2"}))
    assert error.value.status_code == 404


def test_context_preview_never_returns_file_paths_or_secrets(tmp_path: Path) -> None:
    private = tmp_path / "portfolio-secret.txt"
    private.write_text("password=do-not-leak", encoding="utf-8")
    result = asyncio.run(routes.harness_context_preview(
        routes.ContextPreviewRequest(
            current_symbol="600519.SH", cloud_watchlist_refs=["600519.SH"],
            risk_profile_ref="balanced", market_snapshot_ref="market:v1",
            local_files=[str(private)], extra={"api_key": "secret", "theme": "quality"},
        ),
        user={"id": "u1"},
    ))
    dumped = result.model_dump_json()
    assert str(private) not in dumped
    assert "do-not-leak" not in dumped
    assert '"api_key"' not in dumped
    assert result.local_files[0].local_only is True


def test_harness_routes_require_user_dependency() -> None:
    protected = {"/api/harness/status", "/api/harness/tools", "/api/harness/runs", "/api/harness/runs/{run_id}", "/api/harness/runs/{run_id}/cancel", "/api/harness/context/preview"}
    for route in routes.router.routes:
        if route.path in protected:
            assert route.dependant.dependencies
