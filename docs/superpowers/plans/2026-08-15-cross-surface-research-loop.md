# Cross-Surface Research Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a personal user hand a saved Web query or instrument to Desktop through a one-time safe task, then deliberately publish a redacted immutable report snapshot back to Web.

**Architecture:** The cloud product store owns short-lived handoff tickets whose plaintext token is shown once and whose hash is stored. Electron only accepts the `sigmx://research/<token>` allowlisted shape and forwards the opaque token to the renderer; Desktop consumes it once through the authenticated cloud API and turns the returned safe prompt/symbol into local research context. Existing report snapshots remain the only public output and accept only user-entered title/summary, never local files or full reports.

**Tech Stack:** FastAPI, SQLite, React, TypeScript, Electron, pytest, Vitest, Node test runner.

## Global Constraints

- Personal `user_id` ownership only; no organization fields or shared task access.
- Ticket lifetime is at most 10 minutes, plaintext is never persisted, and successful consumption is one-time.
- Allowed payload kinds are `saved_query`, `instrument`, and `similar_query`; payload contains only query text, public symbol, and public result references.
- Deep links never contain JWT, refresh token, Data Hub Credential, filesystem path, holdings, or report content.
- Desktop keeps private research local; publishing requires an explicit user action and uploads only title plus redacted summary.
- No real-trading execution or broker action is introduced.

---

### Task 1: Cloud handoff tickets

**Files:** Create `agent/src/product/research_handoffs.py`; modify `agent/src/product/store.py`, `agent/src/api/product_routes.py`; test `agent/tests/test_research_handoffs.py`.

**Interfaces:** Produces `ResearchHandoffService.create(user_id, kind, payload)` and `consume(user_id, plaintext)` plus `POST /api/cloud/handoffs` and `POST /api/cloud/handoffs/{token}/consume`.

- [x] Write failing tests proving owner isolation, payload allowlist/redaction, ten-minute expiry, hashed storage, and one-time consumption.
- [x] Run `python -m pytest tests/test_research_handoffs.py -q` and confirm failure because the service is absent.
- [x] Add schema v9 `research_handoffs`, domain service, request/response models, and authenticated routes.
- [x] Run focused product tests and confirm pass.
- [x] Commit `feat(cloud): add one-time research handoffs`.

### Task 2: Web continuation actions

**Files:** Modify `frontend/src/lib/cloudResearchApi.ts`, `frontend/src/pages/portal/MePage.tsx`, `frontend/src/pages/public/PublicInstrumentPage.tsx`; test corresponding page/API tests.

**Interfaces:** Consumes `createHandoff(kind, payload)` and opens only the returned `sigmx://research/<token>` URL.

- [x] Write failing tests for “Desktop 继续研究” on saved queries/instruments and download fallback when protocol launch is unavailable.
- [x] Run focused Vitest files and confirm RED.
- [x] Implement explicit handoff creation buttons without embedding research data in the URI.
- [x] Run focused tests and confirm GREEN.
- [x] Commit `feat(web): hand research tasks to desktop`.

### Task 3: Electron protocol allowlist and Desktop consumption

**Files:** Modify `desktop/main.js`, `desktop/preload.js`, `frontend/src/hooks/useAuthState.ts`; create `frontend/src/lib/researchHandoff.ts`; test Node protocol parser and Vitest consumer.

**Interfaces:** Produces `parseResearchDeepLink(url)` in Electron and `consumePendingResearchHandoff()` in the renderer.

- [x] Write failing tests rejecting foreign schemes, extra path/query data, invalid token shapes, and accepting one opaque ticket.
- [x] Implement default-protocol registration, single-instance forwarding, pending ticket IPC, and renderer consumption after Connected authentication.
- [x] Route a consumed saved query to `/agent` with local in-memory state; never persist the ticket or payload.
- [x] Run Node/Vitest tests and confirm pass.
- [x] Commit `feat(desktop): consume safe research handoffs`.

### Task 4: Explicit redacted report publishing

**Files:** Create `frontend/src/components/harness/PublishReportSnapshot.tsx`; modify relevant Desktop report page and `cloudResearchApi.ts`; test component and cloud API routes.

**Interfaces:** Consumes existing `POST /api/cloud/reports` with `{title, summary}` and returns immutable public `slug`.

- [x] Write failing tests proving preview, explicit confirmation, character limits, no file/path fields, public link, and revoke state.
- [x] Implement the publish dialog from a user-selected summary only.
- [x] Run focused backend/frontend tests and confirm pass.
- [x] Commit `feat(reports): publish redacted web snapshots`.

### Task 5: Reconciliation and verification

- [x] Run all backend product/Harness tests, all frontend tests, Electron parser tests, production build, and `git diff --check`.
- [x] Scan deep links and API models for secrets, paths, holdings, broker fields, and non-personal ownership.
- [x] Update the total architecture spec with concrete APIs and route behavior.
- [x] Commit `docs(product): record cross-surface research loop`.
