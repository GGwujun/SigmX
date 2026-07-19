"""Tests for notification noise control — dedup / cooldown / quiet hours / severity.

The module persists state to ``~/.vibe-trading/noise_state.json``. Tests
monkeypatch the state path to a tmp dir so they never touch the real file, and
inject explicit ``now`` datetimes so time-based logic is deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.notify import noise_control as nc


_CST = timezone(timedelta(hours=8))


@pytest.fixture
def tmp_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect noise state to a tmp file."""
    state_file = tmp_path / "noise_state.json"
    monkeypatch.setattr(nc, "_state_path", lambda: state_file)
    return state_file


def _now(h: int, m: int = 0) -> datetime:
    return datetime(2026, 7, 17, h, m, tzinfo=_CST)


# ── severity ranking ────────────────────────────────────────────────────

def test_severity_rank_is_monotonic() -> None:
    assert nc.SEVERITY_RANK["info"] < nc.SEVERITY_RANK["warning"]
    assert nc.SEVERITY_RANK["warning"] < nc.SEVERITY_RANK["error"]
    assert nc.SEVERITY_RANK["error"] < nc.SEVERITY_RANK["critical"]


# ── quiet hours ─────────────────────────────────────────────────────────

def test_quiet_hours_same_day_window() -> None:
    # 09:00-12:00 → inside at 10:00, outside at 13:00
    assert nc._is_in_quiet_hours("09:00-12:00", _now(10)) is True
    assert nc._is_in_quiet_hours("09:00-12:00", _now(13)) is False
    # boundary: start inclusive, end exclusive
    assert nc._is_in_quiet_hours("09:00-12:00", _now(9)) is True
    assert nc._is_in_quiet_hours("09:00-12:00", _now(12)) is False


def test_quiet_hours_overnight_window() -> None:
    # 23:00-08:00 crosses midnight
    assert nc._is_in_quiet_hours("23:00-08:00", _now(23, 30)) is True
    assert nc._is_in_quiet_hours("23:00-08:00", _now(2)) is True
    assert nc._is_in_quiet_hours("23:00-08:00", _now(12)) is False
    assert nc._is_in_quiet_hours("23:00-08:00", _now(8)) is False  # end exclusive


def test_quiet_hours_invalid_format_returns_false() -> None:
    assert nc._is_in_quiet_hours("not-a-range", _now(10)) is False
    assert nc._is_in_quiet_hours("", _now(10)) is False
    assert nc._is_in_quiet_hours("9-5", _now(10)) is False


# ── config effectiveness ────────────────────────────────────────────────

def test_default_config_is_not_effective() -> None:
    assert nc.NoiseConfig().is_effective() is False


def test_config_with_any_rule_is_effective() -> None:
    assert nc.NoiseConfig(dedup_ttl_seconds=60).is_effective() is True
    assert nc.NoiseConfig(cooldown_seconds=60).is_effective() is True
    assert nc.NoiseConfig(quiet_hours="23:00-08:00").is_effective() is True
    assert nc.NoiseConfig(min_severity="warning").is_effective() is True


# ── evaluate_noise: ineffective config always sends ─────────────────────

def test_evaluate_ineffective_config_always_sends(tmp_state: Path) -> None:
    decision = nc.evaluate_noise(nc.NoiseConfig(), content="x", severity="info")
    assert decision.should_send is True
    assert decision.reason_code == "ok"


# ── evaluate_noise: min_severity filter (evaluated first after effective) ─

