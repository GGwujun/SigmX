# Progressive Personal Plan Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the four personal plans into a strictly increasing Free → Desktop Pro → Data Pro → Pro Bundle entitlement ladder without breaking historical `data_developer` references.

**Architecture:** Keep stable plan codes and the existing catalog API, but update the canonical catalog and add an idempotent migration for old official rows. Enforce inheritance in the product layer, then render a concise progressive card row plus a complete comparison table from the server-provided catalog.

**Tech Stack:** Python 3.11+, SQLite, FastAPI/Pydantic, React 18, TypeScript, Tailwind CSS, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-progressive-plan-catalog-design.md`

## Global Constraints

- Stable codes remain `free`, `desktop_pro`, `data_developer`, and `pro_bundle`.
- Public name `Data Developer` becomes `Data Pro`; historical orders and activation codes keep `data_developer`.
- Prices are 0, 26800, 39800, and 51800 CNY fen per quarter/order period.
- Every later plan contains every earlier boolean and dataset entitlement and has no lower numeric quota.
- `datahub.commercial_use` remains false for all personal plans.
- Existing order price and entitlement snapshots are never rewritten.
- `/api/catalog/plans` response shape remains unchanged.

---

### Task 1: Canonical progressive catalog and inheritance contract

**Files:**
- Modify: `agent/src/product/catalog.py`
- Modify: `agent/tests/test_product_store.py`

**Interfaces:**
- Consumes: existing `PlanSeed` and `DEFAULT_CATALOG`.
- Produces: `validate_progressive_catalog(plans: list[PlanSeed]) -> None`, called at module load and reusable by admin validation.

- [ ] **Step 1: Write failing catalog tests**

Add assertions that `data_developer` is named `Data Pro`, costs `39800`, enables Desktop and cloud AI, grants 700 monthly research credits, two devices, and includes every Desktop Pro dataset. Add a table-driven inheritance test over booleans, dataset sets, and numeric quota keys.

- [ ] **Step 2: Run the focused tests and verify the old catalog fails**

Run: `uv run --with pytest pytest agent/tests/test_product_store.py -q`

Expected: failures for the old Data Developer price/name and its disabled Desktop/AI entitlements.

- [ ] **Step 3: Update the four canonical seeds**

Set Data Pro to:

```python
"name_zh": "Data Pro",
"price_cny_fen": 39_800,
"monthly_credits": 700,
"description": "完整个人投研能力，增加标准行情与财务数据接口",
"desktop.connected_mode": True,
"desktop.device_limit": 2,
"cloud_ai.enabled": True,
"cloud_ai.concurrent_jobs": 3,
"reports.cloud_history": True,
```

Keep its 100,000 Data Hub monthly quota and market/finance datasets. Ensure Pro Bundle remains greater than or equal to Data Pro for every inherited key.

- [ ] **Step 4: Add the catalog validator**

Implement a validator that compares adjacent seeds. It raises `ValueError` with the plan code and entitlement key when booleans regress, dataset groups are not supersets, or positive numeric quotas decrease. Invoke it once for `DEFAULT_CATALOG` after construction.

- [ ] **Step 5: Run the catalog tests**

Run: `uv run --with pytest pytest agent/tests/test_product_store.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add agent/src/product/catalog.py agent/tests/test_product_store.py
git commit -m "refactor product catalog into progressive plans"
```

### Task 2: Idempotent migration of existing official catalog rows

**Files:**
- Modify: `agent/src/product/store.py`
- Modify: `agent/tests/test_product_store.py`
- Modify: `agent/tests/test_product_devices.py`
- Modify: `agent/tests/test_data_hub_entitlements.py`

**Interfaces:**
- Consumes: `DEFAULT_CATALOG`, `to_seed_row(seed)`.
- Produces: `ProductStore._migrate_progressive_catalog(conn: sqlite3.Connection) -> None` executed during schema initialization.

- [ ] **Step 1: Write failing migration tests**

Create a database, replace `data_developer` with the old official row, reopen the store, and assert it becomes Data Pro with Desktop, AI, two devices, and price 39800. Reopen a second time and assert the row is unchanged. Insert an order snapshot at 19800 before migration and assert that snapshot remains 19800 afterward.

- [ ] **Step 2: Update entitlement behavior tests**

Replace `test_data_developer_does_not_unlock_desktop` with a test that activates the stable `data_developer` code and successfully authorizes up to two devices. Keep tests proving it cannot access `pro.v1`.

- [ ] **Step 3: Run focused tests and verify failure**

Run: `uv run --with pytest pytest agent/tests/test_product_store.py agent/tests/test_product_devices.py agent/tests/test_data_hub_entitlements.py -q`

Expected: failures because existing rows are not updated and Data Developer still blocks Desktop.

- [ ] **Step 4: Implement transactional migration**

During store initialization, detect the old official `data_developer` signature (`name_zh='Data Developer'`, price 19800, or both Desktop and cloud AI disabled). Replace only that canonical row using the new seed. Do not update orders, activation codes, subscriptions, or noncanonical codes. Execute inside the existing schema transaction.

- [ ] **Step 5: Run focused migration and entitlement tests**

Run the command from Step 3 and expect all tests to pass.

- [ ] **Step 6: Commit**

```bash
git add agent/src/product/store.py agent/tests/test_product_store.py agent/tests/test_product_devices.py agent/tests/test_data_hub_entitlements.py
git commit -m "migrate existing users to progressive plan entitlements"
```

### Task 3: Progressive pricing page

**Files:**
- Modify: `frontend/src/pages/public/PricingPage.tsx`
- Create: `frontend/src/pages/public/__tests__/PricingPage.test.tsx`

**Interfaces:**
- Consumes: unchanged `getPlans() -> Promise<PlanView[]>`.
- Produces: a server-driven card ladder and complete entitlement comparison table.

- [ ] **Step 1: Write failing UI tests**

Mock the complete four-plan catalog. Assert the order Free, Desktop Pro, Data Pro, Pro Bundle; assert cards two through four contain “包含上一档全部权益”; assert exactly one “进阶推荐” badge on Data Pro and one “最高配置” badge on Pro Bundle; assert the comparison table renders AI monthly use, Data Hub monthly use, devices, datasets, and history depth.

- [ ] **Step 2: Run the test and verify failure**

Run: `npm test -- --run src/pages/public/__tests__/PricingPage.test.tsx --pool=threads --maxWorkers=1`

Expected: failure because the current page renders standalone repetitive cards and no progression markers.

- [ ] **Step 3: Implement concise progressive cards**

Sort plans by `sort_order`. Change the heading to “从体验到专业研究，权益逐级增加”. Each card shows price, positioning, predecessor inclusion, and only these core values: monthly AI use, monthly Data Hub use, devices, dataset scope. Apply the recommended badge to Data Pro and the highest-tier badge to Pro Bundle.

- [ ] **Step 4: Implement the complete comparison table**

Below the cards, render one row per recognized entitlement key and one column per plan. Reuse `quotaLabel`; add a label for monthly AI research credits from `plan.monthly_credits`. Preserve the signed-in management link behavior.

- [ ] **Step 5: Run UI tests and typecheck**

Run:

```bash
npm test -- --run src/pages/public/__tests__/PricingPage.test.tsx --pool=threads --maxWorkers=1
npm run typecheck
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/public/PricingPage.tsx frontend/src/pages/public/__tests__/PricingPage.test.tsx
git commit -m "redesign pricing as a progressive plan ladder"
```

### Task 4: Unified current-plan presentation

**Files:**
- Modify: `frontend/src/components/layout/ProductStatus.tsx`
- Modify: `frontend/src/pages/account/SubscriptionPage.tsx`
- Create: `frontend/src/components/layout/__tests__/ProductStatus.test.tsx`

**Interfaces:**
- Consumes: `getMyEntitlements()`, `getMyCredits()`, and `getPlans()`.
- Produces: current Chinese plan name, `currentIndex/4` ladder position, and unified entitlement cards.

- [ ] **Step 1: Write failing current-plan tests**

Mock a `data_developer` subscription and assert “Data Pro”, “第 3/4 档”, AI research available use, 100,000 Data Hub monthly use, two devices, and market/finance dataset names appear. Assert the raw code `data_developer` does not appear.

- [ ] **Step 2: Run the test and verify failure**

Run: `npm test -- --run src/components/layout/__tests__/ProductStatus.test.tsx --pool=threads --maxWorkers=1`

Expected: failure because the component has no ladder position or dataset summary.

- [ ] **Step 3: Implement unified presentation**

Build the ordered plan-name map from the catalog response. Add a compact progress strip with four labeled steps and highlight the current code. Keep the four summary cards, rename generic units to “套餐内 AI 研究用量”, and add a dataset/history detail row below them.

- [ ] **Step 4: Run component tests and typecheck**

Run:

```bash
npm test -- --run src/components/layout/__tests__/ProductStatus.test.tsx --pool=threads --maxWorkers=1
npm run typecheck
```

Expected: both commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/ProductStatus.tsx frontend/src/pages/account/SubscriptionPage.tsx frontend/src/components/layout/__tests__/ProductStatus.test.tsx
git commit -m "show unified progressive plan benefits"
```

