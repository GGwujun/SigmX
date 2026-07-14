# Market Data Quality Design

**Date:** 2026-07-14  
**Status:** Approved for implementation  
**Scope:** A-share market-data ingestion, validation, publication, readiness, and historical repair

## 1. Objective

Make market data correctness a hard system invariant: missing data is allowed and visible, but unverified or approximate data must never be presented as canonical settled data. Daily recommendations, factor computation, backtests, and business queries must consume only published datasets that passed explicit quality gates.

The work has two delivery phases:

1. Prevent new bad data: strict ingestion, validation, publication, truthful status, and consumer readiness gates.
2. Repair existing bad data: audit, quarantine, authoritative rebuild, and dependent-cache invalidation.

Recommendation ranking logic is outside this design except for blocking recommendation generation when required data is not ready.

## 2. Architectural Boundary

The existing process separation is mandatory and must be strengthened:

- **Fetch/sync worker:** the standalone `vibe-trading-sync` process is the only component allowed to fetch external market data, populate staging data, run quality checks, publish canonical data, and update dataset readiness.
- **Canonical market database:** contains only verified, published market data plus immutable provenance and readiness metadata.
- **Business query service:** FastAPI serves queries and recommendations from canonical data. It must not call external market-data sources as a fallback and must not execute synchronization in-process.

The API-side market-sync daemon remains disabled in deployment. Existing administrative synchronization endpoints must no longer execute `run_daily_sync()` inside the API process. The first implementation may disable mutating endpoints with an explicit operator message and retain the standalone CLI as the supported trigger. A later control-plane queue is not required for this scope.

## 3. Current Failure Modes

The design addresses these confirmed failures:

- Dataset exceptions are caught independently, but a day is still marked complete.
- Global deadlines can stop a run after partial work without making the run fail.
- Any non-zero bulk response can suppress missing-symbol fallback work.
- Realtime snapshots can be converted into canonical settled daily bars.
- SQLite integrity checks validate file structure, not market-data correctness.
- Canonical daily bars have no source, run, or quality provenance.
- Freshness checks compare two possibly stale tables instead of the expected settled trading date.
- Admin sync APIs report success for empty or partial results.

## 4. Data Model

### 4.1 Sync runs

Add `sync_runs` with one row per worker execution:

- `run_id`: stable UUID
- `trade_date`: requested market date
- `started_at`, `finished_at`
- `status`: `pending`, `fetching`, `validating`, `verified`, `published`, `partial`, `failed`, or `quarantined`
- `deadline_at`
- `error_summary`
- `worker_id`

Add `sync_dataset_runs` with one row per run and dataset:

- `run_id`, `dataset`
- `status`
- `source`
- `expected_rows`, `received_rows`, `valid_rows`, `published_rows`
- `missing_rows`, `invalid_rows`
- `latest_trade_date`
- `quality_report_json`
- `error_summary`
- timestamps

The legacy `daemon:<date>` metadata may remain temporarily for compatibility, but it can be written only after the critical datasets have status `published`. It must never be the source of truth for readiness.

### 4.2 Staging and provenance

Add `bars_daily_staging` keyed by `(run_id, code, trade_date, source)`. It stores normalized OHLCV, raw source identity, collection timestamp, and validation errors.

Extend canonical `bars_daily` with:

- `source`
- `sync_run_id`
- `quality_status`, fixed to `verified` for canonical rows
- `ingested_at`

Canonical bars use unadjusted/raw price semantics. Adjusted series must be derived separately and must not be mixed into `bars_daily`.

Add `data_quarantine` for rejected rows or batches, including dataset, run, key, reason, and a sanitized payload snapshot.

Realtime data remains only in `realtime_quote_snapshot`. It is provisional and is never copied into `bars_daily`.

## 5. Ingestion and Publication Flow

For each settled trading date:

1. Worker creates a `sync_runs` record.
2. Source adapters fetch data and normalize symbol, date, price, volume, and amount units.
3. Rows are written to staging, never directly to canonical tables.
4. Dataset validators generate deterministic quality reports.
5. Invalid rows and failed batches enter quarantine.
6. Critical datasets must all reach `verified` before publication.
7. Publication occurs in a single database transaction or by publishing a verified shadow database.
8. The worker records `published` only after post-publication verification succeeds.
9. Failed or partial datasets remain retryable; no completion marker is written.

Source priority for daily bars is:

1. Tushare whole-market settled daily data.
2. TPDog historical daily data for explicit missing-symbol repair.
3. A configured historical fallback with the same raw-price semantics.

Realtime quotes are excluded from this hierarchy.

## 6. Quality Gates

### 6.1 Expected date

The worker resolves the latest settled A-share trading date from the trading calendar. A batch for another date cannot satisfy current readiness. Weekend-only fallback may schedule retries but cannot certify a dataset as verified when the authoritative calendar is unavailable.

### 6.2 Row validity

Every daily row must satisfy:

