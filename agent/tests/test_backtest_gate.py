# -*- coding: utf-8 -*-
"""回测前置闸口：要么 Plan 要么 Refusal，接线 run_backtest 与 post-run 守卫。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.tools.backtest_gate import (
    DISCLOSURES,
    Plan,
    Refusal,
    apply_post_run,
    count_trading_days,
    plan_backtest,
)
from src.tools import backtest_tool


def _write_run(tmp_path: Path, **config) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True, exist_ok=True)
    (run_dir / "code" / "signal_engine.py").write_text("# stub\n", encoding="utf-8")
    base = {
        "source": "tushare",
        "codes": ["600519.SH"],
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "interval": "1D",
    }
    base.update(config)
    (run_dir / "config.json").write_text(
        json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return run_dir


# ---------------- 纯函数闸口 ----------------

@pytest.mark.unit
def test_refusal_bool_and_payload() -> None:
    ref = Refusal(("理由A",))
    assert not ref
    assert ref.as_dict() == {"ok": False, "reasons": ["理由A"],
                             "disclosures": list(DISCLOSURES)}


@pytest.mark.unit
def test_plan_bool_and_disclosures() -> None:
    plan = Plan()
    assert plan
    d = plan.as_dict()
    assert d["ok"] is True and d["warnings"] == []
    assert any("做空" in x for x in d["disclosures"])   # A股做空披露
    assert any("ST" in x for x in d["disclosures"])     # ST ±5% 披露


@pytest.mark.unit
def test_gate_refuses_empty_codes(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, codes=[])
    result = plan_backtest(run_dir, trading_days=lambda s, e: 300)
    assert not result
    assert any("codes 为空" in r for r in result.as_dict()["reasons"])


@pytest.mark.unit
def test_gate_refuses_reversed_dates(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path, start_date="2025-12-31", end_date="2025-01-01")
    result = plan_backtest(run_dir, trading_days=lambda s, e: 300)
    assert not result
    assert any("日期倒序" in r for r in result.as_dict()["reasons"])


@pytest.mark.unit
def test_gate_refuses_short_daily_window(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    result = plan_backtest(run_dir, trading_days=lambda s, e: 59)
    assert not result
    assert any("日线区间交易日仅 59 天" in r for r in result.as_dict()["reasons"])


@pytest.mark.unit
def test_gate_refuses_thin_intraday_bars(tmp_path: Path) -> None:
    # 100 交易日 × 每日 4 根 60m ≈ 400 根 < 500
    run_dir = _write_run(tmp_path, interval="60m")
    result = plan_backtest(run_dir, trading_days=lambda s, e: 100)
    assert not result
    assert any("400 根" in r and "60m" in r for r in result.as_dict()["reasons"])


@pytest.mark.unit
def test_gate_passes_healthy_daily_run(tmp_path: Path) -> None:
    run_dir = _write_run(tmp_path)
    result = plan_backtest(run_dir, trading_days=lambda s, e: 200)
    assert isinstance(result, Plan)
    assert result.as_dict()["ok"] is True


@pytest.mark.unit
def test_gate_refuses_missing_config(tmp_path: Path) -> None:
    result = plan_backtest(tmp_path / "nope")
    assert not result
    assert result.as_dict()["reasons"] == ["config.json 缺失或不可解析，无法过闸口"]


@pytest.mark.unit
def test_count_trading_days_sane_january() -> None:
    # 真实日历或周末规则，2026-01 都应有 ~3 周交易日
    n = count_trading_days("2026-01-01", "2026-01-31")
    assert 15 <= n <= 23
    assert count_trading_days("2026-01-10", "2026-01-10") == 0  # 周六


# ---------------- run_backtest 接线 ----------------

class _FakeRunner:
    """替身 Runner：可编程结果，用于验证闸口两端的接线。"""

    instances: list["_FakeRunner"] = []

    def __init__(self, timeout: int = 0) -> None:
        self.calls = 0
        _FakeRunner.instances.append(self)

    def execute(self, entry, run_path, cwd=None, cli_args=None):
        self.calls += 1
        return SimpleNamespace(
            success=True, exit_code=0, stdout="", stderr="",
            artifacts={"metrics.json": Path(run_path) / "artifacts" / "metrics.json"},
        )


@pytest.fixture(autouse=True)
def _allow_run_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    _FakeRunner.instances.clear()


@pytest.mark.unit
def test_run_backtest_refused_before_engine(tmp_path: Path,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backtest_tool, "Runner", _FakeRunner)
    run_dir = _write_run(tmp_path)  # 默认区间 2025 全年，但注入 10 个交易日

    monkeypatch.setattr(backtest_tool, "plan_backtest",
                        lambda rd, **kw: Refusal(("日线区间交易日仅 10 天（< 60）",)))
    payload = json.loads(backtest_tool.run_backtest(str(run_dir)))

    assert payload["status"] == "refused"
    assert payload["gate"]["ok"] is False
    assert "日线区间交易日仅 10 天" in payload["gate"]["reasons"][0]
    assert _FakeRunner.instances == []                      # 引擎一次都没跑
    assert json.loads((run_dir / "gate.json").read_text(
        encoding="utf-8"))["ok"] is False                   # 拒绝也留痕


@pytest.mark.unit
def test_run_backtest_gate_envelope_and_post_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backtest_tool, "Runner", _FakeRunner)
    run_dir = _write_run(tmp_path)
    monkeypatch.setattr(backtest_tool, "plan_backtest",
                        lambda rd, **kw: Plan())

    artifacts = run_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "trades.csv").write_text(
        "symbol,pnl\n600519.SH,100\n600519.SH,-50\n", encoding="utf-8")  # 2 笔 < 10

    payload = json.loads(backtest_tool.run_backtest(str(run_dir)))

    assert payload["status"] == "ok"
    assert payload["gate"]["ok"] is True
    assert payload["gate"]["disclosures"]
    assert any("交易笔数仅 2 笔" in w for w in payload["gate"]["warnings"])
    gate_file = json.loads((run_dir / "gate.json").read_text(encoding="utf-8"))
    assert gate_file["ok"] is True
    assert gate_file["warnings"] == payload["gate"]["warnings"]


@pytest.mark.unit
def test_post_run_no_trades_csv_warns(tmp_path: Path) -> None:
    plan = apply_post_run(Plan(), tmp_path)   # 目录里没有 artifacts/trades.csv
    assert any("trades.csv" in w for w in plan.warnings)


@pytest.mark.unit
def test_post_run_enough_trades_no_warning(tmp_path: Path) -> None:
    trades = tmp_path / "artifacts"
    trades.mkdir(parents=True)
    (trades / "trades.csv").write_text(
        "symbol,pnl\n" + "\n".join(f"c{i},1" for i in range(12)), encoding="utf-8")
    plan = apply_post_run(Plan(), tmp_path)
    assert plan.warnings == []
