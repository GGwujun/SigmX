# A-Stock Data Quality and Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the a-stock-data integration accurate, testable, complete for SigmX consumers, and reliably publish verified local batches to the production query service.

**Architecture:** Treat the upstream Markdown skill as a response-contract reference, not a runtime dependency. Provider adapters return normalized nullable records; market-sync validates and exports immutable run manifests; data-sync uploads idempotent chunks; the server stages and atomically commits a complete run while business queries continue reading the previous published data until commit succeeds.

**Tech Stack:** Python 3.13, pytest, FastAPI/Pydantic, SQLite, urllib/requests, Docker Compose.

## Global Constraints

- Work directly on the current `main` branch; do not create a branch or worktree.
- Preserve the separate `market-sync` and `data-sync` containers on the same host with a shared volume.
- Production may receive verified data but must never call external market-data providers.
- Missing provider fields are `NULL`, never fabricated numeric zeroes.
- All behavior changes follow red-green-refactor and receive regression tests.
- Business pages are unchanged; only data acquisition, storage, delivery, operational status, and tests are in scope.

---

### Task 1: Provider contract regression tests

**Files:**
- Create: `agent/tests/test_astock_client.py`
- Modify: `agent/src/data/astock_client.py`

**Interfaces:**
- Consumes: upstream V3.4 response shapes captured as local fixtures.
- Produces: normalized adapter functions returning JSON/SQLite-safe dictionaries.

- [ ] Write failing tests for direct-list stock news, Baidu list/dict response variants, THS heat fields, nullable hot-reason fields, V3.4 lockup fields, and duplicate public function names.
- [ ] Run `python -m pytest agent/tests/test_astock_client.py -q` and confirm failures match the reproduced defects.
- [ ] Remove duplicate definitions and implement minimal parsers that satisfy the contracts.
- [ ] Add missing production-relevant upstream adapters: reports/PDF metadata, daily/seat dragon-tiger, industry comparison, stock info, announcement backup, hot concept/rank.
- [ ] Re-run the adapter tests and commit the independently working adapter layer.

### Task 2: Storage semantics and atomic dataset replacement

**Files:**
- Modify: `agent/tests/test_market_store.py`
- Modify: `agent/src/data/market_store.py`

**Interfaces:**
- Consumes: normalized nullable adapter records.
- Produces: `replace_option_chain(...)`, source-aware fund-flow rows, V3.4 lockup fields, and persistent dataset cursors.

- [ ] Write failing tests proving THS tags serialize, fund-flow backup retains `net_amount`, option months/call-put batches coexist, and lockup type/ratio/available shares survive storage.
- [ ] Run the new tests and confirm the old implementation fails for each semantic defect.
- [ ] Extend schemas/upserts without preserving the incorrect test-only schema behavior.
- [ ] Add persistent rotating cursors keyed by dataset so bounded per-code jobs eventually cover the full universe.
- [ ] Re-run store and migration tests, then commit.

### Task 3: Sync coverage, fallback routing, and scheduling

**Files:**
- Modify: `agent/tests/test_market_sync.py`
- Modify: `agent/tests/test_market_sync_worker.py`
- Modify: `agent/src/data/market_sync.py`
- Modify: `agent/src/data/market_sync_worker.py`

**Interfaces:**
- Consumes: adapter functions and dataset cursors.
- Produces: explicit dataset results with row counts, source, freshness, status, and blocking reasons.

- [ ] Write failing tests for fallback activation, cursor rotation, complete option aggregation, and recommendation-slot datasets.
- [ ] Confirm failures before implementation.
- [ ] Route primary failures to independent backup providers and distinguish unavailable from valid-empty responses.
- [ ] Move realtime hotspot, pools, heat, northbound, and telegraph datasets into intraday snapshots while retaining post-close persistence.
- [ ] Add 09:26 and 14:29 readiness-oriented slots without adding recommendation generation times.
- [ ] Ensure expensive bounded per-code jobs honor a deadline and rotate across the universe.
- [ ] Re-run sync/worker tests and commit.

### Task 4: Per-dataset quality policies and immutable outbox

**Files:**
- Modify: `agent/tests/test_market_quality.py`
- Modify: `agent/tests/test_market_sync_worker.py`
- Modify: `agent/src/data/market_quality.py`
- Modify: `agent/src/data/market_store.py`
- Modify: `agent/src/data/market_sync_worker.py`

**Interfaces:**
- Produces: `manifest.json` plus compressed JSONL chunks under `/data/outbox/{run_id}`.

- [ ] Write failing tests for required-field ratios, valid-empty policy, stale snapshots, dataset criticality, manifest hashes, and quarantine behavior.
- [ ] Implement policy tiers: recommendation-critical, post-close-core, and enrichment.
- [ ] Generate the outbox only from a verified shadow snapshot and include schema version, source, row count, date range, null ratios, and SHA-256.
- [ ] Do not mark an entire 43-dataset run healthy merely because a failing adapter returned zero.
- [ ] Re-run quality/worker tests and commit.

### Task 5: Idempotent run/chunk/commit delivery

**Files:**
- Create: `agent/src/data/market_ingest.py`
- Create: `agent/tests/test_market_ingest.py`
- Modify: `agent/src/api/market_sync_routes.py`
- Modify: `agent/tests/test_market_sync_api.py`
- Rewrite: `data-sync/app.py`
- Create: `data-sync/test_app.py`

**Interfaces:**
- Produces server endpoints `POST /data-ingest/runs`, `PUT /data-ingest/runs/{run_id}/chunks/{dataset}/{chunk_no}`, `POST /data-ingest/runs/{run_id}/commit`, and `GET /data-ingest/runs/{run_id}`.

- [ ] Write failing authentication, idempotency, checksum, missing-chunk, duplicate-chunk, retry, and atomic-commit tests.
- [ ] Keep provider-fetch endpoints disabled while adding a separately authenticated receive-only API.
- [ ] Stage chunks by run ID and apply target-table mutations in one SQLite transaction.
- [ ] Mark the local outbox delivered only after a successful server ACK.
- [ ] Re-run API and data-sync tests and commit.

### Task 6: Deployment topology and end-to-end verification

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.local.yml`
- Modify: `README.md`

**Interfaces:**
- Local compose: market-sync and data-sync share `/data`; production compose starts only the business/query service unless an explicit sync profile is enabled.

- [ ] Update Compose so the two local containers share the same bind-mounted data root and production does not start provider sync by default.
- [ ] Document schedules, run states, alert thresholds, recovery, token rotation, and backfill isolation.
- [ ] Run focused pytest suites, compile checks, compose config validation, `git diff --check`, and the existing recommendation regression suite.
- [ ] Review `git diff` against this plan, run GitNexus change detection if the CLI becomes available, and commit verified changes.
