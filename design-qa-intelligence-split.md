# Design QA — AI 发现 / 情报搜索拆页

**Evidence**

- Source visual truth: `C:\Users\Lenovo\.codex\generated_images\01a02e09-e6ac-7542-aac7-7752f7cd817e\exec-90ef1390-5b64-4a38-a8b4-ed5c440d464a.png`
- Browser-rendered AI Discover: `E:\gwj\SigmX\artifacts\ai-discovery-split.png`
- Browser-rendered Intelligence Search: `E:\gwj\SigmX\artifacts\intelligence-search-split.png`
- Side-by-side comparison: `E:\gwj\SigmX\artifacts\intelligence-search-comparison.png`
- Source pixels: 1487 × 1058. Implementation pixels/CSS viewport: 905 × 701 at device scale 1. The full views were proportionally fit side-by-side; no pixel-perfect density claim is made.
- State: authenticated public web shell, intelligence feed loaded, default “全部” filter selected.

**Findings**

- No actionable P0/P1/P2 regressions from the route split. AI 发现 and 情报搜索 now have separate page identities, inputs, result structures, and navigation destinations.
- Typography: Chinese UI hierarchy, weights, line lengths, and compact metadata remain consistent with the selected visual direction.
- Spacing/layout: the first browser pass exposed excessive vertical height around intelligence CTAs at the 905 px viewport. The feed switched to its two-column layout at the medium breakpoint; the post-fix capture shows compact, aligned rows.
- Colors/tokens: the teal primary, neutral surfaces, borders, muted copy, relevance green, and status treatments remain consistent.
- Image/assets: no content imagery is required by this information-dense screen. Existing SigmX brand and icon-library assets remain sharp.
- Copy/content: the page consistently frames intelligence as source-backed investment-impact search. AI Discover copy is absent from the feed body except for the explicit conversion action.

**Primary Interactions Tested**

- Top navigation opens distinct `/` and `/intelligence` destinations.
- “生成选股条件” navigates to a linkable `/?q=...` AI Discover state.
- Converted query is prefilled correctly and the destination resets to the top of the page.
- Browser console checked after the conversion path: no warnings or errors.

**Comparison History**

- P2: intelligence rows became too tall below the large breakpoint because the CTA occupied a separate row.
- Fix: moved the two-column result layout breakpoint from `lg` to `md`.
- Post-fix evidence: `artifacts/intelligence-search-split.png`; result titles, metadata, and conversion CTAs remain aligned above the fold.

**Implementation Checklist**

- [x] Separate navigation and route boundaries.
- [x] Independent page search states and content.
- [x] Cross-page intelligence-to-discovery conversion.
- [x] Desktop browser rendering and console check.
- [x] Responsive density correction.

**Follow-up Polish**

- P3: on very narrow mobile widths, the four intelligence filters could become a horizontally scrollable single row instead of wrapping.

final result: passed
