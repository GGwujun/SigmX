# Market Data Quality Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent new incorrect or incomplete A-share daily data from entering the canonical database and block business consumers until the latest settled dataset is verified.

**Architecture:** The standalone `vibe-trading-sync` worker remains the only external-data fetcher and canonical writer. It synchronizes into a shadow database, records provenance, validates date/coverage/OHLC invariants, and publishes only verified data; FastAPI remains a read-only consumer and checks a shared readiness contract.

**Tech Stack:** Python 3.11+, SQLite, FastAPI, pytest, existing `MarketStore`, standalone `vibe-trading-sync` worker

## Global Constraints

- Missing data is preferable to incorrect data.
- `vibe-trading-sync` is the only external-data fetcher and canonical market-data writer.
- FastAPI handlers read canonical data only and never fetch external market data as fallback.
- Realtime quote snapshots never become canonical daily bars.
- Canonical daily prices use raw/unadjusted semantics.
- No exception, deadline, empty response, partial response, or failed quality gate may create a published state.
- Existing untracked `prototypes/` content is outside scope and must remain untouched.
- Phase 1 prevents new bad data; historical audit and rebuild are a separate Phase 2 plan.

---

## File Structure

- Create `agent/src/data/market_quality.py`: quality types, daily validation, readiness model.
- Modify `agent/src/data/market_store.py`: schema migration, run state, provenance, readiness queries.
- Modify `agent/src/data/market_sync.py`: source provenance, complete fallback, no realtime-to-daily writes.
- Modify `agent/src/data/market_sync_worker.py`: strict lifecycle and publication gate.
- Modify `agent/src/api/market_sync_routes.py`: read-only status and disabled in-process mutation.
- Modify `agent/src/api/daily_recommendation_routes.py`: verified readiness gate.
- Create `agent/tests/test_market_quality.py`, `test_market_sync_worker.py`, and `test_market_sync_api.py`.
- Modify existing market sync/store/recommendation tests.

---

### Task 1: Quality State, Run Persistence, and Provenance

**Files:**
- Create: `agent/src/data/market_quality.py`
- Modify: `agent/src/data/market_store.py:65-73,396-520,2277-2360`
- Test: `agent/tests/test_market_quality.py`
- Test: `agent/tests/test_market_store.py`

**Interfaces:**
- Produces: `QualityStatus`, `DatasetQualityReport`, `DataReadiness`.
- Produces: `MarketStore.create_sync_run()`, `finish_sync_run()`, `record_dataset_result()`, `get_data_readiness()`, and provenance-aware `upsert_daily_bars()`.

- [ ] **Step 1: Write failing model and persistence tests**

```python
def test_sync_run_and_dataset_result_round_trip(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    run_id = store.create_sync_run("2026-07-14", worker_id="test-worker")
    report = DatasetQualityReport(
        dataset="bars_daily",
        trade_date="2026-07-14",
        status=QualityStatus.VERIFIED,
        expected_rows=2,
        received_rows=2,
        valid_rows=2,
        source="tushare.daily",
    )
    store.record_dataset_result(run_id, report)
    store.finish_sync_run(run_id, QualityStatus.PUBLISHED)
    readiness = store.get_data_readiness("bars_daily", "2026-07-14")
    assert readiness.ready is True
    assert readiness.run_id == run_id
    assert readiness.valid_rows == 2


def test_daily_bar_provenance_round_trip(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_daily_bars(
        "600000.SH",
        [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        source="tushare.daily",
        sync_run_id="run-1",
        quality_status="verified",
    )
    row = store._conn.execute(
        "SELECT source, sync_run_id, quality_status FROM bars_daily WHERE code=? AND trade_date=?",
        ("600000.SH", "2026-07-14"),
    ).fetchone()
    assert tuple(row) == ("tushare.daily", "run-1", "verified")
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest -q agent/tests/test_market_quality.py agent/tests/test_market_store.py
```

Expected: failures because quality types, sync tables, provenance columns, and methods do not exist.

- [ ] **Step 3: Implement quality types**

