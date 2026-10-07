# Web AI Analysis Chat Implementation Plan

> **批量审计关闭（2026-10-07）：** 本计划属线C（Web AI发现/公网研究智能体，2026-08-23 至 08-29）系列。终态已交付并验证：研究 planner（`/api/research/plans`）、定价阶梯（PricingPage）、统一 agent runtime（`agent/src/research_agent/`）、GPT 风格聊天 UI 均已上线并有测试覆盖（后端 26 + 前端 38 测试 + tsc 全绿，`design-qa.md` passed）。部分步骤经后续取代计划以不同提交信息完成，checkbox 按终态存在性批量关闭；逐条追溯见 git log 8141912..1532227。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Web AI Discovery form layout with a user-facing chat analysis workspace that preserves the current research-plan and research-task APIs.

**Architecture:** Keep `LandingPage` as the data-flow owner and extract focused presentational components for conversation history and the analysis timeline. Map the existing `idle/planning/plan/running/done/error` state machine to chat messages and structured cards without introducing a new backend chat protocol.

**Tech Stack:** React 19, TypeScript, React Router, Tailwind CSS, Lucide React, Vitest, Testing Library

**Spec:** `docs/superpowers/specs/2026-08-28-web-ai-analysis-chat-design.md`

## Global Constraints

- This phase changes frontend UI and frontend state composition only; no backend endpoints are added or modified.
- Do not expose model names, providers, API URLs, token details, internal table names, or raw tool arguments.
- Keep existing research plan, task execution, authentication handoff, pending-plan restoration, and result navigation behavior.
- Do not add desktop-only trading, file upload, Swarm, Goal, or live-runtime controls.
- The history rail is part of AI analysis only and becomes a drawer on narrow screens.

---

### Task 1: Build the AI Analysis Shell and Conversation History

**Files:**
- Create: `frontend/src/components/public/AIAnalysisShell.tsx`
- Test: `frontend/src/components/public/__tests__/AIAnalysisShell.test.tsx`

**Interfaces:**
- Consumes: `ResearchTask` from `@/lib/researchApi`, `children: ReactNode`, `onNewAnalysis: () => void`
- Produces: `AIAnalysisShell({ recentTasks, activeTaskId, onNewAnalysis, children })` and a responsive history toggle labeled `对话历史`

- [x] **Step 1: Write the failing shell tests**

```tsx
render(
  <MemoryRouter>
    <AIAnalysisShell
      recentTasks={[task]}
      activeTaskId={task.id}
      onNewAnalysis={onNew}
    >
      <div>当前对话</div>
    </AIAnalysisShell>
  </MemoryRouter>,
);
expect(screen.getByRole("heading", { name: "对话历史" })).toBeInTheDocument();
expect(screen.getByRole("link", { name: task.question })).toHaveAttribute("href", `/research/result/${task.id}`);
expect(screen.queryByText(/glm-|provider|API URL/i)).not.toBeInTheDocument();
fireEvent.click(screen.getByRole("button", { name: "新建分析" }));
expect(onNew).toHaveBeenCalledOnce();
```

- [x] **Step 2: Run the shell test and verify it fails**

Run: `npm run test:run -- src/components/public/__tests__/AIAnalysisShell.test.tsx`

Expected: FAIL because `AIAnalysisShell.tsx` does not exist.

- [x] **Step 3: Implement the shell**

Create a two-column layout with these exact responsibilities:

```tsx
interface AIAnalysisShellProps {
  recentTasks: ResearchTask[];
  activeTaskId: string | null;
  onNewAnalysis: () => void;
  children: ReactNode;
}

export function AIAnalysisShell(props: AIAnalysisShellProps) {
  const [historyOpen, setHistoryOpen] = useState(false);
  // Desktop: 220px history rail + flexible analysis area.
  // Mobile: history is hidden until the 对话历史 button opens an overlay drawer.
}
```

Render only user-facing labels: `对话历史`, `新建分析`, `今天`, `更早`, and `SigmX AI 分析`. Group tasks using their `created_at` date, show completed tasks as links to `/research/result/:id`, and show an empty-history message when no tasks exist.

- [x] **Step 4: Run the shell test and verify it passes**

Run: `npm run test:run -- src/components/public/__tests__/AIAnalysisShell.test.tsx`

Expected: PASS with no model/provider copy rendered.

- [x] **Step 5: Commit the shell**

```bash
git add frontend/src/components/public/AIAnalysisShell.tsx frontend/src/components/public/__tests__/AIAnalysisShell.test.tsx
git commit -m "feat: add web AI analysis chat shell"
```

### Task 2: Build Chat Timeline Cards for Every Research State

**Files:**
- Create: `frontend/src/components/public/AIAnalysisTimeline.tsx`
- Test: `frontend/src/components/public/__tests__/AIAnalysisTimeline.test.tsx`
- Reuse: `frontend/src/components/public/ResearchPlanPanel.tsx`

**Interfaces:**
- Consumes: `RunState`, question, `ResearchPlan | null`, `ResearchTask | null`, research events, `ResearchResult | null`, load/run errors, and callbacks
- Produces: `AIAnalysisTimeline` that renders user and assistant message rows plus plan/progress/result cards

- [x] **Step 1: Write failing state-mapping tests**

Cover the six states with explicit assertions:

```tsx
expect(renderState("idle")).toHaveTextContent("今天想分析什么？");
expect(renderState("planning")).toHaveTextContent("正在理解你的研究问题");
expect(renderState("plan")).toHaveTextContent("我整理了一份研究计划");
expect(renderState("running")).toHaveTextContent("正在分析");
expect(renderState("done")).toHaveTextContent(result.summary);
expect(renderState("error")).toHaveTextContent("分析没有完成");
```

