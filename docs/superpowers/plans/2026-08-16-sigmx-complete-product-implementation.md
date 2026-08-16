# SigmX Complete Product Implementation Plan

> **For Codex:** Execute continuously on `main`. Use test-driven development for behavior changes and verification-before-completion before any completion claim. Do not implement real payment providers.

**Goal:** Fully implement every personal-user requirement in the 2026-08-15 product architecture, replacing shallow page shells with complete Web, Desktop Financial Harness, Data Hub, and operations workflows.

**Architecture:** Split the current Vite renderer into independent Web and Desktop applications in one workspace. Share design tokens, domain types, and typed API clients. Keep the Python service and Electron sidecar, but introduce authoritative cloud-task and Harness-run domain services instead of read-only aggregation. Preserve activation-code commerce and immutable dual-credit ledgers.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind, Vitest/Testing Library, Playwright, Electron, FastAPI, SQLite, pytest, Python SDK.

---

## Task 1: Establish authoritative requirement evidence

**Files:**
- Modify: `docs/superpowers/plans/2026-08-15-total-architecture-evidence-matrix.md`
- Create: `scripts/verify_product_architecture.py`
- Test: `agent/tests/test_product_architecture_verifier.py`

**Steps:**
1. Write failing verifier tests for missing/indirect/complete evidence states.
2. Implement a machine-readable requirement inventory for every numbered section in the source design.
3. Replace the optimistic matrix with current evidence and explicit gaps.
4. Run `pytest agent/tests/test_product_architecture_verifier.py -q`.
5. Commit the verifier and truthful baseline matrix.

## Task 2: Split Web and Desktop build boundaries

**Files:**
- Create: `frontend/apps/web/index.html`, `frontend/apps/web/src/main.tsx`, `frontend/apps/web/src/router.tsx`
- Create: `frontend/apps/desktop/index.html`, `frontend/apps/desktop/src/main.tsx`, `frontend/apps/desktop/src/router.tsx`
- Create: `frontend/packages/ui/src/index.ts`, `frontend/packages/domain/src/index.ts`, `frontend/packages/api-client/src/index.ts`
- Modify: `frontend/package.json`, `frontend/tsconfig*.json`, `frontend/vite.config.ts`
- Modify: `agent/src/api/static_frontend.py`, `desktop/main.js`, `scripts/build-desktop.sh`
- Test: `frontend/src/router/__tests__/productBoundaries.test.tsx`, `desktop/test/product-build.test.js`, `agent/tests/test_static_frontend.py`

**Steps:**
1. Add failing tests proving Web has no Desktop workbench routes and Desktop has no public marketing routes.
2. Add workspace aliases and separate Vite modes/build outputs (`dist/web`, `dist/desktop`).
3. Move route composition into the two application entries while initially reusing existing pages.
4. Serve the selected build explicitly in cloud and desktop modes.
5. Make Electron load the Desktop artifact only.
6. Run frontend, backend static-serving, and Electron boundary tests.
7. Commit the independent build boundary.

## Task 3: Create the shared professional financial design system

**Files:**
- Create: `frontend/packages/ui/src/tokens.css`
- Create: `frontend/packages/ui/src/components/{AppShell,DataTable,DataStatus,EmptyState,ErrorState,MetricStrip,Panel,Timeline}.tsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/packages/ui/src/components/__tests__/*.test.tsx`

**Steps:**
1. Write accessibility and state-contract tests for shared primitives.
2. Implement terminal-grade typography, color, density, focus, status, table, chart, and responsive tokens.
3. Implement complete loading/empty/error/degraded/permission states.
4. Add a component showcase route available only in development.
5. Run UI tests and visual browser snapshots.
6. Commit the shared system.

## Task 4: Complete public discovery domain and search

**Files:**
- Modify: `agent/src/product/public_research.py`, `agent/src/api/public_product_routes.py`
- Create: `agent/src/product/query_intent.py`, `agent/src/product/instrument_profile.py`
- Modify: `frontend/src/pages/public/{LandingPage,PublicSearchPage,PublicInstrumentPage,PublicReportPage}.tsx`
- Modify: `frontend/src/lib/productApi.ts`
- Test: `agent/tests/test_public_discovery.py`, `agent/tests/test_query_intent.py`
- Test: `frontend/src/pages/public/__tests__/PublicDiscovery.test.tsx`

**Steps:**
1. Add failing tests for code/name, structured screening, ETF/LOF, market questions, and docs intent.
2. Implement deterministic intent parsing with explainable conditions and safe fallback.
3. Add stock/fund profile DTOs containing quotes, valuation, finance, flows, events, risk, summary, source/version/quality.
4. Implement saved-query, cloud-watchlist, share, and Desktop-handoff actions.
5. Rebuild all four pages with shared data-state components and meaningful information hierarchy.
6. Run backend, frontend, and browser flow tests.
7. Commit the complete discovery vertical slice.

