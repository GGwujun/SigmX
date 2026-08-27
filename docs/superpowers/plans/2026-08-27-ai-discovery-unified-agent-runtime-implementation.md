# AI Discovery Unified Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Web AI Discovery execute the mature AgentLoop with real research tools, Skills, controlled multi-agent work, context, files, evidence, and structured outputs.

**Architecture:** Add a Web-only `ResearchAgentRuntime` around the existing `AgentLoop`, with a strict allowlist and evidence adapter. Preserve existing research task APIs while extending runtime events and output schemas, then update the Web execution and result UI.

**Tech Stack:** Python 3, FastAPI, AgentLoop, SQLite, Pydantic, React, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-ai-discovery-unified-agent-runtime-design.md`

## Global Constraints

- Do not modify client Agent behavior or client settings.
- Never grant trading, account, position, order, shadow-account, Shell, background-process, arbitrary filesystem, or Skill-write tools.
- Default maximum is 50 iterations with an 80% wrap-up signal.
- Every material conclusion must reference evidence from the same research run.
- Rules fallback is `rules_degraded`, never normal AI completion.
- Preserve existing task APIs and old-result readability.

---

### Task 1: Runtime Contracts and Output Schema

**Files:**
- Create: `agent/src/research_agent/contracts.py`
- Create: `agent/src/research_agent/output.py`
- Test: `agent/tests/test_research_runtime_contracts.py`

**Interfaces:**
- Produces `ResearchRuntimeRequest`, `ResearchRuntimeState`, `ResearchBudget`, `ResearchOutputV2`, `EvidenceValidator.validate()`.

- [ ] Write failing tests for mode, phases, budgets, tools, Skills, agents, context, artifacts, same-run evidence, and legacy conversion.
- [ ] Run `pytest agent/tests/test_research_runtime_contracts.py -q` and verify failure.
- [ ] Implement versioned typed contracts and strict evidence validation.
- [ ] Run focused tests and verify pass.
- [ ] Commit `feat: define unified research runtime contracts`.

### Task 2: Research Tool Policy

**Files:**
- Create: `agent/src/research_agent/policy.py`
- Modify: `agent/src/tools/__init__.py`
- Test: `agent/tests/test_research_tool_policy.py`

**Interfaces:**
- Produces `ResearchToolPolicy.allowed_names(capabilities)`, `build_research_registry(...)`.

- [ ] Write failing allowlist/denylist tests enumerating all discovered tools and remote MCP behavior.
- [ ] Run focused tests and verify failure.
- [ ] Implement allowlist-first registry construction and permanent forbidden-name/category checks.
- [ ] Run tests and prove forbidden tools cannot be registered even when requested.
- [ ] Commit `feat: enforce Web research tool policy`.

### Task 3: AgentLoop Runtime Adapter

**Files:**
- Create: `agent/src/research_agent/runtime.py`
- Modify: `agent/src/agent/loop.py` only for reusable cancellation/event hooks if required
- Test: `agent/tests/test_research_agent_runtime.py`

**Interfaces:**
- Produces `ResearchAgentRuntime.run(request, emit, cancelled) -> ResearchOutputV2`.

- [ ] Write tests for 50 iterations, wrap-up, cancellation, timeout, tool events, budget exhaustion, model metadata, and structured completion.
- [ ] Run focused tests and verify failure.
- [ ] Implement adapter using existing `AgentLoop`; do not copy its ReAct loop.
- [ ] Run focused tests and existing AgentLoop tests.
- [ ] Commit `feat: run AI discovery on AgentLoop`.

### Task 4: Executable Research Skills

**Files:**
- Create: `agent/src/research_agent/skills.py`
- Modify: `agent/src/skill_runtime/manifest.py`
- Test: `agent/tests/test_research_skills_runtime.py`

**Interfaces:**
- Produces `ResearchSkillsLoader.resolve(plan, selected)`, Skill provenance and allowed-endpoint metadata.

- [ ] Write tests for matching, full instruction loading, declared Data Hub endpoints, fallback source disclosure, version/provenance, and tool-policy enforcement.
- [ ] Run focused tests and verify failure.
- [ ] Implement research loader and Agent context injection; remove metadata-only behavior from the new runtime.
- [ ] Run tests and verify a Skill drives a real allowed tool call.
- [ ] Commit `feat: execute research Skills in AI discovery`.

### Task 5: Evidence Collection and Intelligence Context

**Files:**
- Create: `agent/src/research_agent/evidence.py`
- Modify: `agent/src/research_agent/runtime.py`
- Test: `agent/tests/test_research_evidence.py`

**Interfaces:**
- Consumes stable article/event context from the intelligence plan.
- Produces `EvidenceCollector.record_tool_result()`, evidence snapshots, source/as-of metadata.

- [ ] Write tests for tool-result normalization, duplicate evidence, cross-run rejection, article/event snapshots, stale evidence, and missing dates.
- [ ] Run focused tests and verify failure.
- [ ] Implement collector and inject the evidence protocol into Agent context.
- [ ] Run focused tests.
- [ ] Commit `feat: add traceable research evidence ledger`.

### Task 6: Orchestrator Migration and Persistence

**Files:**
- Modify: `agent/src/product/research_orchestrator.py`
- Modify: `agent/src/product/research_tasks.py`
- Modify: `agent/src/api/research_task_routes.py`
- Test: `agent/tests/test_research_orchestrator_agent_runtime.py`

**Interfaces:**
- Persists runtime state/events while preserving current task endpoints.

- [ ] Write compatibility tests for create/run/cancel/result, restart recovery, legacy records, explicit degraded mode, and event replay.
- [ ] Run focused tests and verify failure.
- [ ] Route new tasks through `ResearchAgentRuntime`, persist V2 runtime state, and retain legacy readers.
- [ ] Run research route/orchestrator suites.
- [ ] Commit `refactor: migrate research tasks to unified runtime`.

### Task 7: Follow-up Context

**Files:**
- Create: `agent/src/research_agent/context.py`
- Modify: `agent/src/api/research_task_routes.py`
- Test: `agent/tests/test_research_followups.py`

**Interfaces:**
- Produces derived-run endpoint and `ResearchContextBuilder` with parent run/evidence lineage.

- [ ] Write tests for follow-up, appended constraints, rerun, evidence freshness, ownership, and lineage.
- [ ] Run focused tests and verify failure.
- [ ] Implement bounded context summaries and derived task persistence.
- [ ] Run focused tests.
- [ ] Commit `feat: support contextual AI research follow-ups`.

### Task 8: Restricted Files and Artifacts

**Files:**
- Create: `agent/src/research_agent/files.py`
- Modify: `agent/src/api/research_task_routes.py`
- Test: `agent/tests/test_research_files.py`

**Interfaces:**
- Produces upload/parse/artifact APIs limited to PDF, CSV, XLSX, JSON, and text.

- [ ] Write tests for allowed types, size limits, path traversal, isolation, lifecycle, read-only parsing, and controlled downloads.
- [ ] Run focused tests and verify failure.
- [ ] Implement per-task workspace and artifact metadata without arbitrary filesystem tools.
- [ ] Run focused tests.
- [ ] Commit `feat: add isolated research files and artifacts`.

### Task 9: Controlled Research Swarm

**Files:**
- Create: `agent/src/research_agent/swarm.py`
- Create: `agent/src/swarm/presets/web_research_team.yaml`
- Test: `agent/tests/test_research_swarm.py`

**Interfaces:**
- Produces `ResearchSwarmRouter.should_use_swarm()` and a fixed research-only preset.

- [ ] Write tests for simple/complex routing, inherited tools, shared budget/cancel, evidence merge, and forbidden permissions.
- [ ] Run focused tests and verify failure.
- [ ] Implement controlled roles and runtime integration.
- [ ] Run focused and existing swarm tests.
- [ ] Commit `feat: add controlled multi-agent Web research`.

### Task 10: AI Discovery Execution UI

**Files:**
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/pages/public/__tests__/LandingPageResearch.test.tsx`

