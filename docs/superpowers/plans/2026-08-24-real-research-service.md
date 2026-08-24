# Real Research Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace AI discovery, research execution, and research results runtime mock data with persisted, source-attributed service responses.

**Architecture:** Extend the existing FastAPI public-research domain and ProductStore SQLite boundary. Public market discovery remains read-only; authenticated research runs persist a task and evidence-backed result. React consumes one typed client and renders loading, ready, empty, and error states without static fallback.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite, pytest, React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-24-runtime-mock-removal-design.md`

## Global Constraints

- Runtime failures must render an error or empty state, never static business data.
- Market and research responses include source and observation time.
- Research tasks require authentication and persist across refreshes.
- LLM text cannot invent missing numeric evidence.
- Test mocks remain allowed under test files only.

---

### Task 1: Runtime Mock Guard

**Files:**
- Create: `tools/check_web_runtime_mocks.py`
- Create: `agent/tests/test_web_runtime_mock_guard.py`

**Interfaces:**
- Consumes: repository path passed to `scan_runtime_mocks(root: Path)`.
- Produces: `list[Violation]` with `path`, `line`, and `reason`.

- [x] **Step 1: Write the failing test**

```python
def test_detects_runtime_demo_copy_but_ignores_tests(tmp_path):
    (tmp_path / "frontend/src/pages").mkdir(parents=True)
    (tmp_path / "frontend/src/pages/Page.tsx").write_text('const rows = [{name: "虚构公司"}];\n演示数据', encoding="utf-8")
    violations = scan_runtime_mocks(tmp_path)
    assert {item.reason for item in violations} == {"demo-marker", "page-business-array"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest agent/tests/test_web_runtime_mock_guard.py -q`
Expected: FAIL because `tools.check_web_runtime_mocks` does not exist.

- [x] **Step 3: Implement scanner and CLI**

Scan production `.ts/.tsx` files outside `__tests__`, flag explicit demo markers and exported page-level business fixtures. Support an allowlist for navigation/options/documentation metadata.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest agent/tests/test_web_runtime_mock_guard.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/check_web_runtime_mocks.py agent/tests/test_web_runtime_mock_guard.py
git commit -m "test: guard against web runtime mock data"
```

### Task 2: Real Market Discovery API

**Files:**
- Modify: `agent/src/product/public_research.py`
- Modify: `agent/src/api/public_research_routes.py`
- Test: `agent/tests/test_public_research_api.py`

**Interfaces:**
- Produces: `GET /api/public/discovery` → `{as_of, source, is_delayed, market_status, metrics, templates}`.
- Each metric is `{key, label, value, change, unit, quality}`.
- Each template is `{id, label, description, prompt, data_domains}`.

- [x] **Step 1: Write failing API tests**

```python
def test_discovery_has_source_time_and_no_fabricated_fallback(client, monkeypatch):
    response = client.get("/api/public/discovery")
    assert response.status_code == 200
    body = response.json()
    assert body["source"]
    assert body["as_of"]
    assert all(item["quality"] in {"fresh", "delayed", "unavailable"} for item in body["metrics"])
```

- [x] **Step 2: Verify failure**

Run: `python -m pytest agent/tests/test_public_research_api.py -q`
Expected: FAIL with 404 for `/api/public/discovery`.

- [x] **Step 3: Implement discovery DTO and service aggregation**

Reuse latest-trade-date, index, breadth, and fund-summary store queries. If a source is unavailable, return a metric with `quality="unavailable"` and `value=None`; do not insert a numeric default.

- [x] **Step 4: Verify API tests**

Run: `python -m pytest agent/tests/test_public_research_api.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add agent/src/product/public_research.py agent/src/api/public_research_routes.py agent/tests/test_public_research_api.py
git commit -m "feat: serve real public market discovery"
```

### Task 3: Persisted Research Task and Result API

**Files:**
- Create: `agent/src/product/research_tasks.py`
- Create: `agent/src/api/research_task_routes.py`
- Modify: `agent/src/product/store.py`
- Modify: `agent/api_server.py`
- Create: `agent/tests/test_research_task_api.py`

**Interfaces:**
- `POST /api/research/tasks` body `{question, template_id?, scope, constraints, idempotency_key}`.
- `GET /api/research/tasks/{id}` returns task state and confirmed steps.
- `GET /api/research/tasks/{id}/result` returns persisted summary, candidates, evidence, risks, `source`, and `as_of`.
- `POST /api/research/tasks/{id}/cancel` cancels queued/running tasks.

- [x] **Step 1: Write failing task lifecycle tests**

```python
def test_research_task_persists_real_result(client, auth_headers, seeded_market_store):
    created = client.post("/api/research/tasks", headers=auth_headers, json={
        "question": "低估值高股息", "scope": {"market": "A", "exclude_st": True},
        "constraints": [{"field": "dividend_yield", "op": ">=", "value": 4}],
        "idempotency_key": "research-1",
    })
    assert created.status_code == 201
    result = client.get(f"/api/research/tasks/{created.json()['id']}/result", headers=auth_headers)
    assert result.status_code == 200
    assert result.json()["source"] != "demo"
    assert all(item["evidence"] for item in result.json()["candidates"])
```

- [x] **Step 2: Verify failure**

Run: `python -m pytest agent/tests/test_research_task_api.py -q`
Expected: FAIL because the route and schema do not exist.

- [x] **Step 3: Add additive SQLite migration**

Create `research_tasks`, `research_results`, and `research_evidence` tables and increment `_SCHEMA_VERSION`. Store JSON only for bounded request/result structures; index task owner, status, and creation time.

- [x] **Step 4: Implement service and routes**

Parse supported constraints, call the existing `PublicResearchService.search`, retain only values actually returned by the data store, create evidence rows for every displayed metric, and persist terminal state. Unknown constraints return 422.

- [x] **Step 5: Verify lifecycle, ownership, idempotency, cancellation, and source tests**

Run: `python -m pytest agent/tests/test_research_task_api.py -q`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add agent/src/product/research_tasks.py agent/src/api/research_task_routes.py agent/src/product/store.py agent/api_server.py agent/tests/test_research_task_api.py
git commit -m "feat: persist evidence-backed research tasks"
```

### Task 4: Typed Web Research Client and AI Discovery Page

**Files:**
- Create: `frontend/src/lib/researchApi.ts`
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Delete after migration: `frontend/src/pages/public/researchWorkbenchData.ts`
- Modify: `frontend/src/pages/public/__tests__/LandingPage.test.tsx`

**Interfaces:**
- `getDiscovery(): Promise<DiscoveryResponse>`.
- `createResearchTask(input): Promise<ResearchTask>`.
- `getResearchTask(id): Promise<ResearchTask>`.

- [x] **Step 1: Replace fixture-oriented tests with API state tests**

Test loading, success, unavailable metrics, empty templates, request failure, task creation, server-confirmed progress, and navigation to `/research/result/{taskId}`.

- [x] **Step 2: Verify tests fail**

Run: `npm test -- --run src/pages/public/__tests__/LandingPage.test.tsx`
Expected: FAIL because the page still imports runtime fixtures.

- [x] **Step 3: Implement typed client**

Use `authHeaders()` for task routes, parse non-2xx responses into `ApiError`, and expose no fallback values.

- [x] **Step 4: Refactor LandingPage**

Fetch discovery on mount, render four states, submit a real task, poll its confirmed state, and navigate only when the result is ready. Remove timers, `marketPulse`, `researchCandidates`, `topicPrompts`, and all demo labels.

- [x] **Step 5: Verify frontend tests**

Run: `npm test -- --run src/pages/public/__tests__/LandingPage.test.tsx`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add frontend/src/lib/researchApi.ts frontend/src/pages/public/LandingPage.tsx frontend/src/pages/public/__tests__/LandingPage.test.tsx
git rm frontend/src/pages/public/researchWorkbenchData.ts
git commit -m "feat: connect AI discovery to real research service"
```

### Task 5: Real Research Result Page

**Files:**
- Modify: `frontend/src/pages/public/ResearchResultPage.tsx`
- Modify: `frontend/src/pages/public/__tests__/ResearchResultPage.test.tsx`

**Interfaces:**
- Consumes: `getResearchResult(taskId): Promise<ResearchResult>` from Task 4.
- Produces: source-attributed result UI with empty/error/not-ready states.

- [x] **Step 1: Write failing response-state tests**

Assert candidate values come only from the API, evidence source links render, unavailable metrics show `—`, and revoked/missing tasks show an error rather than demo content.

- [x] **Step 2: Verify tests fail**

Run: `npm test -- --run src/pages/public/__tests__/ResearchResultPage.test.tsx`
Expected: FAIL because the page imports `researchWorkbenchData`.

- [x] **Step 3: Refactor result rendering**

Use route parameter as task ID, fetch the result, render its scope, candidates, evidence, risks, source, and observation time. Remove all hard-coded conclusion and method text that claims a completed analysis.

- [x] **Step 4: Verify tests**

Run: `npm test -- --run src/pages/public/__tests__/ResearchResultPage.test.tsx`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add frontend/src/pages/public/ResearchResultPage.tsx frontend/src/pages/public/__tests__/ResearchResultPage.test.tsx
git commit -m "feat: render persisted research results"
```

### Task 6: Research Vertical-Slice Verification

**Files:**
- Modify: `tools/check_web_runtime_mocks.py`
- Modify: `artifacts/runtime-mock-inventory.txt`

**Interfaces:**
- Consumes all Task 1–5 artifacts.
- Produces a passing API/UI/build gate for the research slice.

- [ ] **Step 1: Run backend suite**

Run: `python -m pytest agent/tests/test_public_research_api.py agent/tests/test_research_task_api.py agent/tests/test_web_runtime_mock_guard.py -q`
Expected: PASS.

- [ ] **Step 2: Run frontend suite and build**

Run: `npm test -- --run src/pages/public/__tests__/LandingPage.test.tsx src/pages/public/__tests__/ResearchResultPage.test.tsx && npm run typecheck && npm run build:web`
Expected: PASS.

- [ ] **Step 3: Run runtime mock scanner**

Run: `python tools/check_web_runtime_mocks.py --scope research`
Expected: no AI discovery or research-result violations.

- [ ] **Step 4: Browser integration check**

Start the existing backend and Web dev server, sign in, submit a question, observe persisted task steps, refresh during execution, and open the completed result. Stop the data source and confirm an unavailable/error state replaces numeric content.

- [ ] **Step 5: Commit verification artifacts**

```bash
git add tools/check_web_runtime_mocks.py artifacts/runtime-mock-inventory.txt
git commit -m "test: verify real research vertical slice"
```
