# SigmX Total Architecture Evidence Matrix

This is the strict completion gate for `2026-08-15-sigmx-product-architecture-design.md`.

The previous matrix equated routes, files, narrow tests, and adapter DTOs with completed product behavior. That assessment was invalid. The authoritative inventory is now `sigmx-product-requirements.json`, audited by `scripts/verify_product_architecture.py`.

## Evidence rules

- `complete`: both executable test evidence and current runtime/browser/package evidence exist.
- `indirect`: implementation or test files exist, but do not directly prove the complete user-facing requirement.
- `missing`: no evidence exists or the declared evidence is absent.
- Real payment is excluded by the explicit personal-product scope decision; activation-code commerce remains required.

## Current baseline

Run:

```powershell
python scripts/verify_product_architecture.py
```

At this baseline, no product-architecture row is marked complete. Existing implementation files are retained as indirect evidence and missing product behavior is represented without evidence. Runtime evidence will be added only after the corresponding vertical slice passes browser, API, SDK, or packaged-Desktop verification.

## Known critical gaps

1. Web and Desktop still share one Vite application and runtime route filtering.
2. Public instrument/search pages lack the full data, quality, event, risk, and action model.
3. `/me` lacks an authoritative today view, query history, cloud task state, and device presence.
4. Harness runs are read-only adapters over unrelated stores, not an authoritative runtime model.
5. Data Hub response quality/version/normalization contracts are not consistently enforced.
6. Data Hub console and operations UI are dense partial pages rather than complete workflows.
7. Retention, Desktop, data-quality, commercial, and margin metrics are incomplete.
8. The production artifacts have not proved independent Web/Desktop boundaries.

This matrix must not be manually promoted based on intent or file existence. Update the manifest with direct evidence paths only after executing the relevant completion gate.
