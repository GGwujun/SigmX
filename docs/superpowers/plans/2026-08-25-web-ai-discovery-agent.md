# Web AI Discovery Agent Implementation Plan

> **批量审计关闭（2026-10-07）：** 本计划属线C（Web AI发现/公网研究智能体，2026-08-23 至 08-29）系列。终态已交付并验证：研究 planner（`/api/research/plans`）、定价阶梯（PricingPage）、统一 agent runtime（`agent/src/research_agent/`）、GPT 风格聊天 UI 均已上线并有测试覆盖（后端 26 + 前端 38 测试 + tsc 全绿，`design-qa.md` passed）。部分步骤经后续取代计划以不同提交信息完成，checkbox 按终态存在性批量关闭；逐条追溯见 git log 8141912..1532227。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Web AI Discovery's rule-only execution with a real, research-only AgentLoop pipeline and add administrator-owned AI runtime configuration.

**Architecture:** A platform AI configuration service supplies validated, secret-safe model settings to a new Web Research Orchestrator. The orchestrator uses an explicit research tool allowlist, persists public-safe progress events and evidence, and exposes plan/task/result APIs consumed by the existing AI Discovery visual flow.

**Tech Stack:** Python 3.12, FastAPI, SQLite, existing ChatLLM/AgentLoop/Skill Runtime, React 19, TypeScript, SSE, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-web-ai-discovery-agent-design.md`

## Global Constraints

- Do not expose or register account, portfolio, broker, order, mandate, live-runner, trading, or shadow-account tools.
- Do not expose platform API keys through responses, logs, SSE events, or reports.
- Data Hub is the primary research source; fallback sources must be disclosed.
- Preserve the current Web AI Discovery visual language and plan-confirmation flow.
- Do not present a rules-only result as AI-generated.

---

### Task 1: Platform AI configuration and secret-safe admin API

**Files:**
- Create: `agent/src/product/ai_runtime_config.py`
- Create: `agent/src/api/admin_ai_routes.py`
- Modify: `agent/src/product/store.py`
- Modify: `agent/api_server.py`
- Create: `agent/tests/test_ai_runtime_config.py`
- Create: `agent/tests/test_admin_ai_routes.py`

**Interfaces:**
- Produces: `AIRuntimeConfigService.get_effective() -> AIRuntimeConfig`
- Produces: `/api/admin/ai/providers`, `/strategy`, `/secrets`, `/sources`, `/health`

- [x] Write failing store tests proving provider settings persist, secrets are encrypted/masked, and API responses never contain plaintext keys.
- [x] Run `python -m pytest agent/tests/test_ai_runtime_config.py -q` and verify failures are caused by missing service/schema.
- [x] Implement focused SQLite tables, environment-backed encryption key handling, masked DTOs, and effective strategy resolution.
- [x] Run the store tests until green.
- [x] Write failing route tests for admin authorization, CRUD, provider connection-test injection, and audit records.
- [x] Run `python -m pytest agent/tests/test_admin_ai_routes.py -q` and verify expected failures.
- [x] Implement and register the admin routes without returning secret material.
- [x] Run both task test files and commit.

### Task 2: Research-only Agent boundary

**Files:**
- Create: `agent/src/research_agent/__init__.py`
- Create: `agent/src/research_agent/tools.py`
- Create: `agent/src/research_agent/runner.py`
- Create: `agent/tests/test_research_agent_tools.py`
- Create: `agent/tests/test_research_agent_runner.py`

**Interfaces:**
- Produces: `build_research_tools(dependencies) -> list[Tool]`
- Produces: `ResearchAgentRunner.run(request, emit, cancel) -> AgentResearchOutput`
- Consumes: `ChatLLM`, Skill Registry, DataHubClient, news/report search dependencies.

- [x] Write a failing allowlist test asserting research tools are present and forbidden trading/account marker names are absent.
- [x] Run the test and verify it fails because the module is missing.
- [x] Implement the smallest explicit allowlist; never derive it by filtering the global tool registry.
- [x] Run the allowlist test until green.
- [x] Write failing runner tests using injected LLM/tools for tool calls, evidence capture, cancellation, timeout, and sanitized emitted events.
- [x] Run the runner tests and verify behavioral failures.
- [x] Implement the runner adapter around the existing agent primitives with dependency injection and public event mapping.
- [x] Run the task tests and commit.

### Task 3: AI plan generation with deterministic validation

**Files:**
- Modify: `agent/src/product/research_plans.py`
- Modify: `agent/src/api/research_task_routes.py`
- Modify: `agent/tests/test_research_plans.py`
- Modify: `agent/tests/test_research_task_api.py`

**Interfaces:**
- Produces: `AIResearchPlanService.create(question, template_id, scope) -> ResearchPlan`
- Consumes: effective planning model and existing metric capability validator.

- [x] Add failing tests that require an LLM call, validate structured multi-metric plans, reject invented datasets/operators, and report `ai_unconfigured` rather than silently claiming AI.
- [x] Run the focused tests and verify they fail against the existing regex-only service.
- [x] Implement structured planning prompts, JSON parsing/repair, capability validation, and explicit `execution_mode`/degradation metadata.
- [x] Run the focused tests until green and commit.

### Task 4: Persistent asynchronous research orchestration and SSE

**Files:**
- Create: `agent/src/product/research_orchestrator.py`
- Modify: `agent/src/product/research_tasks.py`
- Modify: `agent/src/product/store.py`
- Modify: `agent/src/api/research_task_routes.py`
- Create: `agent/tests/test_research_orchestrator.py`
- Modify: `agent/tests/test_research_task_api.py`

**Interfaces:**
- Produces: `ResearchOrchestrator.start(...)`, `cancel(...)`, `retry(...)`, `events(...)`
- Produces: SSE endpoint `/api/research/tasks/{id}/events`
- Consumes: `ResearchAgentRunner` and persisted confirmed plan.

- [x] Add failing tests for queued/running/partial/succeeded/failed/cancelled states, refresh recovery, event cursors, retry lineage, idempotency, and evidence-linked conclusions.
- [x] Run focused tests and verify expected failures.
- [x] Add the minimal schema migration for plans, agent metadata, events, evidence references, and retry lineage.
- [x] Implement background execution, safe event persistence, cancellation, retry, and result assembly.
- [x] Run focused tests until green and commit.

### Task 5: AI Discovery frontend integration

**Files:**
- Modify: `frontend/src/lib/researchApi.ts`
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Modify: `frontend/src/components/public/ResearchPlanPanel.tsx`
- Modify: `frontend/src/components/public/ResearchProgress.tsx`
- Modify: `frontend/src/pages/public/ResearchResultPage.tsx`
- Modify: corresponding files under `frontend/src/**/__tests__/`

**Interfaces:**
- Consumes: AI plan metadata, asynchronous task state, SSE events, evidence-rich result response.

- [x] Add failing component/API tests for AI mode disclosure, editable plan confirmation, live source/Skill progress, partial completion, cancellation/retry, refresh recovery, evidence cards, follow-up, and absence of trading UI.
- [x] Run focused Vitest files and verify failures are feature-related.
- [x] Extend typed API clients and implement the existing visual flow against the new asynchronous APIs.
- [x] Keep research topics as full-question input helpers without numeric badges.
- [x] Run focused tests until green and commit.

### Task 6: Operations console AI capability pages

**Files:**
- Modify: `frontend/src/components/admin/AdminLayout.tsx`
- Create: `frontend/src/pages/admin/AIProvidersPage.tsx`
- Create: `frontend/src/pages/admin/AIStrategyPage.tsx`
- Create: `frontend/src/pages/admin/AISecretsPage.tsx`
- Create: `frontend/src/pages/admin/AIDataSourcesPage.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/lib/productApi.ts`
- Create: `frontend/src/pages/admin/__tests__/AISettingsPages.test.tsx`

**Interfaces:**
- Consumes: `/api/admin/ai/*` APIs from Task 1.

- [x] Add failing tests for navigation, masked secret rendering, provider tests, strategy validation, source priority, errors, and admin-only access.
- [x] Run the focused frontend test and verify expected failures.
- [x] Implement four focused pages and typed API methods; do not place all functions back into the operations overview.
- [x] Run focused tests until green and commit.

### Task 7: End-to-end verification and production readiness

**Files:**
- Modify only files required by failures found in this task, with a failing regression test first.

**Interfaces:**
- Verifies all interfaces produced by Tasks 1-6.

- [x] Run focused backend suites for AI configuration, planning, research agent, orchestrator, and research routes.
- [x] Run the full frontend test suite and production build with the bundled Node runtime.
- [x] Run Python compile checks and the broad backend suite; report the known Windows symlink privilege limitation separately if it recurs.
- [x] Start the local service with an injected test provider and execute a real AI Discovery flow through the browser.
- [x] Verify the UI contains no account/trading/shadow-account affordance and that every result number has evidence.
- [x] Run secret scans and `git diff --check`.
- [x] Commit any regression fixes and prepare deployment as a separate explicitly authorized operation.
