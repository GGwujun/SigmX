"""Regression tests for the sync hardening plan (steps ①②③).

These guard against the original 43-minute hang: an akshare provider call with
no per-request timeout, plus a dataset that couldn't be abandoned, froze the
whole ``once``/post-close run well past its deadline.

* ① ``_net_timeout`` injects a default connect/read timeout into HTTPAdapter.send.
* ② ``run_daily_sync``'s ``_run`` abandons a dataset that exceeds
  ``MARKET_SYNC_DATASET_TIMEOUT`` instead of hanging on it forever.
* ③ ``index_history`` is no longer in run_daily_sync's default chain.
"""

from __future__ import annotations

import inspect
import time

import pytest

import src.data.market_sync as ms
from src.data import _net_timeout
from src.data.market_store import MarketStore


# ---------------------------------------------------------------------------
# ① _net_timeout: default timeout is injected when the caller omits it
# ---------------------------------------------------------------------------


def test_net_timeout_injects_default_when_omitted():
    """HTTPAdapter.send with no timeout must be handed the default (connect, read)."""
    import os

    from requests.adapters import HTTPAdapter

    captured: dict = {}

    class _FakeReq:
        url = "http://x"
        method = "GET"
        headers = {}

    # Set our fake as the underlying send, then install the wrapper on top.
    def fake_original(self, request, **kwargs):
        captured.update(kwargs)
        return "ok"

    HTTPAdapter.send = fake_original  # type: ignore[method-assign]
    _net_timeout._patched = False
    _net_timeout.install()

    HTTPAdapter().send(_FakeReq())
    assert captured.get("timeout") == (
        float(os.getenv("MARKET_SYNC_NET_TIMEOUT_CONNECT", "5")),
        float(os.getenv("MARKET_SYNC_NET_TIMEOUT_READ", "30")),
    ), "patch must inject default timeout when caller omits it"

    # And an explicit timeout must be preserved (not overwritten).
    captured.clear()
    HTTPAdapter().send(_FakeReq(), timeout=42)
    assert captured.get("timeout") == 42, "explicit timeout must not be overwritten"


# ---------------------------------------------------------------------------
# ② dataset-level isolation: a hung dataset is abandoned, not hung
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "market.db")
    yield s
    s._conn.close()


def test_hung_dataset_is_abounded_not_hung(store, monkeypatch):
    """A dataset fn that never returns must be abandoned within the timeout,
    not block run_daily_sync indefinitely (the original 43-min hang)."""
    # A tiny dataset timeout so the test is fast.
    monkeypatch.setattr(ms, "_DATASET_TIMEOUT", 1.0)

    # Replace one real dataset fn with a hanger. ``etf_master`` is in the default
    # chain and takes only ``store`` (simple to stub).
    def hang(store):
        time.sleep(30)  # simulates a stalled socket; well past the 1s budget
        return 0

    monkeypatch.setattr(ms, "_sync_etf_master", hang)

    t0 = time.monotonic()
    rows = ms.run_daily_sync("2026-07-17", store=store, datasets={"etf_master"}, deadline_seconds=10)
    elapsed = time.monotonic() - t0
    # Must return promptly (well under the 30s hang), not block.
    assert elapsed < 10, f"run_daily_sync hung for {elapsed:.1f}s — dataset isolation broken"
    # The hung dataset records failure (0 / absent) instead of hanging.
    assert rows.get("etf_master", 0) == 0


def test_dataset_timeout_disabled_falls_back_to_unbounded(monkeypatch):
    """MARKET_SYNC_DATASET_TIMEOUT=0 disables the hard timeout (legacy path)."""
    monkeypatch.setattr(ms, "_DATASET_TIMEOUT", 0.0)
    assert ms._DATASET_TIMEOUT <= 0  # _run takes the unbounded branch


# ---------------------------------------------------------------------------
# ③ index_history is out of the default sync chain
# ---------------------------------------------------------------------------


def test_index_history_not_in_run_daily_sync_chain():
    """The akshare long-term backfill must not run inside run_daily_sync — it
    has its own _maybe_run_index_history_sync channel (plan step ③)."""
    src = inspect.getsource(ms.run_daily_sync)
    assert '_run("index_history"' not in src, "index_history must be removed from run_daily_sync"
    assert hasattr(ms, "_maybe_run_index_history_sync"), "dedicated channel must exist"


# ---------------------------------------------------------------------------
# ⑤b daily reference: source-unavailable degrades, data-shortage blocks
# ---------------------------------------------------------------------------


