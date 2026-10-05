# Design QA — 情报搜索、全球事件与投研 Skills

## Scope

- Source references: `exec-843f08c9-24e1-4952-b325-5d8a2c9f8b38.png` and `exec-24b3de1b-04dd-475d-8253-31fe305bb82b.png`.
- Prototype routes: `/intelligence`, `/global-events`, `/skills`.
- Verification viewport: 1440 × 900.
- Existing `PublicLayout` header, navigation, footer and route shell were preserved.
- Second-pass refinement places the title/subtitle and search on one compact row at desktop widths; both search fields are 40px high and page headings are 24px.

## Visual comparison

### 情报搜索

- Compact title and search row aligns with the two adjacent research pages.
- Editorial feed uses source/time metadata, restrained actions and a sticky overview panel instead of a heavy dashboard card.
- Degraded-source warnings are converted to concise user-facing copy and no longer expose transport exceptions.
- Live results are limited to ten initially with a load-more control.

### 全球事件

- Title, subtitle, search, restrained filter chips, editorial timeline, inline AI summary and right-side market-impact panel match the selected content-area reference.
- Real API data is denser and may contain English source titles; first render is limited to eight events with an explicit load-more control.
- Responsive behavior moves the impact panel below the timeline before the wide breakpoint.

### 投研 Skills

- Title, search, category tabs, two featured cards and three-column library match the selected content-area reference.
- Cards use the live published-skill manifest rather than invented catalog entries.
- First render is limited to twelve library cards with an explicit load-more control; search and category interactions remain functional.

## Interaction and quality checks

- Search inputs, category controls, detail navigation, event evidence drawer and AI-analysis handoff remain active.
- No browser console errors on either route.
- No clipping or horizontal overflow at 1440 × 900.
- Primary content begins substantially higher in the viewport; compact controls preserve clear hierarchy without crowding.
- P0/P1/P2 visual issues: none remaining.
- P3 note: source event titles are shown verbatim, so language and title length vary more than in the visual reference.

## Result

final result: passed

---

# Design QA — AI 发现聊天区

## Evidence

- Source visual truth: `C:/Users/Lenovo/AppData/Local/Temp/codex-clipboard-24341e8e-7a9a-4b24-875c-d5ddadead703.png`.
- Implementation capture: `E:/gwj/SigmX/.qa-artifacts/ai-chat-after-1920.png`.
- Viewport and normalization: source 1920 × 879 px; implementation 1920 × 879 CSS px, device pixel ratio 1, 1920 × 879 px. No density normalization required.
- State: wide desktop, light theme, one running conversation with two model reply segments, a completed tool activity, a failed tool activity, history sidebar, and follow-up composer.
- Full-view comparison: the focused AI workspace was compared at equal dimensions. The public header is intentionally excluded from the isolated component capture because this change does not modify it.
- Focused-region evidence: conversation column, tool activity rows, sidebar, and bottom composer were all legible in the full-size equal-dimension capture; no additional crop was required.

## Comparison history

- Earlier P1: model text and tool rows stretched across the full workspace, producing weak reading hierarchy. Fixed by aligning the conversation and composer to an 820px centered reading column.
- Earlier P1: `tool_call` plus `tool_started` created duplicate “加载研究方法” rows. Fixed by pairing the started event with the existing running activity.
- Earlier P2: the secondary “AI 发现” title bar consumed vertical space and duplicated the active top navigation label. Removed from the workspace shell.
- Earlier P2: full-width shaded tool rows looked like a data table. Replaced with compact, content-width Agent activity lines and restrained expandable metadata.
- Post-fix evidence: `ai-chat-after-1920.png` shows one activity per operation, continuous model prose, compact vertical rhythm, and composer alignment with the response column.

## Required fidelity surfaces

- Fonts and typography: retained the product font stack; model prose is 15px with 1.8 line-height and slightly tightened tracking; tool metadata is subordinate at 11–12px.
- Spacing and layout rhythm: conversation begins near the top of the workspace, uses 32px turn rhythm, and no longer contains the large blank band visible in the source issue capture.
- Colors and tokens: retained neutral zinc product tokens; user messages use a quiet zinc-100 surface and tools use low-contrast semantic status icons.
- Image quality and assets: no raster imagery is part of the chat surface; existing brand and Lucide icon assets remain sharp at native scale.
- Copy and content: model text remains primary; tool labels and statuses are concise, Chinese, and no fixed research-plan copy is introduced.

## Findings

- No actionable P0/P1/P2 findings remain for the scoped AI chat workspace.
- P3: very long model paragraphs may benefit from Markdown paragraph/list rendering in a later content-formatting pass.

## Interaction checks

- Tool activity expand/collapse remains interactive.
- Running cursor, failure status, retry state, history selection, and composer controls remain covered by automated component tests.
- Duplicate tool lifecycle events are covered by a reducer regression test.

final result: passed
