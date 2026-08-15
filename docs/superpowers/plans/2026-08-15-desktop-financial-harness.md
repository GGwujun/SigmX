# Desktop Financial Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a single product contract and observable Desktop experience over SigmX's existing research runtimes.

**Architecture:** A new `src/harness` package contains pure descriptors and adapters; it reads existing stores but never becomes a second run store. Product APIs expose normalized state only to authenticated Desktop/device callers. Temporary device-bound Data Hub credentials make Connected mode automatic without restoring legacy auth.

**Tech Stack:** Python, FastAPI, Pydantic, SQLite, React, TypeScript, Electron secure bridge, pytest, Vitest.

## Global Constraints

- Reuse current Session, Goal, Swarm, Core Runner, MarketStore, Tool Registry, and Live Runtime.
- No real-trading `execute` tool is registered.
- Private file content, holdings, broker credentials, and model keys remain local.
- Web routes never load Harness pages or local state.
- Follow test-first red/green/refactor and commit each independently testable task.

---

### Task 1: Harness descriptors and governance registry

**Files:** Create `agent/src/harness/models.py`, `agent/src/harness/registry.py`; test `agent/tests/test_harness_registry.py`.

- [x] Write tests for descriptor validation, stable categories, cost dimensions, confirmation rules, and absence of `execute` tools.
- [x] Confirm RED, implement enums/models and adapters over the existing tool registry, then confirm GREEN.
- [x] Commit `feat(harness): add governed tool registry`.

### Task 2: Context manifest and run adapters

**Files:** Create `agent/src/harness/context.py`, `agent/src/harness/runs.py`; test `agent/tests/test_harness_context.py`, `agent/tests/test_harness_runs.py`.

- [x] Write tests for local-only file references, secret redaction, Session and Swarm normalization, partial adapter failure, evidence and cost mapping.
- [x] Confirm RED, implement pure manifest builder and read-only adapters, then confirm GREEN.
- [x] Commit `feat(harness): normalize research context and runs`.

### Task 3: Desktop Harness API

**Files:** Create `agent/src/api/harness_routes.py`; modify `agent/api_server.py`; test `agent/tests/test_harness_routes.py`.

- [ ] Write API tests for status/tools/runs/context preview, authentication, local fallback, and no secret-bearing fields.
- [ ] Confirm RED, implement routes and register them outside public/product routers, then confirm GREEN.
- [ ] Commit `feat(harness): expose desktop runtime api`.

### Task 4: Automatic short-lived Connected credential

**Files:** Modify `agent/src/product/datahub_credentials.py`, `agent/src/api/product_routes.py`; test `agent/tests/test_desktop_datahub_session.py`.

- [ ] Write tests for 24-hour maximum expiry, device/user ownership, entitlement-limited scopes, automatic prior-session revocation, exclusion from long-term Key limit, and gateway authentication.
- [ ] Confirm RED, add `credential_kind`/`device_id` schema v8 migration and session issuance endpoint, then confirm GREEN.
- [ ] Commit `feat(data-hub): issue device-bound desktop sessions`.

### Task 5: Harness Overview and Connected UX

**Files:** Create `frontend/src/lib/harnessApi.ts`, `frontend/src/components/harness/HarnessOverview.tsx`; modify `frontend/src/pages/Home.tsx`, `frontend/src/pages/Settings.tsx`; test focused component/page files.

- [ ] Write UI tests for mode, source, governance, recent runs, dual credits, partial state, and automatic Connected setup.
- [ ] Confirm RED, implement Overview and replace manual-Key-first Connected UX, then confirm GREEN.
- [ ] Commit `feat(desktop): surface financial harness status`.

### Task 6: Verification and reconciliation

- [ ] Run Harness/Data Hub backend suites, full frontend suite, production build, and `git diff --check`.
- [ ] Prove Browser mode cannot navigate to Harness-only routes and scan for claims of automatic trading.
- [ ] Update total architecture with concrete Harness APIs and implemented Connected flow.
- [ ] Commit `docs(product): record desktop harness completion`.
