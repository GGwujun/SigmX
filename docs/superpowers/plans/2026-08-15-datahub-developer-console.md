# Data Hub Developer Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the personal Data Hub self-service loop with request/error logs, per-Credential daily Data Credit budgets and threshold alerts, plus an allowlisted online API debugger.

**Architecture:** Usage audit rows remain the source of truth. A small budget service stores a daily limit per personal Credential, checks authorized cost inside the gateway before credit reservation, and derives 50/80/100 threshold events from settled usage without creating a second counter. Account APIs expose owner-filtered logs/budgets; the browser debugger calls only enabled GET endpoints from the versioned catalog with a user-supplied one-time Credential held in component memory.

**Tech Stack:** FastAPI, SQLite, React, TypeScript, pytest, Vitest.

## Global Constraints

- Personal `user_id` ownership only; Desktop ephemeral sessions cannot be configured as developer budgets.
- Budget is Data Credit spend, not request count, and resets at UTC day boundary.
- A request whose maximum authorized cost would exceed the remaining daily budget fails before credit authorization and does not deduct credits.
- Thresholds are fixed at 50%, 80%, and 100%; each threshold emits at most one in-app event per Credential per UTC day.
- Logs never expose Credential hashes/plaintext, authorization headers, raw response bodies, IP addresses, or query values.
- Debugger accepts enabled catalog GET paths only, keeps the plaintext Credential in React memory, and never saves it.

---

### Task 1: Budget enforcement and threshold events

**Files:** Create `agent/src/product/datahub_budgets.py`; modify `agent/src/product/store.py`, `agent/src/product/datahub_gateway.py`; test `agent/tests/test_datahub_budgets.py`.

- [x] Write failing tests for owner isolation, UTC daily reset, pre-authorization rejection, no credit deduction, and unique 50/80/100 events.
- [x] Add schema v10 budget/event tables and gateway enforcement.
- [x] Run budget and gateway tests; commit `feat(data-hub): enforce credential credit budgets`.

### Task 2: Personal logs and budget APIs

**Files:** Modify `agent/src/api/product_routes.py`; test `agent/tests/test_datahub_console_routes.py`.

- [x] Write failing route tests for owner-filtered paginated logs, error-only filter, budget CRUD, and alert serialization.
- [x] Add `/api/datahub/logs`, `/api/datahub/credentials/{id}/budget`, and `/api/datahub/budget-alerts`.
- [x] Run route tests; commit `feat(api): expose data hub logs and budgets`.

### Task 3: Console UI and online debugger

**Files:** Modify `frontend/src/lib/productApi.ts`, `frontend/src/pages/account/DataHubConsolePage.tsx`; test `frontend/src/pages/account/__tests__/DataHubConsolePage.test.tsx`.

- [x] Write failing UI tests for logs/errors, daily budget, threshold alert, enabled endpoint selection, in-memory Credential, response status/cost headers, and no persistence.
- [x] Implement the console tabs and allowlisted GET debugger.
- [x] Run focused tests and TypeScript checks; commit `feat(web): complete data hub developer console`.

### Task 4: Verification and documentation

- [x] Run relevant backend tests, all frontend tests, production build, secret scan, and `git diff --check`.
- [x] Update total architecture spec with concrete budget/log/debug behavior.
- [x] Commit the console completion record with the concurrency-safe budget closeout.