```python
from dataclasses import dataclass, field
from enum import StrEnum


class QualityStatus(StrEnum):
    PENDING = "pending"
    FETCHING = "fetching"
    VALIDATING = "validating"
    VERIFIED = "verified"
    PUBLISHED = "published"
    PARTIAL = "partial"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class DatasetQualityReport:
    dataset: str
    trade_date: str
    status: QualityStatus
    expected_rows: int
    received_rows: int
    valid_rows: int
    published_rows: int = 0
    missing_codes: list[str] = field(default_factory=list)
    invalid_rows: list[dict] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    source: str = ""


@dataclass(frozen=True)
class DataReadiness:
    dataset: str
    as_of: str
    status: QualityStatus
    expected_rows: int
    valid_rows: int
    published_rows: int
    source: str
    run_id: str
    blocking_reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status in {QualityStatus.VERIFIED, QualityStatus.PUBLISHED}
```

- [ ] **Step 4: Implement idempotent SQLite schema and methods**

Add `sync_runs`, `sync_dataset_runs`, and `data_quarantine`. Migrate `bars_daily` with `source`, `sync_run_id`, `quality_status`, and `ingested_at`. Update the exact signature:

```python
def upsert_daily_bars(
    self,
    code: str,
    rows: list[dict],
    *,
    source: str = "unknown",
    sync_run_id: str = "",
    quality_status: str = "unverified",
) -> int:
```

Store report details as JSON. `get_data_readiness(dataset, as_of)` reconstructs the latest dataset result for the exact date and never treats `partial`, `failed`, or `quarantined` as ready.

- [ ] **Step 5: Run tests and verify GREEN**

```powershell
python -m pytest -q agent/tests/test_market_quality.py agent/tests/test_market_store.py
```

- [ ] **Step 6: Commit**

```powershell
git add agent/src/data/market_quality.py agent/src/data/market_store.py agent/tests/test_market_quality.py agent/tests/test_market_store.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat(data): add quality state and market provenance"
```

---

### Task 2: Strict Daily Validation and Source Isolation

**Files:**
- Modify: `agent/src/data/market_quality.py`
- Modify: `agent/src/data/market_sync.py:499-635,1615-1658,4352-4485`
- Test: `agent/tests/test_market_quality.py`
- Test: `agent/tests/test_market_sync.py`

**Interfaces:**
- Consumes: Task 1 quality types and provenance-aware store.
- Produces: `fetch_suspended_codes(trade_date)` using authoritative Tushare `suspend_d` data.
- Produces: `fetch_daily_reference_closes(trade_date, sample_codes)` using settled TPDog daily bars.
- Produces: `validate_daily_dataset(store, trade_date, expected_codes, run_id, suspension_result, reference_result)`.
- Produces: missing-symbol historical fallback without realtime-to-daily conversion.

- [ ] **Step 1: Write failing validator tests**

```python
def test_daily_validator_rejects_invalid_ohlc(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_daily_bars(
        "600000.SH",
        [{"date": "2026-07-14", "open": 10, "high": 9, "low": 8, "close": 10.5, "volume": 100}],
        source="tushare.daily", sync_run_id="run-1",
    )
    report = validate_daily_dataset(store, "2026-07-14", ["600000.SH"], "run-1")
    assert report.status == QualityStatus.QUARANTINED
    assert report.invalid_rows[0]["code"] == "600000.SH"


def test_daily_validator_rejects_unexplained_missing_code(tmp_path):
    store = MarketStore(tmp_path / "market.db")
    store.upsert_daily_bars(
        "600000.SH",
        [{"date": "2026-07-14", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        source="tushare.daily", sync_run_id="run-1",
    )
    report = validate_daily_dataset(
        store, "2026-07-14", ["600000.SH", "000001.SZ"], "run-1",
        suspension_result=SuspensionResult.available(set()),
        reference_result=matching_reference_result("600000.SH"),
    )
    assert report.status == QualityStatus.PARTIAL
    assert report.missing_codes == ["000001.SZ"]


def test_daily_validator_blocks_when_suspension_reference_is_unavailable(tmp_path):
    report = validate_daily_dataset(
        store, "2026-07-14", ["600000.SH"], "run-1",
        suspension_result=SuspensionResult.unavailable("tushare timeout"),
        reference_result=matching_reference_result(),
    )
    assert report.status == QualityStatus.PARTIAL
    assert "suspension_reference_unavailable" in report.blocking_reasons


def test_daily_validator_excludes_confirmed_suspension(tmp_path):
    report = validate_daily_dataset(
        store, "2026-07-14", ["600000.SH", "000001.SZ"], "run-1",
        suspension_result=SuspensionResult.available({"000001.SZ"}),
        reference_result=matching_reference_result("600000.SH"),
    )
    assert report.status == QualityStatus.VERIFIED


def test_daily_validator_quarantines_cross_source_close_mismatch(tmp_path):
    insert_valid_bar(store, code="600000.SH", close=10.50, run_id="run-1")
    report = validate_daily_dataset(
        store, "2026-07-14", ["600000.SH"], "run-1",
        suspension_result=SuspensionResult.available(set()),
        reference_result=ReferenceResult.available({"600000.SH": 10.80}),
    )
    assert report.status == QualityStatus.QUARANTINED
    assert "cross_source_close_mismatch" in report.blocking_reasons
```

