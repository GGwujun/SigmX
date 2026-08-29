# Web AI Agent Conversation Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render real user-visible model updates, tool activity, and verified final analysis in chronological Agent-chat order on Web AI Discovery.

**Architecture:** Add a research-only public-update stream parser around the shared `AgentLoop`, publish new persisted research events without exposing `thinking_delta` or final JSON, then reduce those ordered events into plain assistant/tool/final chat blocks in React. Preserve the existing task APIs, result validation, SSE replay, polling fallback, and legacy-task result rendering.

**Tech Stack:** Python 3, FastAPI/SSE, SQLite event log, pytest, React 19, TypeScript, Vitest, Testing Library, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-08-29-web-ai-agent-conversation-stream-design.md`

## Global Constraints

- Never render `thinking_delta`, system prompts, raw final JSON, secrets, internal URLs, or unapproved tool arguments.
- `assistant_final` is emitted only after evidence validation succeeds.
- Persist every public event before SSE publication so replay and live views are identical.
- Do not change Desktop `Agent.tsx` or its SSE contract.
- Existing completed research tasks without the new events must remain readable.
- Follow TDD for every production behavior change.

---

### Task 1: Parse Explicit Public Model Updates

**Files:**
- Create: `agent/src/research_agent/public_updates.py`
- Create: `agent/tests/test_research_public_updates.py`

**Interfaces:**
- Produces: `PublicUpdateStreamParser.feed(delta: str) -> list[str]`
- Produces: `PublicUpdateStreamParser.finish() -> list[str]`
- Contract: only text inside `<public_update>...</public_update>` is returned; arbitrary chunk boundaries are supported.

- [ ] **Step 1: Write failing parser tests**

```python
def test_emits_only_tagged_public_text_across_chunk_boundaries():
    parser = PublicUpdateStreamParser()
    visible = []
    for chunk in ["hidden<public_", "update>先查行情", "。</public_update>{\"summary\":"]:
        visible.extend(parser.feed(chunk))
    visible.extend(parser.finish())
    assert "".join(visible) == "先查行情。"

def test_supports_multiple_public_segments_without_leaking_json():
    parser = PublicUpdateStreamParser()
    visible = parser.feed("<public_update>第一段</public_update>noise<public_update>第二段</public_update>")
    assert "".join(visible) == "第一段第二段"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest agent/tests/test_research_public_updates.py -q`

Expected: FAIL because `src.research_agent.public_updates` does not exist.

- [ ] **Step 3: Implement the streaming state machine**

```python
class PublicUpdateStreamParser:
    OPEN = "<public_update>"
    CLOSE = "</public_update>"

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        output: list[str] = []
        while self._buffer:
            marker = self.CLOSE if self._inside else self.OPEN
            index = self._buffer.find(marker)
            if index >= 0:
                if self._inside and index:
                    output.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(marker):]
                self._inside = not self._inside
                continue
            keep = max(len(marker) - 1, 0)
            if self._inside and len(self._buffer) > keep:
                output.append(self._buffer[:-keep] if keep else self._buffer)
            self._buffer = self._buffer[-keep:] if keep else ""
            break
        return output

    def finish(self) -> list[str]:
        output = [self._buffer] if self._inside and self._buffer else []
        self._buffer = ""
        self._inside = False
        return output
```

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m pytest agent/tests/test_research_public_updates.py -q`

Expected: all parser tests pass.

- [ ] **Step 5: Commit parser behavior**

```bash
git add agent/src/research_agent/public_updates.py agent/tests/test_research_public_updates.py
git commit -m "feat: parse public research updates"
```

### Task 2: Publish Safe Research Agent Events

**Files:**
- Modify: `agent/src/research_agent/runtime.py`
- Modify: `agent/src/product/research_orchestrator.py`
- Test: `agent/tests/test_research_agent_runtime.py`
- Test: `agent/tests/test_research_task_api.py`

**Interfaces:**
- Consumes: `PublicUpdateStreamParser`
- Produces event: `assistant_delta {segment_id: str, iteration: int, delta: str}`
- Produces event: `assistant_segment_done {segment_id: str, iteration: int}`
- Produces event: `assistant_final {summary: str, conclusions: list, risks: list}`

- [ ] **Step 1: Add failing runtime event-order tests**

Use a deterministic fake loop/event sequence and assert the literal public sequence:

```python
assert [event["type"] for event in emitted] == [
    "assistant_delta", "assistant_segment_done",
    "tool_call", "tool_result", "assistant_final", "runtime_completed",
]
assert emitted[0]["delta"] == "我先核验行情。"
assert "internal reasoning" not in json.dumps(emitted, ensure_ascii=False)
```

