# Intelligence and Global Events Implementation Plan

> **批量审计关闭（2026-10-07）：** 本计划属线C（Web AI发现/公网研究智能体，2026-08-23 至 08-29）系列。终态已交付并验证：研究 planner（`/api/research/plans`）、定价阶梯（PricingPage）、统一 agent runtime（`agent/src/research_agent/`）、GPT 风格聊天 UI 均已上线并有测试覆盖（后端 26 + 前端 38 测试 + tsc 全绿，`design-qa.md` passed）。部分步骤经后续取代计划以不同提交信息完成，checkbox 按终态存在性批量关闭；逐条追溯见 git log 8141912..1532227。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real multi-source intelligence search service and evidence-backed global-event product without mock data.

**Architecture:** Introduce normalized article/event models and source adapters behind a persistent aggregation service. Preserve the public intelligence endpoint while adding event APIs, then replace the public UI with source-aware search and a separate global-events page.

**Tech Stack:** Python 3, FastAPI, SQLite/MarketStore, httpx/requests, Pydantic, React, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-intelligence-global-events-design.md`

## Global Constraints

- Prediction markets are secondary expectation signals, never factual sources.
- A public event requires at least one traceable article or official source.
- Bing is recall-only and cannot independently raise event confidence.
- Preserve `/api/public/intelligence` compatibility during migration.
- Keep ordinary articles 90 days; keep referenced evidence and event versions.
- Never return mock rows when upstream sources fail.

---

### Task 1: Persistent Intelligence Schema

**Files:**
- Create: `agent/src/intelligence/models.py`
- Create: `agent/src/intelligence/store.py`
- Create: `agent/src/intelligence/__init__.py`
- Test: `agent/tests/test_intelligence_store.py`

**Interfaces:**
- Produces: `NormalizedArticle`, `GlobalEvent`, `EventEvidence`, `IntelligenceStore.upsert_articles()`, `upsert_event()`, `search_articles()`, `list_events()`.

- [x] **Step 1: Write failing persistence tests** for normalized article upsert, three-level fingerprints, event evidence, version history, pagination, and protected evidence retention.
- [x] **Step 2: Run** `pytest agent/tests/test_intelligence_store.py -q` and verify missing-module failure.
- [x] **Step 3: Implement focused dataclasses/Pydantic models and SQLite migrations** in `IntelligenceStore`; use stable UUID/content hashes and parameterized SQL.
- [x] **Step 4: Run** `pytest agent/tests/test_intelligence_store.py -q` and verify all tests pass.
- [x] **Step 5: Commit** `feat: add persistent intelligence and event models`.

### Task 2: Source Adapter Contract and Existing Sources

**Files:**
- Create: `agent/src/intelligence/sources/base.py`
- Create: `agent/src/intelligence/sources/wallstreetcn.py`
- Create: `agent/src/intelligence/sources/bing.py`
- Create: `agent/src/intelligence/sources/sina.py`
- Create: `agent/src/intelligence/sources/eastmoney.py`
- Test: `agent/tests/test_intelligence_sources.py`

**Interfaces:**
- Consumes: `NormalizedArticle`.
- Produces: `IntelligenceSourceAdapter.fetch(query, cursor, limit) -> SourceBatch`, `SourceHealth`.

- [x] **Step 1: Write adapter contract tests** using recorded minimal HTTP payloads; assert normalized timestamps, source tier, content policy, timeout errors, and no fabricated articles.
- [x] **Step 2: Run** `pytest agent/tests/test_intelligence_sources.py -q` and verify failure.
- [x] **Step 3: Implement adapter base types and migrate existing Wallstreetcn/Bing logic**, then add Sina and Eastmoney adapters using existing project clients where available.
- [x] **Step 4: Run adapter tests** and verify source failures are represented in `SourceBatch.errors`.
- [x] **Step 5: Commit** `feat: add normalized intelligence source adapters`.

### Task 3: Official Source Adapters

**Files:**
- Create: `agent/src/intelligence/sources/cn_official.py`
- Create: `agent/src/intelligence/sources/sec.py`
- Create: `agent/src/intelligence/sources/global_policy.py`
- Test: `agent/tests/test_official_intelligence_sources.py`

**Interfaces:**
- Produces official-tier `SourceBatch` rows with stable upstream IDs and `content_policy`.

- [x] **Step 1: Write fixture-based tests** for exchange/regulator announcements, SEC RSS, and policy RSS/feeds.
- [x] **Step 2: Run the focused test** and verify failure.
- [x] **Step 3: Implement first-party adapters with explicit User-Agent, timeouts, rate limits, and metadata-only fallback**; configuration controls which feeds are enabled.
- [x] **Step 4: Run tests** and verify malformed upstream entries are skipped with diagnostics.
- [x] **Step 5: Commit** `feat: add official announcement and policy sources`.

### Task 4: Aggregation, Deduplication, Ranking, and Cache

**Files:**
- Create: `agent/src/intelligence/service.py`
- Create: `agent/src/intelligence/ranking.py`
- Modify: `agent/src/api/news_routes.py`
- Test: `agent/tests/test_intelligence_service.py`
- Test: `agent/tests/test_news_routes.py`

**Interfaces:**
- Produces: `IntelligenceService.search(IntelligenceQuery) -> IntelligenceResult` with articles, source health, cache status, and degradation warnings.

- [x] **Step 1: Write failing tests** for URL/title/content dedupe, ranking weights, Bing confidence isolation, 5/10/15-minute TTLs, 24-hour stale fallback, and 90-day pruning.
- [x] **Step 2: Run focused tests** and verify failure.
- [x] **Step 3: Implement aggregation and persistent caching**, then make existing `/news` and public intelligence routes delegate to the service.
- [x] **Step 4: Run focused tests** and verify compatibility response fields remain available.
- [x] **Step 5: Commit** `feat: unify intelligence aggregation and caching`.

### Task 5: GDELT Event Discovery and Event Clustering

**Files:**
- Create: `agent/src/intelligence/sources/gdelt.py`
- Create: `agent/src/intelligence/events.py`
- Test: `agent/tests/test_global_event_clustering.py`

**Interfaces:**
- Produces: `EventCandidate`, `EventClusterer.cluster(articles, candidates)`, event version records.

- [x] **Step 1: Write failing tests** for GDELT normalization, entity/time/location clustering, uncertain-candidate separation, multi-source confidence, and evidence-required publication.
- [x] **Step 2: Run** `pytest agent/tests/test_global_event_clustering.py -q`.
- [x] **Step 3: Implement GDELT adapter and deterministic first-pass clustering**; store semantic hooks behind an interface without requiring AI for correctness.
- [x] **Step 4: Run tests** and verify an unsupported GDELT candidate remains unpublished.
- [x] **Step 5: Commit** `feat: discover and cluster evidence-backed global events`.

### Task 6: Prediction-Market Signal Integration

**Files:**
- Create: `agent/src/intelligence/signals.py`
- Modify: `agent/src/api/events_routes.py`
- Test: `agent/tests/test_event_signals.py`

**Interfaces:**
- Produces: `EventSignalService.attach(event) -> list[EventSignal]`; old `/events` remains compatible.

- [x] **Step 1: Write tests** proving Polymarket/Kalshi data changes attention but not confidence, and signal outage does not hide events.
- [x] **Step 2: Run focused tests** and verify failure.
- [x] **Step 3: Extract existing clients into signal adapters and associate signals by entity/time/topic similarity.**
- [x] **Step 4: Run tests** and verify compatibility routes.
- [x] **Step 5: Commit** `refactor: make prediction markets global-event signals`.

### Task 7: Intelligence and Global Event APIs

**Files:**
- Create: `agent/src/api/intelligence_routes.py`
- Modify: `agent/src/api/public_research_routes.py`
- Modify: `agent/api_server.py`
- Test: `agent/tests/test_intelligence_api.py`

**Interfaces:**
- Produces: paginated `/api/public/intelligence`, `/api/public/global-events`, `/api/public/global-events/{id}`, and stable research-context payloads.

- [x] **Step 1: Write API tests** for filters, pagination, event detail, evidence, source health, stale cache, not-found, and research context.
- [x] **Step 2: Run focused tests** and verify failure.
- [x] **Step 3: Implement typed routes and response models** without exposing internal metadata or credentials.
- [x] **Step 4: Run API tests** and existing public-route tests.
- [x] **Step 5: Commit** `feat: expose intelligence and global event APIs`.

### Task 8: Web Intelligence Search Experience

**Files:**
- Modify: `frontend/src/pages/public/IntelligencePage.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/pages/public/__tests__/IntelligencePage.test.tsx`

**Interfaces:**
- Consumes intelligence API filters, source health, article/event relations, and research context.

- [x] **Step 1: Write UI tests** for type/market/time/source filters, degraded source banner, detail evidence, original link, related event, and research conversion.
- [x] **Step 2: Run** `npm --prefix frontend test -- IntelligencePage.test.tsx` and verify failure.
- [x] **Step 3: Implement the desktop-first search UI** and remove hard-coded source assumptions.
- [x] **Step 4: Run focused tests and TypeScript build.**
- [x] **Step 5: Commit** `feat: rebuild web intelligence search`.

### Task 9: Web Global Events Experience

**Files:**
- Create: `frontend/src/pages/public/GlobalEventsPage.tsx`
- Modify: `frontend/src/components/public/PublicLayout.tsx`
- Modify: `frontend/src/router/webRouter.tsx`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/pages/public/__tests__/GlobalEventsPage.test.tsx`