- [ ] **Step 2: Write failing sync regression tests**

```python
def test_partial_tushare_bulk_fetches_missing_symbols(store):
    codes = ["600000.SH", "000001.SZ"]
    with mock.patch.object(ms, "_all_a_share_codes", return_value=codes), \
         mock.patch.object(ms, "_sync_daily_tushare_by_date", return_value=1), \
         mock.patch.object(store, "last_daily_date", side_effect=lambda code: "2026-07-14" if code == "600000.SH" else None), \
         mock.patch.object(ms, "_sync_daily_for_code", return_value=1) as fallback, \
         mock.patch.object(ms, "_today_cst_str", return_value="2026-07-15"):
        result = ms.run_daily_sync("2026-07-14", store=store, datasets={"daily"})
    fallback.assert_called_once()
    assert fallback.call_args.args[1] == "000001.SZ"
    assert result["daily"] == 2


def test_daily_sync_never_uses_realtime_as_settled_bar(store):
    with mock.patch.object(ms, "_sync_daily_tushare_by_date", return_value=0), \
         mock.patch.object(ms, "_sync_daily_for_code", return_value=0), \
         mock.patch.object(ms, "_sync_daily_from_realtime_snapshot") as realtime_fallback, \
         mock.patch.object(ms, "_all_a_share_codes", return_value=["600000.SH"]), \
         mock.patch.object(ms, "_today_cst_str", return_value="2026-07-15"):
        ms.run_daily_sync("2026-07-14", store=store, datasets={"daily"})
    realtime_fallback.assert_not_called()
```

- [ ] **Step 3: Run tests and verify RED**

```powershell
python -m pytest -q agent/tests/test_market_quality.py agent/tests/test_market_sync.py
```

- [ ] **Step 4: Implement authoritative suspension and cross-source inputs**

Add typed `SuspensionResult` and `ReferenceResult` objects that distinguish an authoritative empty result from an unavailable provider. Fetch suspensions with Tushare `suspend_d(trade_date=YYYYMMDD)` and normalize `ts_code`. Select a deterministic reference sample (core strategy codes first, then sorted universe, capped at 10), fetch exact-date settled daily bars from TPDog, and capture source/error metadata. Provider unavailability is never represented as an empty successful result.

- [ ] **Step 5: Implement validator behavior**

Query exact-date rows for `run_id`; enforce positive OHLC, `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`, non-negative volume, exact date, source, and run provenance. Subtract only confirmed suspensions from expected codes. Require the suspension query to be available and the deterministic reference sample to be complete; compare close prices with a configurable tolerance defaulting to 0.1%. Return `QUARANTINED` for invalid rows or cross-source mismatches, `PARTIAL` for unexplained missing codes or unavailable verification inputs, and `VERIFIED` only for a complete valid set. Persist invalid rows and mismatches to `data_quarantine`.

- [ ] **Step 6: Remove realtime fallback and complete partial bulk results**

```python
bulk_written = _sync_daily_tushare_by_date(..., sync_run_id=sync_run_id)
missing_codes = [code for code in daily_codes if store.last_daily_date(code) != trade_date]
written = bulk_written
for code in missing_codes:
    written += _sync_daily_for_code(
        store, code, trade_date, today_str,
        lookback_days=lookback_days, deadline=deadline, sync_run_id=sync_run_id,
    )
result["daily"] = written
```

Remove both settled-daily calls to `_sync_daily_from_realtime_snapshot`. Attach `tushare.daily` or `tpdog.stock/daily` source provenance to each write.

- [ ] **Step 7: Run tests and verify GREEN**

```powershell
python -m pytest -q agent/tests/test_market_quality.py agent/tests/test_market_sync.py agent/tests/test_market_store.py
```

- [ ] **Step 8: Commit**

```powershell
git add agent/src/data/market_quality.py agent/src/data/market_sync.py agent/tests/test_market_quality.py agent/tests/test_market_sync.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "fix(data): validate complete settled daily datasets"
```

---

### Task 3: Worker Publication Gate

