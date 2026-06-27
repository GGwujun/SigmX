"""Shared fixtures and sys.path setup for all tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure agent/ is on sys.path so imports like `backtest.*` and `src.*` work.
AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))


@pytest.fixture(autouse=True)
def isolate_real_env_tokens(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Keep unit tests from reading the developer machine's real agent/.env."""
    for name in ("TUSHARE_TOKEN", "TPDOG_TOKEN", "TS_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIBE_TRADING_ENV_PATH", str(tmp_path / ".env"))
    yield
