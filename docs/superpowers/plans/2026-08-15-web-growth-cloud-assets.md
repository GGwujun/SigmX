# Web Growth and Cloud Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the public Web discovery funnel and real personal cloud assets required by the SigmX total architecture.

**Architecture:** Add a focused `CloudResearchService` over ProductStore-owned SQLite tables for saved queries, cloud watchlists, and report snapshots. Expose authenticated asset APIs and deliberately limited public read APIs; React public pages consume only those APIs while `/me` consumes authenticated assets. Desktop handoff uses a signed, single-use handoff record rather than exposing local tokens.

**Tech Stack:** FastAPI, Pydantic, SQLite, React, TypeScript, Vitest, pytest.

## Global Constraints

- Personal accounts only; every mutable asset is owned directly by `user_id`.
- Public pages return limited real data and never require login before showing value.
- Private files, holdings, model keys, and full local reports are never uploaded implicitly.
- All new behavior follows test-first red/green/refactor.
- No old Data Hub credential or request-quota compatibility path may be restored.

---

### Task 1: Personal cloud research persistence

**Files:**
- Create: `agent/src/product/cloud_research.py`
- Modify: `agent/src/product/store.py`
- Test: `agent/tests/test_cloud_research.py`

**Interfaces:**
- Produces: `CloudResearchService.save_query(user_id, query, result_summary)`, `list_saved_queries(user_id)`, `add_watchlist(user_id, symbol, name)`, `remove_watchlist(user_id, symbol)`, `list_watchlist(user_id)`, `publish_report(user_id, title, summary)`, `get_public_report(slug)`, `revoke_report(user_id, report_id)`.

- [x] Write tests proving owner isolation, deterministic query persistence, watchlist uniqueness, immutable public snapshots, and revoked-report 410 state.
- [x] Run `python -m pytest agent/tests/test_cloud_research.py -q` and confirm failures are caused by the missing service/schema.
- [x] Add schema v7 tables `saved_queries`, `cloud_watchlist`, and `report_snapshots`; implement the service with UUID identifiers and UTC timestamps.
- [x] Re-run the test file and confirm all cases pass.
- [x] Commit with `feat(cloud): add personal research asset store`.

### Task 2: Authenticated cloud asset and public report APIs

**Files:**
- Modify: `agent/src/api/product_routes.py`
- Test: `agent/tests/test_cloud_research_routes.py`

**Interfaces:**
- Produces: `GET/POST /api/cloud/queries`, `GET/POST/DELETE /api/cloud/watchlist`, `GET/POST/DELETE /api/cloud/reports`, and public `GET /api/public/reports/{slug}`.

- [x] Write route tests proving authentication, per-user isolation, validation, report publication, and explicit 410 for revoked snapshots.
- [x] Run `python -m pytest agent/tests/test_cloud_research_routes.py -q` and confirm the new endpoints are absent.
- [x] Add typed request/response models and route handlers delegating all persistence to `CloudResearchService`.
- [x] Re-run route tests and existing `test_product_routes.py`.
- [x] Commit with `feat(api): expose personal cloud research assets`.

### Task 3: Public discovery pages and unified search

Before the frontend, implement the anonymous read boundary:

**Files:**
- Create: `agent/src/product/public_research.py`
- Create: `agent/src/api/public_research_routes.py`
- Modify: `agent/api_server.py`
- Test: `agent/tests/test_public_research.py`
- Test: `agent/tests/test_public_research_routes.py`

**Interfaces:**
- Produces: `GET /api/public/search?q=`, `GET /api/public/stocks/{code}`, and `GET /api/public/funds/{code}` with at most ten delayed, source-labelled results.

- [x] Write service and route tests for code/name search, supported natural-language filters (`低估值`, `高股息`, `小市值`), stock summary, fund summary, empty data, and absence of auth requirements.
- [x] Run both backend test files and confirm failure because the service/routes do not exist.
- [x] Implement read-only queries over `MarketStore`; return only public fields plus `source`, `as_of`, and `is_delayed` metadata.
- [x] Register the public router independently of Data Hub billing routes and re-run the tests.
- [x] Commit with `feat(web): expose limited public research api`.

Then implement the public React pages:

**Files:**
- Create: `frontend/src/pages/public/PublicSearchPage.tsx`
- Create: `frontend/src/pages/public/PublicInstrumentPage.tsx`
- Create: `frontend/src/pages/public/PublicReportPage.tsx`
- Create: `frontend/src/lib/cloudResearchApi.ts`
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/pages/public/__tests__/PublicDiscovery.test.tsx`

**Interfaces:**
- Produces: routes `/query/:id`, `/stock/:code`, `/fund/:code`, `/research/:slug`; homepage search classifies six-digit stock/fund codes and natural-language queries; authenticated users can save a query without losing anonymous input.

- [ ] Write Vitest cases for route rendering, anonymous limited results, save-after-login intent persistence, and revoked report messaging.
- [ ] Run the focused Vitest file and confirm it fails for missing pages/routes.
- [ ] Implement typed API calls, pages, homepage search, and router entries; ensure all pages use `PublicLayout` only.
- [ ] Re-run focused and router/navigation tests.
- [ ] Commit with `feat(web): add public research discovery funnel`.

### Task 4: Replace `/me` planning cards with real cloud assets

**Files:**
- Modify: `frontend/src/pages/portal/MePage.tsx`
- Test: `frontend/src/pages/portal/__tests__/MePage.test.tsx`

**Interfaces:**
- Consumes: cloud queries, watchlist, and reports from Task 2.
- Produces: actionable lists with empty states, remove actions, public report links, and Desktop continuation actions.

- [ ] Write tests that reject the current “规划中” cards and assert real asset rows, empty states, and error isolation.
- [ ] Run the focused test and confirm it fails against the current placeholder page.
- [ ] Load assets with `Promise.allSettled`, render each independently, and remove all “规划中” copy.
- [ ] Re-run the focused test and complete frontend suite.
- [ ] Commit with `feat(web): connect personal cloud workspace`.

### Task 5: Verification and architecture reconciliation

**Files:**
- Modify: `docs/superpowers/specs/2026-08-15-sigmx-product-architecture-design.md`

- [ ] Run backend cloud/product tests and the full frontend Vitest suite.
- [ ] Run the frontend production build and `git diff --check`.
- [ ] Update the total architecture shared-object list to personal-only objects and record the implemented Web routes without changing non-goals.
- [ ] Scan for “规划中” in `/me` and missing required public paths in `router.tsx`.
- [ ] Commit with `docs(product): record web growth completion`.