**Files:**
- Modify: `agent/src/data/market_sync_worker.py:74-209`
- Test: `agent/tests/test_market_sync_worker.py`

**Interfaces:**
- Consumes: Task 1 run persistence and Task 2 validator.
- Produces: shadow publication only after verified quality; failed runs remain retryable.

- [ ] **Step 1: Write failing worker tests**

```python
def test_partial_daily_dataset_is_not_published(tmp_path, monkeypatch):
    live, shadow = tmp_path / "live.db", tmp_path / "shadow.db"
    MarketStore(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *a, **k: {"daily": 1})
    monkeypatch.setattr(worker, "validate_daily_dataset", lambda *a, **k: partial_report())
    publish = Mock()
    monkeypatch.setattr(worker, "_publish_shadow", publish)
    with pytest.raises(MarketDataQualityError):
        worker._run_post_close_shadow_sync(
            "2026-07-14", live_db=live, shadow_db=shadow,
            datasets={"daily"}, deadline_seconds=60, lookback_days=30,
        )
    publish.assert_not_called()
    assert MarketStore(live).get_meta("daemon:2026-07-14") is None


def test_verified_daily_dataset_publishes(tmp_path, monkeypatch):
    live, shadow = tmp_path / "live.db", tmp_path / "shadow.db"
    MarketStore(live)
    monkeypatch.setattr(worker, "run_daily_sync", lambda *a, **k: {"daily": 2})
    monkeypatch.setattr(worker, "validate_daily_dataset", lambda *a, **k: verified_report(2))
    result = worker._run_post_close_shadow_sync(
        "2026-07-14", live_db=live, shadow_db=shadow,
        datasets={"daily"}, deadline_seconds=60, lookback_days=30,
    )
    assert result == {"daily": 2}
    assert MarketStore(live).get_meta("daemon:2026-07-14") is not None
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest -q agent/tests/test_market_sync_worker.py
```

- [ ] **Step 3: Implement lifecycle in this exact order**

```python
run_id = shadow_store.create_sync_run(trade_date, worker_id=_worker_id())
rows = run_daily_sync(..., sync_run_id=run_id)
report = validate_daily_dataset(
    shadow_store,
    trade_date,
    expected_codes,
    run_id,
    suspension_result=fetch_suspended_codes(trade_date),
    reference_result=fetch_daily_reference_closes(trade_date, reference_sample),
)
shadow_store.record_dataset_result(run_id, report)
if report.status is not QualityStatus.VERIFIED:
    shadow_store.finish_sync_run(run_id, report.status, error_summary="; ".join(report.blocking_reasons))
    raise MarketDataQualityError(report)
shadow_store.finish_sync_run(run_id, QualityStatus.VERIFIED)
if not _integrity_ok(shadow_db):
    raise RuntimeError(f"shadow DB integrity check failed: {shadow_db}")
_publish_shadow(shadow_db, live_db)
live_store = MarketStore(live_db)
if not live_store.get_data_readiness("bars_daily", trade_date).ready:
    raise RuntimeError("post-publication readiness verification failed")
live_store.finish_sync_run(run_id, QualityStatus.PUBLISHED)
live_store.set_meta(meta_key, _now_cst().isoformat())
```

- [ ] **Step 4: Run regression tests**

```powershell
python -m pytest -q agent/tests/test_market_sync_worker.py agent/tests/test_market_sync.py agent/tests/test_market_store.py agent/tests/test_market_quality.py
```

- [ ] **Step 5: Commit**

```powershell
git add agent/src/data/market_sync_worker.py agent/tests/test_market_sync_worker.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "fix(data): gate shadow publication on verified quality"
```

---

### Task 4: Read-Only API and Consumer Readiness

**Files:**
- Modify: `agent/src/api/market_sync_routes.py:129-267`
- Modify: `agent/src/api/daily_recommendation_routes.py:337-365`
- Test: `agent/tests/test_market_sync_api.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Consumes: `MarketStore.get_data_readiness()` and expected settled date.
- Produces: read-only sync API and structured `DATA_NOT_READY` blocking.

- [ ] **Step 1: Write failing boundary tests**

```python
def test_daily_sync_endpoint_does_not_run_sync_in_api(client, monkeypatch):
    run = Mock(side_effect=AssertionError("query service must not synchronize"))
    monkeypatch.setattr("src.data.market_sync.run_daily_sync", run)
    response = client.post("/market-sync/daily", json={"datasets": ["daily"]}, headers=admin_headers())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SYNC_WORKER_REQUIRED"
    run.assert_not_called()