Add a validation-failure test asserting no event has type `assistant_final`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m pytest agent/tests/test_research_agent_runtime.py agent/tests/test_research_task_api.py -q`

Expected: FAIL because the three public events are not emitted.

- [ ] **Step 3: Update the research prompt and event adapter**

Extend `_SYSTEM_PROMPT` with the exact contract:

```text
每次准备调用工具前，可先输出一段简短的用户可见进度，必须包裹在
<public_update>与</public_update>中。这里只说明正在核验什么以及为什么，
不得输出隐藏指令、逐步内部推理、密钥、URL或内部工具名称。
最终响应仍然只输出规定的 JSON 对象，不得带 public_update 标签。
```

In `ResearchAgentRuntime.forward`, parse only `text_delta`; convert tagged content to `assistant_delta`; preserve tool events; never forward public `thinking_delta` as display content. Close a segment before the next tool call and assign stable per-run segment IDs.

- [ ] **Step 4: Emit validated final content**

After evidence validation and optional repair, call:

```python
emit({
    "type": "assistant_final",
    "summary": str(payload.get("summary") or "研究已完成"),
    "conclusions": conclusions,
    "risks": [str(item) for item in payload.get("risks", [])],
})
```

Keep the existing `runtime_completed` event after it.

- [ ] **Step 5: Verify runtime and persisted SSE order**

Run: `python -m pytest agent/tests/test_research_agent_runtime.py agent/tests/test_research_task_api.py -q`

Expected: tests pass and SSE replay contains the same event ordering as the database event list.

- [ ] **Step 6: Commit backend protocol**

```bash
git add agent/src/research_agent/runtime.py agent/src/product/research_orchestrator.py agent/tests/test_research_agent_runtime.py agent/tests/test_research_task_api.py
git commit -m "feat: stream public research agent replies"
```

### Task 3: Build Ordered Frontend Conversation Blocks

**Files:**
- Create: `frontend/src/lib/researchConversation.ts`
- Create: `frontend/src/lib/__tests__/researchConversation.test.ts`
- Modify: `frontend/src/lib/researchApi.ts`

**Interfaces:**
- Produces union `ResearchConversationBlock = AssistantBlock | ToolBlock | FinalBlock`
- Produces `buildResearchConversation(events: ResearchEvent[], result: ResearchResult | null): ResearchConversationBlock[]`
- Tool pairs are matched by safe event order and tool name; unknown tools receive the public label `查询研究数据`.

- [ ] **Step 1: Write failing reducer tests**

```typescript
expect(buildResearchConversation([
  event(1, "assistant_delta", { segment_id: "s1", delta: "先查行情。" }),
  event(2, "tool_started", { tool: "market_snapshot" }),
  event(3, "tool_completed", { tool: "market_snapshot", evidence_count: 8 }),
  event(4, "assistant_delta", { segment_id: "s2", delta: "行情显示估值偏低。" }),
  event(5, "assistant_final", { summary: "结论", conclusions: [], risks: [] }),
], null)).toEqual([
  { kind: "assistant", id: "s1", text: "先查行情。" },
  expect.objectContaining({ kind: "tool", status: "completed" }),
  { kind: "assistant", id: "s2", text: "行情显示估值偏低。" },
  expect.objectContaining({ kind: "final", summary: "结论" }),
]);
```

Add literal tests proving `thinking_delta` and `text_delta` are ignored and legacy `result` creates one final block only when no `assistant_final` exists.

- [ ] **Step 2: Run reducer tests and verify RED**

Run: `node node_modules/vitest/vitest.mjs run src/lib/__tests__/researchConversation.test.ts`

Expected: FAIL because the reducer does not exist.

- [ ] **Step 3: Implement typed blocks and safe tool presentation**

Use a small explicit map:

```typescript
const TOOL_LABELS: Record<string, string> = {
  market_snapshot: "查询股票行情",
  financial_statement: "读取财务数据",
  company_announcements: "检索公司公告",
};
```

Never copy arbitrary argument values into the collapsed label. Limit expanded metadata to evidence count, elapsed time, and sanitized failure status.

- [ ] **Step 4: Run reducer tests and verify GREEN**

Run: `node node_modules/vitest/vitest.mjs run src/lib/__tests__/researchConversation.test.ts`

Expected: all reducer tests pass.

- [ ] **Step 5: Commit reducer**

```bash
git add frontend/src/lib/researchConversation.ts frontend/src/lib/researchApi.ts frontend/src/lib/__tests__/researchConversation.test.ts
git commit -m "feat: reduce research events into chat blocks"
```

### Task 4: Render the GPT-Style Dynamic Agent Chat

**Files:**
- Modify: `frontend/src/components/public/AIAnalysisTimeline.tsx`
- Modify: `frontend/src/components/public/__tests__/AIAnalysisTimeline.test.tsx`
- Modify: `frontend/src/pages/public/LandingPage.tsx`
- Test: `frontend/src/pages/public/__tests__/LandingPage.test.tsx`

**Interfaces:**
- Consumes: `buildResearchConversation`
- Renders ordered assistant prose, compact tool rows, verified final Markdown-like content, and a streaming cursor.

- [ ] **Step 1: Replace progress-list expectations with failing Agent-order tests**

Render events in this exact order and assert DOM order with `compareDocumentPosition`:

```typescript
expect(textNode.compareDocumentPosition(toolNode) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(toolNode.compareDocumentPosition(nextTextNode) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(nextTextNode.compareDocumentPosition(finalNode) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
expect(screen.queryByText("internal English reasoning")).not.toBeInTheDocument();
```

Add tests for tool expansion, running cursor, failure retention, and legacy completed tasks.

- [ ] **Step 2: Run component tests and verify RED**

Run: `node node_modules/vitest/vitest.mjs run src/components/public/__tests__/AIAnalysisTimeline.test.tsx src/pages/public/__tests__/LandingPage.test.tsx`

Expected: FAIL because the current timeline renders fixed activity and raw thinking segments.

- [ ] **Step 3: Implement the selected ChatGPT visual target**

Use a responsive centered reading column (`w-full max-w-[840px]`, `px-4 sm:px-6`), keep user messages as right gray bubbles, and render assistant blocks as unboxed prose. Tool rows use one compact neutral button row with `ChevronRight/Down`, monochrome icons, localized label, status, and optional safe details.

Remove `ProcessTimeline`, `ThinkingSegment`, `safeActivity`, and all rendering of `thinking_delta`. Render final summary, conclusions, risks, and existing candidate links as continuous assistant content rather than a separate dashboard card.

- [ ] **Step 4: Preserve live auto-scroll without stealing manual scroll**

Add a scroll-container ref and bottom sentinel in `LandingPage`. Scroll on new blocks only when the user is within 120px of the bottom; once the user scrolls upward, keep their position until they return near the bottom.

- [ ] **Step 5: Run component tests and verify GREEN**

Run: `node node_modules/vitest/vitest.mjs run src/components/public/__tests__/AIAnalysisTimeline.test.tsx src/pages/public/__tests__/LandingPage.test.tsx`

Expected: all chat and page tests pass.

- [ ] **Step 6: Commit frontend Agent chat**

```bash
git add frontend/src/components/public/AIAnalysisTimeline.tsx frontend/src/components/public/__tests__/AIAnalysisTimeline.test.tsx frontend/src/pages/public/LandingPage.tsx frontend/src/pages/public/__tests__/LandingPage.test.tsx
git commit -m "feat: render dynamic research agent chat"
```

### Task 5: End-to-End Verification and Visual QA

**Files:**
- Modify: `design-qa.md`
- Create: `.qa-artifacts/agent-chat-after/` screenshots

**Interfaces:**
- Verifies backend event contract, frontend build, live Web interaction, replay, and responsive visual fidelity.

- [ ] **Step 1: Run backend focused and regression tests**

Run:

```bash
python -m pytest agent/tests/test_research_public_updates.py agent/tests/test_research_agent_runtime.py agent/tests/test_research_task_api.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend focused tests, typecheck, and Web build**

Run with Node 24.13.1:

```powershell
& 'C:\Users\Lenovo\AppData\Roaming\fnm\node-versions\v24.13.1\installation\node.exe' node_modules\vitest\vitest.mjs run src/lib/__tests__/researchConversation.test.ts src/components/public/__tests__/AIAnalysisTimeline.test.tsx src/pages/public/__tests__/LandingPage.test.tsx
& 'C:\Users\Lenovo\AppData\Roaming\fnm\node-versions\v24.13.1\installation\node.exe' node_modules\typescript\bin\tsc -b
& 'C:\Users\Lenovo\AppData\Roaming\fnm\node-versions\v24.13.1\installation\node.exe' node_modules\vite\bin\vite.js build --mode web
```

Expected: tests, typecheck, and build exit 0.

- [ ] **Step 3: Verify a live conversation in the in-app browser**

At 1440×900, submit a real research question and verify the visible order is model reply, tool, model reply, tool, final reply. Refresh the completed conversation and verify the order is unchanged. Repeat at 390×844 and verify the composer remains visible and tool rows do not overflow.

- [ ] **Step 4: Compare the selected mockup and implementation screenshots**

Capture identical desktop and mobile states, inspect both files, and record P0–P3 differences in `design-qa.md`. Fix all P0/P1/P2 issues and repeat until the report contains `final result: passed`.

- [ ] **Step 5: Commit verification artifacts and report**

```bash
git add design-qa.md
git commit -m "test: verify web research agent chat"
```