**Interfaces:**
- Consumes V2 runtime state/events and file endpoints.

- [ ] Write UI tests for phases, iteration usage, granted/called tools, loaded/used Skills, agents, context, files, warnings, cancel, and degraded mode.
- [ ] Run focused Vitest and verify failure.
- [ ] Implement a real event-driven execution panel; remove decorative static capability data.
- [ ] Run focused tests and frontend build.
- [ ] Commit `feat: expose real AI discovery execution state`.

### Task 11: Research Result and Follow-up UI

**Files:**
- Modify: `frontend/src/pages/public/ResearchResultPage.tsx`
- Modify: `frontend/src/lib/researchApi.ts`
- Test: `frontend/src/pages/public/__tests__/ResearchResultPage.test.tsx`

**Interfaces:**
- Consumes `ResearchOutputV2`, evidence, lineage, artifacts, and derived-run endpoint.

- [ ] Write tests for conclusions/evidence, counter-evidence, risks, source dates, model/Skill/tool disclosure, follow-up, append constraints, rerun, downloads, and legacy records.
- [ ] Run focused tests and verify failure.
- [ ] Implement complete result and follow-up interactions.
- [ ] Run tests and build.
- [ ] Commit `feat: complete AI research results and follow-ups`.

### Task 12: Operations, Removal, and End-to-End Verification

**Files:**
- Modify: platform AI operations backend/frontend files discovered during execution
- Delete after migration: `agent/src/research_agent/runner.py`
- Test: `agent/tests/test_research_runtime_security.py`
- Test: `frontend/e2e/ai-discovery.spec.ts`

**Interfaces:**
- Produces runtime settings/metrics and removes the old 8-turn execution path.

- [ ] Write admin authorization, security inventory, degraded-mode, and core prompt E2E tests.
- [ ] Run tests and verify the old runner is still detected.
- [ ] Add maximum iteration/budget settings and metrics, remove old runner/callers, and migrate imports.
- [ ] Run backend suites, frontend tests/build, and the cash-flow-quality E2E scenario including a follow-up.
- [ ] Commit `feat: complete unified AI discovery runtime`.