def test_recommendations_reject_unverified_data(monkeypatch):
    monkeypatch.setattr(routes, "_daily_data_readiness", lambda: partial_readiness())
    with pytest.raises(HTTPException) as exc:
        routes._assert_candidate_market_data_fresh()
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "DATA_NOT_READY"
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest -q agent/tests/test_market_sync_api.py agent/tests/test_daily_recommendation_routes.py
```

- [ ] **Step 3: Disable API-side synchronization**

All mutating sync endpoints return:

```python
raise HTTPException(
    status_code=409,
    detail={
        "code": "SYNC_WORKER_REQUIRED",
        "message": "Run synchronization through vibe-trading-sync once; the business API is read-only.",
    },
)
```

Keep status and health endpoints read-only and expose readiness counts, run ID, source, status, and blocking reasons.

- [ ] **Step 4: Replace recommendation freshness comparison**

Resolve the expected settled date, read exact-date readiness, and reject non-ready states:

```python
raise HTTPException(
    status_code=503,
    detail={
        "code": "DATA_NOT_READY",
        "dataset": "bars_daily",
        "expected_date": expected_date,
        "status": readiness.status,
        "blocking_reasons": readiness.blocking_reasons,
    },
)
```

Delete the old daily-versus-realtime date-gap heuristic.

- [ ] **Step 5: Run tests and verify GREEN**

```powershell
python -m pytest -q agent/tests/test_market_sync_api.py agent/tests/test_daily_recommendation_routes.py agent/tests/test_opportunity_routes.py
```

- [ ] **Step 6: Commit**

```powershell
git add agent/src/api/market_sync_routes.py agent/src/api/daily_recommendation_routes.py agent/tests/test_market_sync_api.py agent/tests/test_daily_recommendation_routes.py
git -c user.name=Codex -c user.email=codex@openai.com commit -m "fix(api): enforce read-only verified market data"
```

---

### Task 5: Integration Verification and Operations

**Files:**
- Modify: `README.md`
- Modify: `docker-compose.yml` only if API daemon separation changed upstream.
- Test: all Task 1-4 tests.

**Interfaces:**
- Consumes: strict worker and readiness gate.
- Produces: supported operator commands and complete regression evidence.

- [ ] **Step 1: Document supported operations**

Document that `vibe-trading-sync worker --interval 60` is the production writer, `vibe-trading-sync once --date YYYY-MM-DD` is the manual recovery command, FastAPI sync POST endpoints are disabled, and a failed quality gate preserves the previous canonical database while blocking recommendations.

- [ ] **Step 2: Run focused backend suite**

```powershell
python -m pytest -q agent/tests/test_market_quality.py agent/tests/test_market_store.py agent/tests/test_market_sync.py agent/tests/test_market_sync_worker.py agent/tests/test_market_sync_api.py agent/tests/test_daily_recommendation_routes.py agent/tests/test_opportunity_routes.py agent/tests/test_market_data_service.py
```

- [ ] **Step 3: Run lint and compile verification**

```powershell
python -m ruff check agent/src/data/market_quality.py agent/src/data/market_store.py agent/src/data/market_sync.py agent/src/data/market_sync_worker.py agent/src/api/market_sync_routes.py agent/src/api/daily_recommendation_routes.py agent/tests/test_market_quality.py agent/tests/test_market_sync_worker.py agent/tests/test_market_sync_api.py
python -m compileall -q agent/src agent/api_server.py
```

- [ ] **Step 4: Verify process boundary and repository scope**

```powershell
rg -n "MARKET_SYNC_DAEMON_ENABLED|vibe-trading-sync" docker-compose.yml docker/start-server.sh README.md
git status --short
git diff --check
```

Expected: API daemon is disabled, worker command exists, only planned files changed, and `prototypes/` is untouched.

- [ ] **Step 5: Commit**

```powershell
git add README.md docker-compose.yml
git -c user.name=Codex -c user.email=codex@openai.com commit -m "docs(data): document strict sync operations"
```

---

## Phase 2 Follow-Up

After Phase 1 produces verified runs, create `docs/superpowers/plans/2026-07-14-market-data-quality-phase2-repair.md` covering an immutable production backup, a 120-settled-day audit, authoritative rebuild through the Phase 1 validator, dependent-cache invalidation, and a reconciliation report. Phase 2 must not touch production until the operator confirms backup location and retention policy.
