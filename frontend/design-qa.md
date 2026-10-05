# Design QA — Web Research + Data Hub

## Evidence

- Web Research source: `C:/Users/Lenovo/.codex/generated_images/01a02e09-e6ac-7542-aac7-7752f7cd817e/exec-783ed4e7-ae70-41ed-b7e9-ac116eb85bf6.png` (1487×1058)
- Web Research implementation: `E:/gwj/SigmX/artifacts/web-research-dual-mode.png` (905×701)
- Intelligence state: `E:/gwj/SigmX/artifacts/web-research-intelligence.png` (905×701)
- Data Hub source: `C:/Users/Lenovo/.codex/generated_images/01a02e09-e6ac-7542-aac7-7752f7cd817e/exec-b35d16e7-95d2-47cc-a5db-50673518c47c.png` (1487×1058)
- Data Hub implementation: `E:/gwj/SigmX/artifacts/data-hub-observatory-v2.png` (905×701)
- Comparisons: `E:/gwj/SigmX/artifacts/compare-web-research.png`, `E:/gwj/SigmX/artifacts/compare-data-hub.png`
- Viewport/state: 905×701 CSS px, scale 1, signed in as `admin@sigmx.local`, light theme.
- Normalization: each source was top-aligned, cropped and downsampled to the implementation viewport for side-by-side inspection.

## Fidelity surfaces

- Typography: existing SigmX system font, compact sizes and tabular numbers preserve the selected targets' financial-tool hierarchy. P3 difference: source mock is slightly denser at 1440px.
- Layout rhythm: both pages use the intended pulse/search/workspace hierarchy. At 905px, secondary API preview intentionally moves below the Data Hub catalog; at 1280px it becomes the third column.
- Colors and tokens: existing primary teal, success green, neutral surfaces and borders align with both selected targets.
- Image/assets: neither target needs raster imagery. Existing logo and project-standard Lucide icons remain sharp and consistent; there are no placeholder assets.
- Copy/content: realistic Chinese A-share fixtures, sources, timestamps, affected companies, coverage, quality and SLA are present; all fixtures are labeled as demonstration data.

## Comparison history

1. Initial Data Hub capture stacked every region because this Tailwind build did not emit arbitrary grid-template utilities. P2: the dataset catalog fell below the first viewport.
2. Fix: added an explicit responsive Data Hub grid in `index.css`: two columns at 768px and three columns at 1280px.
3. Post-fix evidence: `data-hub-observatory-v2.png` shows classification and catalog together with no page-level horizontal overflow.
4. Web Research required no P0/P1/P2 visual correction after capture. The 905px adaptation preserves the selected target's dual-mode composer and candidate workspace.

## Primary interactions verified

- AI 发现 / 情报搜索 mode switching.
- Intelligence event conversion into a populated AI stock-screen query.
- Research query routing and candidate evidence drawer.
- Data Hub category and dataset selection.
- Python/cURL example switching.
- Online API test state: `200 OK · 128ms · 返回 2 条记录`.

## Follow-up polish

- P3: add a compact Data Hub preview drawer at sub-1280px widths so the API preview can open without scrolling.
- P3: connect demonstration timestamps and health metrics to live backend status when service work enters scope.

## Final result

passed