## Task 5: Complete Web personal research cockpit

**Files:**
- Create: `agent/src/product/cloud_tasks.py`, `agent/src/product/query_history.py`, `agent/src/product/device_presence.py`
- Modify: `agent/src/product/store.py`, `agent/src/api/product_routes.py`
- Modify: `frontend/src/pages/portal/MePage.tsx`
- Create: `frontend/src/components/portal/{TodayOverview,CloudTaskCenter,DesktopPresence,SavedQueryWorkspace,CloudReportLibrary}.tsx`
- Test: `agent/tests/test_cloud_tasks.py`, `agent/tests/test_query_history.py`, `agent/tests/test_device_presence.py`
- Test: `frontend/src/pages/portal/__tests__/MePage.test.tsx`

**Steps:**
1. Add schema/migration and failing state-machine tests for authoritative CloudTask.
2. Implement queue/run/succeed/fail/cancel with Research Credit reserve/settle/refund.
3. Persist query executions and condition versions.
4. Add device heartbeat/online/last-seen and secure Desktop handoff state.
5. Rebuild `/me` around today, watchlists, queries, reports, tasks, notifications, and Desktop connection.
6. Verify refresh persistence and all exceptional states.
7. Commit the personal cockpit.

## Task 6: Complete account and activation-code commerce

**Files:**
- Modify: `frontend/src/pages/account/{SubscriptionPage,CreditsPage,DevicesPage,OrdersPage,CloudAccountPage}.tsx`
- Modify: `frontend/src/pages/Account.tsx`
- Modify: `agent/src/product/{commerce,credits,devices}.py`, `agent/src/api/product_routes.py`
- Test: matching backend and frontend account tests

**Steps:**
1. Add tests for plan comparison, entitlement details, lot expiry, ledger filtering, activation redemption, order lifecycle, session/device revocation.
2. Implement missing API projections and safe account operations.
3. Replace thin account cards with navigable detail workflows.
4. Keep real payment adapters disabled and absent from UI.
5. Run account end-to-end tests.
6. Commit the account closure.

## Task 7: Implement authoritative Harness Run storage

**Files:**
- Create: `agent/src/harness/store.py`, `agent/src/harness/service.py`, `agent/src/harness/events.py`
- Modify: `agent/src/harness/{models,runs,context,registry}.py`, `agent/src/api/harness_routes.py`
- Modify producers in session, swarm, AlphaForge, fund arbitrage, backtest, and scheduled analysis modules
- Test: `agent/tests/test_harness_store.py`, `agent/tests/test_harness_service.py`, `agent/tests/test_harness_producer_integrations.py`

**Steps:**
1. Write failing persistence/lifecycle/idempotency tests.
2. Add versioned schema for Run, Step, ToolCall, Evidence, Artifact, Cost, Degradation, GovernanceEvent.
3. Implement start/update/finish/fail/cancel/retry/clone APIs.
4. Instrument every research producer to write authoritative events.
5. Retain legacy adapters only for migration, visibly marked legacy.
6. Run integration tests proving all producer types appear in one run list.
7. Commit the unified runtime domain.

## Task 8: Build the complete Desktop Financial Harness UI

**Files:**
- Create pages under `frontend/apps/desktop/src/pages/{Today,Research,Market,Quant,Tracking,Runs,Assets,Cloud,Settings}`
- Create components under `frontend/apps/desktop/src/components/{workspace,runs,evidence,context,governance}`
- Modify: `frontend/apps/desktop/src/router.tsx`
- Test: corresponding Desktop component and route tests
- E2E: `frontend/e2e/desktop-harness.spec.ts`

**Steps:**
1. Add route and workflow tests for all nine top-level destinations.
2. Implement resizable three-pane research workspace.
3. Implement unified run list/detail, timeline, evidence, cost, degradation, retry, clone, continue, export.
4. Rehouse existing market, quant, tracking, and settings capabilities in the new IA.
5. Implement Standalone/Connected state and offline degradation.
6. Persist and restore the last workspace safely.
7. Run Electron-connected browser and packaged smoke tests.
8. Commit the complete Desktop UI.

## Task 9: Complete Data Hub quality and billing contracts

