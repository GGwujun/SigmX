# AI Research Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public, locally installed AI research Skills catalog that converts users to SigmX Data Hub credentials and usage.

**Architecture:** Static typed Skill metadata powers a catalog and detail route. Detail pages generate per-agent installation commands and Data Hub configuration instructions; online AI discovery remains a secondary preview path. Public navigation uses route-aware active states.

**Tech Stack:** React 19, React Router, TypeScript, Tailwind CSS, Vitest, Testing Library, lucide-react.

**Spec:** `docs/superpowers/specs/2026-08-23-ai-research-skills-design.md`

## Global Constraints

- Public routes are `/skills` and `/skills/:slug`.
- Primary conversion is local Skill installation plus Data Hub Credential activation.
- No backend, community publishing, ratings, or real command execution.
- Reuse the existing public-site design language and Data Hub routes.

---

### Task 1: Route-aware public navigation

**Files:**
- Modify: `frontend/src/components/public/PublicLayout.tsx`
- Test: `frontend/src/components/public/__tests__/PublicLayout.test.tsx`

**Interfaces:**
- Produces: active navigation links using `aria-current="page"` and route-group matching.

- [ ] Write a failing test rendering `/intelligence`, `/docs/data-hub/`, and `/skills/example`, asserting the owning link has `aria-current="page"`.
- [ ] Run `vitest --run src/components/public/__tests__/PublicLayout.test.tsx` and confirm the assertions fail because links are static.
- [ ] Replace public navigation links with route-aware links and add the “投研 Skills” destination.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Typed Skill catalog and marketplace page

**Files:**
- Create: `frontend/src/pages/public/researchSkillsData.ts`
- Create: `frontend/src/pages/public/ResearchSkillsPage.tsx`
- Create: `frontend/src/pages/public/__tests__/ResearchSkillsPage.test.tsx`

**Interfaces:**
- Produces: `ResearchSkill`, `researchSkillCategories`, `researchSkills`, and `getResearchSkill(slug)`.
- Produces: catalog search, category filtering, featured section, 12 Skill links, and empty state.

- [ ] Write failing tests for 12 rendered Skills, category filtering, keyword search, and clearing an empty result.
- [ ] Run the focused test and verify the page/module are missing.
- [ ] Add the typed 12-Skill dataset with Data Hub endpoints, steps, install metadata, usage, freshness, and credit estimates.
- [ ] Implement the responsive catalog using existing SigmX public styles and real lucide icons.
- [ ] Re-run the focused test and confirm all catalog behavior passes.

### Task 3: Local-agent installation detail page

**Files:**
- Create: `frontend/src/pages/public/ResearchSkillDetailPage.tsx`
- Create: `frontend/src/pages/public/__tests__/ResearchSkillDetailPage.test.tsx`

**Interfaces:**
- Consumes: `getResearchSkill(slug)`.
- Produces: agent tabs for Codex, Claude Code, OpenClaw, and SigmX Desktop; copyable command; Credential CTA; Data Hub dependency links; online-preview URL.

- [ ] Write failing tests for the default Codex command, switching to OpenClaw, Credential/docs links, online preview URL, and unknown-slug state.
- [ ] Run the focused test and verify it fails because the detail page does not exist.
- [ ] Implement the detail page and deterministic install command mapping.
- [ ] Re-run the focused test and confirm all detail behavior passes.

### Task 4: Routes, AI preview handoff, and verification

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/router/webRouter.tsx`
- Modify: `frontend/src/router/productRoutes.ts`
- Modify: `frontend/src/router/__tests__/productBoundaries.test.ts`
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Modify: `frontend/src/pages/public/__tests__/LandingPage.test.tsx`

**Interfaces:**
- Consumes: Skills pages and `getResearchSkill(slug)`.
- Produces: route registration and optional `skill`/`q` online-preview prefill.

- [ ] Write failing route-boundary and LandingPage tests for `/skills`, `/skills/:slug`, and Skill-aware research scope.
- [ ] Run focused tests and confirm failures reflect missing routes and metadata display.
- [ ] Register lazy routes in both public routers and product boundaries.
- [ ] Read `skill` and `q` in LandingPage and show the selected Skill in the research scope and plan.
- [ ] Run all focused tests, then full Vitest, `tsc --noEmit`, and Vite build.
- [ ] Open `/skills`, exercise search/category/detail/agent switching, verify navigation active states, and leave the working prototype open.