### Task 5: Full regression and browser acceptance

**Files:**
- Modify only if a regression demonstrates a requirement violation.

**Interfaces:**
- Consumes: completed Tasks 1–4.
- Produces: verified local catalog, pricing page, and subscription page.

- [ ] **Step 1: Run backend product regression**

Run: `uv run --with pytest pytest agent/tests/test_product_store.py agent/tests/test_product_routes.py agent/tests/test_product_devices.py agent/tests/test_data_hub_entitlements.py agent/tests/test_datahub_monthly_grants.py agent/tests/test_datahub_gateway.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend regression and build checks**

Run:

```bash
npm test -- --run src/pages/public/__tests__/PricingPage.test.tsx src/components/layout/__tests__/ProductStatus.test.tsx src/pages/account/__tests__ --pool=threads --maxWorkers=1 --testTimeout=20000
npm run typecheck
```

Expected: all tests pass and TypeScript exits 0.

- [ ] **Step 3: Browser acceptance**

Open `/pricing` and verify the four cards form a left-to-right ladder, Data Pro is the sole recommended tier, and the table is readable at desktop width. Log in, open `/account/subscription`, and verify the Chinese name, third-of-four position, inherited Desktop entitlement, datasets, and quotas.

- [ ] **Step 4: Commit any acceptance-only fixes**

If Step 3 required a source fix, commit only those verified files with message `fix progressive plan acceptance issues`. If no fix was required, do not create an empty commit.
