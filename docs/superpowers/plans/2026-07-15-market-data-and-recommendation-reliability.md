# Market Data and Recommendation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make acquisition and synchronization logic deployable and make daily recommendations depend only on validated, auditable local evidence.

**Architecture:** Add semantic dataset contracts at the acquisition boundary, publish immutable quality manifests with SQLite snapshots, and enforce evidence readiness in the recommendation path. Keep `market-sync`, `data-sync`, and the business query process independent.

**Tech Stack:** Python 3, SQLite, FastAPI, urllib, pytest.

## Global Constraints

- Do not deploy or mutate the production server in this change.
- Do not add recommendation-time external market-data calls.
- Do not preserve invalid legacy behavior merely for compatibility.
- Modify only data acquisition/synchronization internals and daily recommendation behavior; no unrelated page module changes.

---

### Task 1: Semantic dataset contracts

**Files:**
- Create: `agent/src/data/dataset_contracts.py`
- Modify: `agent/src/data/astock_client.py`
- Modify: `agent/src/data/market_sync.py`
- Test: `agent/tests/test_dataset_contracts.py`
- Test: `agent/tests/test_astock_client.py`

**Interfaces:**
- Produces: `validate_dataset(name, rows, *, trade_date=None) -> ValidationResult` and `run_provider_chain(name, providers, *, trade_date=None) -> ProviderResult`.
- Consumes: normalized dictionaries returned by `astock_client`.

- [ ] Write failing tests for empty-but-truthy Baidu data, zero-count EPS rows, invalid northbound fields, stale dates, duplicates, and provider fallback diagnostics.
- [ ] Run `pytest agent/tests/test_dataset_contracts.py agent/tests/test_astock_client.py -q` and confirm the new tests fail.
- [ ] Implement immutable validation/provider results and named semantic contracts.
- [ ] Wire recommendation-relevant sync tasks to provider chains and persist source diagnostics without fabricating missing fields.
- [ ] Re-run the focused tests and confirm they pass.

### Task 2: Event-driven verified snapshots

**Files:**
- Modify: `data-sync/app.py`
- Modify: `agent/src/data/data_ingest_server.py`
- Modify: `agent/src/data/market_store.py`
- Test: `agent/tests/test_data_sync_client.py`
- Test: `agent/tests/test_data_ingest.py`

**Interfaces:**
- Produces: `PublishedRunWatcher.next_snapshot()` semantics based on unseen published `run_id`; receiver verifies the embedded run before atomic replacement.
- Consumes: `sync_runs.status='published'` and dataset validation metadata.

- [ ] Write failing tests showing a newly published run pushes immediately, repeated run IDs are skipped, pending runs are rejected, and an embedded manifest mismatch cannot replace the database.
- [ ] Run focused sync/ingest tests and confirm failures.
- [ ] Replace minute equality triggering with condition polling over published run identity while retaining configured deadline diagnostics.
- [ ] Add receiver validation of embedded run ID, trade date, and publication status before atomic replace.
- [ ] Re-run focused sync/ingest tests.

### Task 3: Local recommendation evidence

**Files:**
- Modify: `agent/src/data/alpha_signals.py`
- Modify: `agent/src/api/opportunity_routes.py`
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`
- Test: `agent/tests/test_alpha_signals.py`

**Interfaces:**
- Produces: local board-member peer lookup, explicit event mapping requirement, production guardrail application, evidence coverage, and deterministic AI-degradation behavior.
- Consumes: validated SQLite tables and candidate dictionaries.

- [ ] Write failing tests proving peer lookup makes no network call, unmapped events produce no candidate, guardrails alter actual reviewed-candidate scores, missing evidence is rejected, and AI failure does not remove deterministic candidates.
- [ ] Run focused recommendation tests and confirm failures.
- [ ] Replace mootdx/hard-coded peer selection with persisted board membership and liquidity-ranked local fallback.
- [ ] Require explicit symbol/sector event attribution.
- [ ] Apply attribution guardrails before deterministic scoring and renormalize scoring over available evidence.
- [ ] Make AI review optional and bounded after deterministic eligibility.
- [ ] Re-run focused recommendation tests.

### Task 4: Forward evidence and promotion gate

**Files:**
- Modify: `agent/src/api/daily_recommendation_routes.py`
- Test: `agent/tests/test_daily_recommendation_routes.py`

**Interfaces:**
- Produces: versioned forward-performance summary and `promotion_status` containing evidence count, thresholds, and decision.

- [ ] Write failing tests for insufficient samples, negative expectancy rejection, and positive out-of-sample promotion.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement sample-size-aware metrics and promotion decision without claiming accuracy for insufficient evidence.
- [ ] Re-run focused tests.

### Task 5: Regression verification

**Files:**
- Verify all files changed above.

- [ ] Run the focused data/sync/recommendation suites.
- [ ] Run the complete backend test suite appropriate to the changed modules.
- [ ] Run GitNexus `detect_changes` against `main`; if the runner remains unavailable, record the exact failure and perform a static changed-symbol/caller audit.
- [ ] Review `git diff --check`, `git status --short`, and the complete diff before committing.