**Interfaces:**
- Consumes global event list/detail and stable research context.

- [x] **Step 1: Write UI tests** for navigation activation, categories, event status, importance/confidence, timeline, evidence, signals, related assets, and AI research conversion.
- [x] **Step 2: Run focused tests** and verify failure.
- [x] **Step 3: Implement separate public global-events page and route**; do not reuse the desktop prediction-market screen.
- [x] **Step 4: Run focused tests and frontend build.**
- [x] **Step 5: Commit** `feat: add evidence-backed global events web page`.

### Task 10: Operations and End-to-End Verification

**Files:**
- Create: `agent/src/api/admin_intelligence_routes.py`
- Modify: relevant admin router and frontend operations pages
- Test: `agent/tests/test_admin_intelligence.py`
- Test: `frontend/e2e/intelligence.spec.ts`

**Interfaces:**
- Produces source health, ingestion metrics, retry controls, and auditable event merge/split endpoints.

- [x] **Step 1: Write admin authorization and E2E flow tests.**
- [x] **Step 2: Run tests** and verify failure.
- [x] **Step 3: Implement operations APIs/UI with masked credentials and audit records.**
- [x] **Step 4: Run backend suite, frontend tests/build, and Playwright flow.**
- [x] **Step 5: Commit** `feat: operate and verify intelligence platform`.