def test_min_severity_blocks_below_threshold(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(min_severity="warning")
    d = nc.evaluate_noise(cfg, content="x", severity="info", now=_now(10))
    assert d.should_send is False
    assert d.reason_code == "min_severity"


def test_min_severity_allows_at_or_above_threshold(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(min_severity="warning")
    d = nc.evaluate_noise(cfg, content="x", severity="warning", now=_now(10))
    assert d.should_send is True


# ── evaluate_noise: quiet hours ─────────────────────────────────────────

def test_quiet_hours_blocks_during_window(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(quiet_hours="23:00-08:00")
    d = nc.evaluate_noise(cfg, content="x", severity="critical", now=_now(3))
    # even critical is blocked by quiet hours (severity check passes, quiet blocks)
    assert d.should_send is False
    assert d.reason_code == "quiet_hours"


def test_quiet_hours_allows_outside_window(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(quiet_hours="23:00-08:00")
    d = nc.evaluate_noise(cfg, content="x", severity="info", now=_now(14))
    assert d.should_send is True


# ── evaluate_noise + record_sent: dedup lifecycle ───────────────────────

def test_dedup_blocks_repeat_within_ttl(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(dedup_ttl_seconds=3600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="same message", now=now)
    assert first.should_send is True
    nc.record_sent(first, cfg, now=now)

    # second identical message within TTL → blocked
    second = nc.evaluate_noise(cfg, content="same message", now=now)
    assert second.should_send is False
    assert second.reason_code == "dedup"


def test_dedup_allows_different_content(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(dedup_ttl_seconds=3600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="message A", now=now)
    nc.record_sent(first, cfg, now=now)
    other = nc.evaluate_noise(cfg, content="message B", now=now)
    assert other.should_send is True


def test_dedup_expires_after_ttl(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(dedup_ttl_seconds=3600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="msg", now=now)
    nc.record_sent(first, cfg, now=now)
    # 2 hours later → TTL expired
    later = nc.evaluate_noise(cfg, content="msg", now=now + timedelta(hours=2))
    assert later.should_send is True


# ── evaluate_noise + record_sent: cooldown lifecycle ────────────────────

def test_cooldown_blocks_same_route_within_window(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(cooldown_seconds=600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="a", route_type="report", now=now)
    assert first.should_send is True
    nc.record_sent(first, cfg, now=now)

    second = nc.evaluate_noise(cfg, content="b", route_type="report", now=now)
    assert second.should_send is False
    assert second.reason_code == "cooldown"


def test_cooldown_allows_different_route(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(cooldown_seconds=600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="a", route_type="report", now=now)
    nc.record_sent(first, cfg, now=now)
    other = nc.evaluate_noise(cfg, content="b", route_type="alert", now=now)
    assert other.should_send is True


def test_cooldown_expires_after_window(tmp_state: Path) -> None:
    cfg = nc.NoiseConfig(cooldown_seconds=600)
    now = _now(10)
    first = nc.evaluate_noise(cfg, content="a", route_type="report", now=now)
    nc.record_sent(first, cfg, now=now)
    later = nc.evaluate_noise(cfg, content="b", route_type="report",
                              now=now + timedelta(minutes=11))
    assert later.should_send is True


# ── evaluation order: min_severity before quiet_hours ────────────────────

def test_min_severity_checked_before_quiet_hours(tmp_state: Path) -> None:
    # both rules active, during quiet hours, low severity → min_severity wins
    cfg = nc.NoiseConfig(min_severity="critical", quiet_hours="23:00-08:00")
    d = nc.evaluate_noise(cfg, content="x", severity="info", now=_now(3))
    assert d.should_send is False
    assert d.reason_code == "min_severity"  # not quiet_hours


# ── stats ───────────────────────────────────────────────────────────────

def test_record_blocked_increments_stats(tmp_state: Path) -> None:
    nc.record_blocked("dedup", now=_now(10))
    # record_blocked writes blocked_<reason>_<today> directly into state stats
    import json
    state = json.loads(tmp_state.read_text(encoding="utf-8"))
    stats = state.get("stats", {})
    blocked_keys = [k for k in stats if k.startswith("blocked_dedup_")]
    assert len(blocked_keys) == 1
    assert stats[blocked_keys[0]] == 1


def test_get_noise_stats_shape_on_empty_state(tmp_state: Path) -> None:
    stats = nc.get_noise_stats()
    for key in ("date", "sent", "blocked_dedup", "blocked_cooldown",
                "blocked_quiet_hours", "blocked_min_severity",
                "dedup_entries", "cooldown_entries"):
        assert key in stats
    assert stats["sent"] == 0
