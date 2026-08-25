# Data Hub First Skill Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all published AI research Skills to a validated, Data-Hub-first data policy with controlled fallbacks, accurate catalog metadata, and a shared executable runtime.

**Architecture:** A focused `src/skill_runtime` package owns manifest validation, Data Hub access, capability routing, provenance, and fallback errors. Every installed `SKILL.md` receives a versioned `sigmx` manifest block generated from a reviewed migration registry; the public catalog and Web UI consume the same parsed metadata instead of inferring ownership or requirements.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, PyYAML-compatible front-matter parsing without a new runtime dependency, React 19, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-data-hub-first-skill-runtime-design.md`

## Global Constraints

- Preserve all existing Skill slugs and `/skills/:slug` URLs.
- Data Hub credentials are read only from `SIGMX_DATA_HUB_BASE_URL` and `SIGMX_DATA_HUB_KEY`.
- Never send a SigmX credential to a non-SigmX request target.
- Fallback sources are explicit, registered, provenance-preserving, and never silently change metric semantics.
- Existing licenses and third-party attribution remain intact.
- Migration is idempotent and must validate 102/102 currently published manifests.
- No Skill may default to `openapi.iwencai.com` or require `IWENCAI_API_KEY` after migration.

---

### Task 1: Manifest schema and migration registry

**Files:**
- Create: `agent/src/skill_runtime/__init__.py`
- Create: `agent/src/skill_runtime/models.py`
- Create: `agent/src/skill_runtime/manifest.py`
- Create: `agent/src/skill_runtime/migration_registry.py`
- Create: `agent/tests/test_skill_runtime_manifest.py`

**Interfaces:**
- Produces: `SkillDataPolicy`, `SkillManifest`, `load_skill_manifest(path)`, `validate_skill_tree(root)`, and `policy_for_slug(slug)`.

- [ ] Write tests asserting valid ownership/source/execution enums, endpoint requirements for Data Hub policies, fallback allow-list validation, stable migration coverage for every installed slug, and rejection of legacy Iwencai defaults.
- [ ] Run `python -m pytest tests/test_skill_runtime_manifest.py -q` and verify failures are caused by missing runtime modules.
- [ ] Implement the immutable models, a bounded front-matter parser for the nested `sigmx` block, and a migration registry covering every current slug.
- [ ] Re-run the focused tests and verify they pass.

### Task 2: Data client, capability registry, and routing

**Files:**
- Create: `agent/src/skill_runtime/registry.py`
- Create: `agent/src/skill_runtime/client.py`
- Create: `agent/src/skill_runtime/router.py`
- Create: `agent/src/skill_runtime/cli.py`
- Create: `agent/tests/test_skill_runtime_client.py`
- Create: `agent/tests/test_skill_runtime_router.py`

**Interfaces:**
- Consumes: `SkillDataPolicy` from Task 1 and `ENDPOINT_CATALOG_V2` from `src.product.datahub_catalog`.
- Produces: `DataRequest`, `DataResult`, `DataHubClient.fetch()`, `SkillDataRouter.fetch()`, stable runtime error codes, and `python -m src.skill_runtime.cli`.

- [ ] Write tests for Bearer authentication, URL containment, JSON normalization, error mapping, Data Hub primary routing, permitted fallback, forbidden fallback, schema mismatch, and provenance retention.
- [ ] Run both focused test files and confirm expected failures.
- [ ] Implement the minimal client and router with dependency-injected transports/fallback adapters.
- [ ] Re-run focused tests and verify they pass.

### Task 3: Migrate all installed manifests and executable scripts

**Files:**
- Create: `agent/scripts/migrate_skill_manifests.py`
- Modify: `agent/src/skills/*/SKILL.md`
- Modify: `agent/src/skills/announcement-search/scripts/announcement_search.py`
- Modify: `agent/src/skills/news-search/scripts/news_search.py`
- Modify: `agent/src/skills/report-search/scripts/report_search.py`
- Modify: `agent/src/skills/hithink-*/scripts/cli.py`
- Create: `agent/tests/test_skill_tree_audit.py`

**Interfaces:**
- Consumes: `policy_for_slug` and `validate_skill_tree`.
- Produces: idempotently migrated manifests and shared-runtime compatibility wrappers for legacy executable Skills.

- [ ] Write a tree audit test requiring every installed manifest to contain schema version 1 metadata, valid endpoints, registered fallbacks, accurate executable status, no Iwencai default URL, and no `IWENCAI_API_KEY` requirement.
- [ ] Run the audit and verify it fails against the legacy tree.
- [ ] Implement the migration script, run it once, and replace duplicated Iwencai HTTP clients with wrappers that invoke the shared runtime while preserving each CLI command surface.
- [ ] Run the migration a second time and assert `git diff` does not change, then run the audit to green.

### Task 4: Public catalog API metadata

**Files:**
- Modify: `agent/src/api/public_skill_routes.py`
- Modify: `agent/src/product/skill_catalog_zh.py`
- Modify: `agent/tests/test_public_skill_routes.py`

**Interfaces:**
- Consumes: `load_skill_manifest`.
- Produces: public summary/detail fields `ownership`, `ownership_label`, `execution`, `primary_source`, `primary_source_label`, `datahub_endpoints`, `fallback_sources`, `markets`, `credential_required`, and `capability_status`.

- [ ] Extend API tests first to assert truthful metadata for official Data Hub, adapted, instructional, and public-source Skills.
- [ ] Run the focused API tests and confirm schema/assertion failures.
- [ ] Replace the regex-only manifest interpretation and unconditional `official=True` with shared parser output and localized labels.
- [ ] Re-run the focused API tests to green.

### Task 5: Skills catalog and detail UI

**Files:**
- Modify: `frontend/src/lib/skillsApi.ts`
- Modify: `frontend/src/pages/public/ResearchSkillsPage.tsx`
- Modify: `frontend/src/pages/public/ResearchSkillDetailPage.tsx`
- Modify: `frontend/src/pages/public/__tests__/ResearchSkillsPage.test.tsx`
- Modify: `frontend/src/pages/public/__tests__/ResearchSkillDetailPage.test.tsx`

**Interfaces:**
- Consumes: enriched public Skill API.
- Produces: accurate ownership/source/execution badges, Data Hub endpoint and fallback disclosure, and conditional installation environment instructions.

- [ ] Update tests first for four ownership labels, main source disclosure, executable state, Data Hub endpoint links, fallback disclosure, and per-Skill environment variables.
- [ ] Run focused Vitest files and confirm expected failures.
- [ ] Implement the minimal UI and TypeScript types using the existing page design system.
- [ ] Re-run focused tests to green.

### Task 6: Whole-system verification

**Files:**
- Modify only files required to repair regressions caused by Tasks 1–5, always with a failing regression test first.

**Interfaces:**
- Consumes: all prior deliverables.
- Produces: verified repository state and browser-tested Skills flow.

- [ ] Run `python -m pytest tests/test_skill_runtime_manifest.py tests/test_skill_runtime_client.py tests/test_skill_runtime_router.py tests/test_skill_tree_audit.py tests/test_public_skill_routes.py -q`.
- [ ] Run the complete backend test suite applicable to `agent` and record exact failures.
- [ ] Run the full frontend Vitest suite with the bundled Node runtime and a 10-second test timeout.
- [ ] Run TypeScript `tsc -b` and Vite `build --mode web`.
- [ ] Run `git diff --check` and the idempotent migration check.
- [ ] Use the in-app browser to inspect `/skills`, a Data Hub Skill detail, an adapted Skill detail, and a public-source Skill detail; verify installation prompts and badges match API metadata.