Also assert that a discovery load error appears as a lightweight assistant message and that `plan.model`, `result.model`, provider names, raw event payloads, and API URLs are absent.

- [x] **Step 2: Run the timeline tests and verify they fail**

Run: `npm run test:run -- src/components/public/__tests__/AIAnalysisTimeline.test.tsx`

Expected: FAIL because the timeline component does not exist.

- [x] **Step 3: Implement the timeline and cards**

Use the following public prop contract:

```tsx
export type AIAnalysisRunState = "idle" | "planning" | "plan" | "running" | "done" | "error";

interface AIAnalysisTimelineProps {
  phase: AIAnalysisRunState;
  question: string;
  plan: ResearchPlan | null;
  task: ResearchTask | null;
  events: ResearchEvent[];
  result: ResearchResult | null;
  loadError: string;
  runError: string;
  onRun: () => void;
  onRetry: () => void;
  onUseSuggested: (question: string) => void;
  onResetPlan: () => void;
}
```

The timeline must:

- render the submitted question as a right-aligned user bubble;
- render planning and running states as plain-language progress rows derived from `task.steps` and safe event labels;
- render `ResearchPlanPanel` inside an assistant message for `plan`;
- render result candidates as responsive cards with PE and dividend yield, plus links to `/stock/:code` and `/research/result/:taskId`;
- render errors as assistant messages with `重试` and `修改问题` actions;
- never render `plan.model`, `result.model`, provider identifiers, raw tools, or raw payload JSON.

- [x] **Step 4: Run timeline tests and verify they pass**

Run: `npm run test:run -- src/components/public/__tests__/AIAnalysisTimeline.test.tsx`

Expected: PASS for all six states and the technical-copy exclusions.

- [x] **Step 5: Commit the timeline**

```bash
git add frontend/src/components/public/AIAnalysisTimeline.tsx frontend/src/components/public/__tests__/AIAnalysisTimeline.test.tsx
git commit -m "feat: render web research flow as AI conversation"
```

### Task 3: Integrate the Chat UI into LandingPage

**Files:**
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Modify: `frontend/src/pages/public/__tests__/LandingPage.test.tsx`

**Interfaces:**
- Consumes: `AIAnalysisShell` and `AIAnalysisTimeline` from Tasks 1 and 2
- Produces: the `/` page as a chat-first analysis experience while preserving current API calls and navigation

- [x] **Step 1: Update LandingPage tests to describe the approved experience**

Replace layout-specific expectations with user behavior:

```tsx
expect(await screen.findByRole("heading", { name: "SigmX AI 分析" })).toBeInTheDocument();
expect(screen.getByRole("heading", { name: "对话历史" })).toBeInTheDocument();
expect(screen.getByLabelText("研究问题")).toBeInTheDocument();
expect(screen.queryByText(/glm-|Provider|API URL/i)).not.toBeInTheDocument();
```

Keep the existing tests for plan-before-task, unavailable-condition replacement, unauthenticated pending-plan preservation, expired-login preservation, task result rendering, and recent research links.

- [x] **Step 2: Run LandingPage tests and verify the new expectations fail**

Run: `npm run test:run -- src/pages/public/__tests__/LandingPage.test.tsx`

Expected: FAIL because the current page still renders the form/workspace layout.

- [x] **Step 3: Replace the layout while preserving data orchestration**

Keep the existing state and API functions in `LandingPage`. Remove the market-metrics header, research-start sidebar, runtime settings grid, and standalone workspace. Compose:

```tsx
<AIAnalysisShell
  recentTasks={recentTasks}
  activeTaskId={activeTask?.id ?? null}
  onNewAnalysis={resetConversation}
>
  <AIAnalysisTimeline {...timelineProps} />
  <AIAnalysisComposer
    value={query}
    disabled={phase === "planning" || phase === "running"}
    suggestions={discovery?.templates ?? []}
    onChange={handleQueryChange}
    onSubmit={submit}
  />
</AIAnalysisShell>
```

Implement the composer inside `LandingPage` unless extraction is required to keep `LandingPage` below its current size. `resetConversation` clears query, template, plan, result, run error, active task, agent events, and pending-plan storage. A follow-up suggestion updates the input only; it must not create a task without the user submitting.

- [x] **Step 4: Run focused tests**

Run: `npm run test:run -- src/components/public/__tests__/AIAnalysisShell.test.tsx src/components/public/__tests__/AIAnalysisTimeline.test.tsx src/pages/public/__tests__/LandingPage.test.tsx`

Expected: all focused test files pass.

- [x] **Step 5: Run type checking and the broader public-page regression suite**

Run: `npm run typecheck`

Expected: exit code 0.

Run: `npm run test:run -- src/pages/public/__tests__/PublicDiscovery.test.tsx src/pages/public/__tests__/LandingPage.test.tsx`

Expected: all tests pass.

- [x] **Step 6: Verify the running Web page**

Start or reuse `npm run dev`, open `http://localhost:5899/`, and verify:

- history is visible on desktop and opens as a drawer on narrow screens;
- a question becomes a user message;
- plan, progress, result, and error states remain inside the conversation;
- no model/provider/API details are visible;
- other Web routes still use the existing platform navigation.

- [x] **Step 7: Commit integration**

```bash
git add frontend/src/pages/public/LandingPage.tsx frontend/src/pages/public/__tests__/LandingPage.test.tsx
git commit -m "feat: make web AI discovery chat-first"
```