**Files:**
- Create: `agent/src/product/data_quality.py`, `agent/src/product/source_normalization.py`
- Modify: `agent/src/product/{datahub_catalog,datahub_contracts,datahub_gateway}.py`
- Modify Data Hub response middleware/routes
- Test: `agent/tests/test_datahub_quality.py`, `agent/tests/test_datahub_contracts.py`, `agent/tests/test_datahub_gateway.py`

**Steps:**
1. Add contract tests for sources, trade date, adjustment, version, freshness, quality flags, partial results, and fallbacks.
2. Implement normalization and quality metadata on every catalog endpoint.
3. Verify permission, row/history/rate constraints and preflight maximum cost.
4. Verify actual-result settlement, zero charge on service failure, and explicit partial charging.
5. Add cost/quality observability aggregates.
6. Commit the completed gateway contract.

## Task 10: Complete Python SDK

**Files:**
- Modify: `datahub-python/src/sigmx_datahub/{client,models,exceptions}.py`
- Create: `datahub-python/src/sigmx_datahub/pagination.py`
- Modify: `datahub-python/README.md`, examples and package metadata
- Test: `datahub-python/tests/*`

**Steps:**
1. Add failing tests for auth, retries, timeout, paging, typed errors, quality metadata, and credit headers.
2. Implement sync client contracts and pagination helpers.
3. Add executable examples for each endpoint group.
4. Build wheel/sdist and test installation in a clean environment.
5. Commit the SDK release candidate.

## Task 11: Split and complete the Data Hub console

**Files:**
- Replace: `frontend/src/pages/account/DataHubConsolePage.tsx`
- Create: `frontend/src/pages/account/datahub/{Overview,Credentials,Catalog,Debugger,Usage,Logs,Budgets,SdkDocs,Credits}.tsx`
- Modify Web router and Account navigation
- Test: corresponding page tests
- E2E: `frontend/e2e/datahub-console.spec.ts`

**Steps:**
1. Add navigation and full workflow tests.
2. Implement overview trends and error summaries.
3. Implement credential/security flows.
4. Implement schema-driven catalog and debugger with cost estimation.
5. Implement usage/log/budget analysis and exports.
6. Implement SDK onboarding and credits workflow.
7. Run responsive browser tests.
8. Commit the complete developer console.

## Task 12: Complete personal operations console

**Files:**
- Create: `agent/src/product/operations.py`, `agent/src/product/audit.py`
- Modify: `agent/src/api/product_routes.py`, `agent/src/product/store.py`
- Replace: `frontend/src/pages/admin/OperationsPage.tsx`
- Create: `frontend/src/pages/admin/operations/{Users,Products,Orders,Codes,Credits,Devices,Endpoints,DataQuality,Content,Metrics,Audit}.tsx`
- Test: backend/admin frontend tests and `frontend/e2e/operations.spec.ts`

**Steps:**
1. Add role, audit, and operation contract tests.
2. Implement user/product/order/code/credit/device administration.
3. Implement endpoint pricing and quality operations.
4. Implement themes, sample queries, reports, and homepage content operations.
5. Implement funnel, activation, retention, engagement, upgrade intent, sharing, consumption, and margin metrics.
6. Require reason and immutable audit record for every write.
7. Run admin authorization and browser workflows.
8. Commit operations completion.

## Task 13: End-to-end product loops and observability

**Files:**
- Create/modify: `frontend/e2e/{web-acquisition,web-desktop-handoff,datahub-billing}.spec.ts`
- Modify: funnel, logging, metrics, and health modules
- Create: `scripts/product_smoke.ps1`, `scripts/product_smoke.sh`

**Steps:**
1. Test Web discovery→registration→saved asset.
2. Test Web research→secure handoff→Desktop continued run.
3. Test credential→Data Hub call→quality metadata→Data Credit settlement→console log.
4. Add correlation IDs and product health checks.
5. Commit cross-product closure.

## Task 14: Packaging, deployment, and strict completion audit

**Files:**
- Modify deployment compose/Nginx/build scripts and `desktop/package.json`
- Modify: `docs/superpowers/plans/2026-08-15-total-architecture-evidence-matrix.md`
- Create: `docs/superpowers/plans/2026-08-16-complete-product-verification.md`

**Steps:**
1. Run all Python, frontend, SDK, Electron, and architecture verifier tests.
2. Build Web-only production assets and confirm Desktop route/code exclusion.
3. Build Desktop installer and confirm public Web route/code exclusion.
4. Render and inspect every core page at desktop and responsive widths.
5. Deploy cloud API, Web, Data Hub, worker/scheduler, and migrations.
6. Run production smoke and billing probes without exposing secrets.
7. Update the evidence matrix only from direct evidence.
8. If any requirement is missing or indirect, continue implementation.
9. Commit and push the verified production release.
