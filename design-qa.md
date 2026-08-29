# AI Discovery ChatGPT-style Design QA

- Source visual truth: `artifacts/ai-discovery-chatgpt-qa/reference-chatgpt.png`
- Implementation screenshot: `artifacts/ai-discovery-chatgpt-qa/implementation-desktop.png`
- Combined comparison: `artifacts/ai-discovery-chatgpt-qa/comparison-desktop.png`
- Mobile evidence: `artifacts/ai-discovery-chatgpt-qa/implementation-mobile.png`
- Browser URL: `http://localhost:5900/`
- Desktop CSS viewport reported by browser: 1186 × 706; captured pixels: 1181 × 702
- Mobile CSS viewport: 390 × 844; captured pixels: 385 × 832
- Source pixels: 1586 × 992
- Density normalization: source and implementation were placed at native pixel size in one horizontal comparison; composition was judged proportionally because the source mock and connected browser expose different pixel widths.
- State: source shows completed analysis; implementation screenshot shows the empty/new-analysis state. Shared shell, history rail, header, composer, typography, spacing, and palette were compared. Completed, planning, running, and error content structures are covered by component tests; visual state coverage remains a follow-up.

## Full-view comparison evidence

The combined image confirms the implementation follows the selected direction: warm-white main canvas, restrained light-gray sidebar, narrow centered conversation column, plain-text history rows, minimal header, low-shadow rounded composer, quiet disclaimer, and no model/provider/API details. The existing SigmX public navigation remains above the page as an intentional product-shell constraint.

## Focused region evidence

No separate crops were required because the full comparison keeps the sidebar, center column, and composer text legible. The composer and history were also checked interactively in the browser; mobile input remains in-view and the history drawer opens.

## Required fidelity surfaces

- Typography: Chinese system sans-serif, restrained 14–15px UI/body scale, clear 24px empty-state heading, readable line height. Passed.
- Spacing/layout: 240px sidebar, centered 820px conversation/composer width, consistent 8px-derived rhythm, fixed visible composer. Passed.
- Colors/tokens: near-white canvas, `#f7f7f8` sidebar, zinc neutrals, limited dark/teal emphasis. Passed.
- Image/assets: no raster imagery is required by the selected design; existing Lucide interface icons are appropriate and sharp. Passed.
- Copy/content: “AI 发现”, “搜索对话”, “给 AI 发现发送消息”, and investment disclaimer match the selected direction. Passed.

## Findings

- [P3] Existing public navigation is visible above the page while the isolated mock starts at the AI surface. This is intentional because the production route lives inside `PublicLayout`; removing it would alter site-wide navigation.
- [P3] The empty-state screenshot cannot visually prove completed-result density. Component tests cover the exact completed/result DOM and navigation, but a future visual-fixture route would make screenshot regression stronger.

## Interaction and accessibility checks

- New analysis, history links, template prompts, composer submission, mobile history drawer, plan confirmation, retry, stock links, and full-analysis link retain accessible names.
- Mobile composer measured fully inside the viewport.
- Fresh browser tab reported no console warnings or errors.
- Screenshot evidence cannot establish full keyboard order, screen-reader announcements, or WCAG compliance.

## Comparison history

1. Initial implementation used card-heavy messages and a framed application shell.
2. Rebuilt shell and timeline to remove large cards, dark user bubbles, repeated status metadata, and heavy shadows.
3. Post-fix evidence shows the ChatGPT-style sidebar, conversation canvas, typography, and composer with no actionable P0/P1/P2 mismatch.

final result: passed