- valid project symbol and a security active on the requested date
- exact target `trade_date`
- positive open, high, low, and close
- `high >= max(open, close)`
- `low <= min(open, close)`
- `high >= low`
- non-negative volume and amount when present
- no duplicate canonical key
- normalized units and raw/unadjusted price basis

When previous close is available, reported change must agree with the calculated change within a configured rounding tolerance. Implausible jumps that are not explained by corporate actions are quarantined.

### 6.3 Coverage

The expected universe is the set of securities active on the target date, excluding securities confirmed as suspended for that date. Publication requires no unexplained missing symbols.

If authoritative suspension data is unavailable, the dataset cannot claim full verification. It remains `degraded` or `partial`, is not published as the current settled dataset, and recommendations stay blocked. This intentionally prefers missing data to silently incomplete data.

### 6.4 Cross-source consistency

Core indices and a deterministic stock sample are checked against an independent source. Price differences must be within the greater of one price tick or the configured relative tolerance. Systematic direction, unit, or scale discrepancies reject the batch.

### 6.5 Post-publication checks

After publication, re-read canonical data and verify target date, row count, provenance, and key invariants. Readiness is updated only after this check passes.

## 7. Retry and Recovery

- Retry datasets independently with bounded backoff: 1, 5, 15, and 30 minutes.
- Preserve verified staging results so successful datasets are not refetched unnecessarily.
- A missed date is automatically placed ahead of the current date on worker startup.
- Worker restart resumes non-terminal runs using `sync_runs` state.
- Deadline exhaustion sets `partial` or `failed`; it never sets `published`.
- Re-running a published date creates a new versioned run and republishes only after full validation.

## 8. Readiness Contract

Provide a shared read-only readiness function:

```python
get_data_readiness(
    dataset: str,
    as_of: str,
    minimum_status: str = "published",
) -> DataReadiness
```

`DataReadiness` includes status, expected date, published date, coverage counts, source, run ID, and blocking reasons.

The business query service uses this contract before serving freshness-sensitive features. Daily recommendation generation requires:

- canonical daily bars published for the expected settled date
- core index daily data published for the same date
- no unresolved critical quality failure for those datasets

Failure returns HTTP `503` with code `DATA_NOT_READY` and structured blocking reasons. Query handlers must not fetch external data to bypass this gate.

## 9. Operator Interfaces

The status API is read-only and reports:

- current expected settled date
- latest published date per dataset
- run and dataset status
- expected, received, valid, missing, invalid, and published counts
- source and run ID
- last error and next retry time
- whether recommendation generation is allowed

Mutating API sync endpoints return a clear response directing operators to `vibe-trading-sync once` until a separate worker control plane exists. They must not claim success for zero or partial rows.

Alerts are emitted for stale canonical data, partial coverage, source conflicts, repeated empty responses, deadline exhaustion, quarantine growth, and recommendation blocking.

## 10. Historical Audit and Repair

Existing canonical daily bars are treated as provenance-unknown. The repair phase:

1. Creates a verified backup of the current market database.
2. Audits at least the latest 120 settled trading days for coverage, OHLC invariants, duplicates, discontinuities, and cross-source differences.
3. Produces an immutable audit report by date and symbol.
4. Quarantines affected dates or symbols.
5. Rebuilds them from the authoritative historical source through the same staging and quality pipeline.
6. Publishes only verified replacements.
7. Invalidates dependent factor caches, recommendation performance calculations, and materialized dashboard snapshots.

The repair process never silently overwrites records without an audit trail.

## 11. Testing Strategy

Tests must be written before implementation and cover:

- dataset exception does not mark a run complete
- deadline exhaustion produces `partial`
- zero and partial bulk responses do not satisfy coverage
- realtime snapshots never enter canonical daily bars
- malformed OHLC rows are quarantined
- unexplained missing symbols block publication
- source disagreement blocks publication
- verified staging publishes atomically
- failed publication preserves the previous canonical dataset
- worker restart resumes an incomplete run
- stale or degraded readiness blocks recommendations
- query service never invokes external market-data fetchers
- status APIs report partial and failed states truthfully

Existing market sync, market store, recommendation, and opportunity tests remain regression coverage.

## 12. Acceptance Criteria

- The sync worker is the only external-data fetcher and canonical market-data writer.
- The query service reads canonical data only.
- No realtime snapshot is stored as a canonical settled daily bar.
- No exception, timeout, empty result, partial result, or failed quality check can write a published completion state.
- Every new canonical daily row has source and run provenance.
- Current readiness is based on the expected settled trading date and verified coverage.
- Recommendations are deterministically blocked when required datasets are not published.
- Operator status distinguishes success, partial, degraded, and failure.
- Historical suspect data is audited and repaired through the same validation path.

## 13. Non-Goals

- Replacing SQLite with a distributed database.
- Building Kafka, a lakehouse, or a general workflow platform.
- Changing recommendation ranking weights or factor direction logic.
- Adding an HTTP control plane to the sync worker in this phase.