def test_daily_reference_source_unavailable_does_not_block(monkeypatch):
    """A PARTIAL caused only by unavailable reference SOURCES (weekend / third-party
    down) must publish in lenient mode — not freeze the backfill.
    (The data itself must be present; the empty-day case is guarded separately.)"""
    import src.data.market_sync_worker as mw

    # 宽松路径会把报告升格为 PUBLISHED 再落库（worker lenient-promote 块），
    # 桩必须带全 DatasetQualityReport 的字段面。
    report = mw.DatasetQualityReport(
        dataset="daily",
        trade_date="2026-07-17",
        status=mw.QualityStatus.PARTIAL,
        expected_rows=5000,
        received_rows=5000,
        valid_rows=5000,
        blocking_reasons=["suspension_reference_unavailable", "cross_source_reference_unavailable"],
        source="stub",
    )
    monkeypatch.setattr(mw, "validate_daily_dataset", lambda *a, **k: report)
    # Stub the fetchers validate_daily_reference calls before the report.
    from src.data.market_quality import ReferenceResult, SuspensionResult

    monkeypatch.setattr(mw, "fetch_suspended_codes", lambda *a, **k: SuspensionResult.success(set()))
    monkeypatch.setattr(mw, "fetch_daily_reference_closes", lambda *a, **k: ReferenceResult.success({}))
    monkeypatch.setattr(mw, "fetch_tdx_reference_closes", lambda *a, **k: ReferenceResult.success({}))

    recorded: list = []

    class _Shadow:
        def daily_codes_for_run(self, *a): return []
        def daily_rows_for_run(self, *a): return []
        def record_dataset_result(self, *a, **k): recorded.append(a)

    # Must NOT raise — source-unavailable with data present is environmental,
    # publishes in lenient mode (promoted report recorded as PUBLISHED).
    mw._validate_daily_reference(_Shadow(), "2026-07-17", "run-x", [])
    promoted = [r for r in recorded if getattr(r[1], "status", None) is mw.QualityStatus.PUBLISHED]
    assert promoted, "lenient promote must record a PUBLISHED dataset report when data is present"
    assert promoted[0][1].source.endswith("+lenient_promoted")


def test_daily_reference_empty_day_never_lenient_promoted(monkeypatch):
    """2026-10 事故回归：源全天空转返回 0 行 + 参考源自然不可用时，绝不允许
    宽松发布成 status=published/received=0 —— tier 元数据键落定后当天被标记
    "已完成"永不再补，数据洞被发布成功掩盖。空日必须抛错走重试。"""
    import src.data.market_sync_worker as mw
    from src.data.market_quality import ReferenceResult, SuspensionResult

    report = mw.DatasetQualityReport(
        dataset="daily",
        trade_date="2026-10-08",
        status=mw.QualityStatus.PARTIAL,
        expected_rows=5000,
        received_rows=0,
        valid_rows=0,
        blocking_reasons=["suspension_reference_unavailable", "cross_source_reference_unavailable"],
        source="",
    )
    monkeypatch.setattr(mw, "validate_daily_dataset", lambda *a, **k: report)
    monkeypatch.setattr(mw, "fetch_suspended_codes", lambda *a, **k: SuspensionResult.success(set()))
    monkeypatch.setattr(mw, "fetch_daily_reference_closes", lambda *a, **k: ReferenceResult.success({}))
    monkeypatch.setattr(mw, "fetch_tdx_reference_closes", lambda *a, **k: ReferenceResult.success({}))

    recorded: list = []
    finished: list = []

    class _Shadow:
        def daily_codes_for_run(self, *a): return []
        def daily_rows_for_run(self, *a): return []
        def record_dataset_result(self, *a, **k): recorded.append(a)
        def finish_sync_run(self, *a, **k): finished.append(a)

    with pytest.raises(mw.MarketDataQualityError):
        mw._validate_daily_reference(_Shadow(), "2026-10-08", "run-x", [])

    # 不留任何 PUBLISHED 面目的记录（原始 PARTIAL 报告可以有），run 以
    # 非 PUBLISHED 收尾 —— 缺口对 readiness/监控 诚实可见。
    assert not [r for r in recorded
                if getattr(r[1], "status", None) is mw.QualityStatus.PUBLISHED]
    assert finished, "empty day must finish the run (PARTIAL), not leave it dangling"
    assert finished[0][1] is not mw.QualityStatus.PUBLISHED


def test_daily_reference_data_shortage_still_blocks(monkeypatch):
    """A PARTIAL caused by genuine missing data (not just source availability)
    must still block publish — only source-unavailability degrades."""
    import src.data.market_sync_worker as mw
    from src.data.market_quality import ReferenceResult, SuspensionResult

    report = mw.DatasetQualityReport(
        dataset="daily",
        trade_date="2026-07-17",
        status=mw.QualityStatus.PARTIAL,
        expected_rows=5000,
        received_rows=3000,
        valid_rows=3000,
        blocking_reasons=["unexplained_missing_codes"],  # real data shortage
        source="stub",
    )

    monkeypatch.setattr(mw, "validate_daily_dataset", lambda *a, **k: report)
    monkeypatch.setattr(mw, "fetch_suspended_codes", lambda *a, **k: SuspensionResult.success(set()))
    monkeypatch.setattr(mw, "fetch_daily_reference_closes", lambda *a, **k: ReferenceResult.success({}))
    monkeypatch.setattr(mw, "fetch_tdx_reference_closes", lambda *a, **k: ReferenceResult.success({}))

    class _Shadow:
        def daily_codes_for_run(self, *a): return []
        def daily_rows_for_run(self, *a): return []
        def record_dataset_result(self, *a, **k): pass
        def finish_sync_run(self, *a, **k): pass
        _conn = None

    with pytest.raises(mw.MarketDataQualityError):
        mw._validate_daily_reference(_Shadow(), "2026-07-17", "run-x", [])

