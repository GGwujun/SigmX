# Product Boundary Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser experience land on a lightweight `/me` product home, keep commercial settings under `/account/*`, and preserve the full `/app` Financial Harness exclusively for Desktop.

**Architecture:** Keep the existing React bundle and runtime `isDesktopMode()` detection. Add a focused portal home and a shared product-navigation model, then update redirects so browser users never fall into the Desktop workbench while Desktop users retain the existing `Layout`. No backend schema or API changes are required in this phase.

**Tech Stack:** React 19, TypeScript 5.7, React Router 7, Tailwind CSS 3, Vitest 4, Testing Library.

## Global Constraints

- Browser login and registration land on `/me`; Desktop login and registration land on `/app`.
- `/portal` remains as a compatibility alias and redirects to `/me`.
- Browser access to any Desktop-only route redirects to `/me`.
- `/me` is a product-status and cloud-asset home; `/account/*` remains the commercial and security area.
- Existing account, admin and Desktop routes remain backward compatible.
- The phase does not add natural-language query execution, SSR, new Data Hub billing APIs, organizations, real payment or live trading.
- All new user-facing copy keeps the investment-risk boundary explicit and does not imply guaranteed returns.

---

## File Map

- Create `frontend/src/components/navigation/productNavigation.ts`: one source of truth for the three public product entries.
- Create `frontend/src/components/portal/PortalNav.tsx`: authenticated browser navigation between `/me` and `/account` plus product links.
- Create `frontend/src/components/portal/__tests__/PortalNav.test.tsx`: active/link behavior tests.
- Create `frontend/src/pages/portal/MePage.tsx`: lightweight browser product home using existing entitlement, credit, usage and device APIs.
- Create `frontend/src/pages/portal/__tests__/MePage.test.tsx`: loading, success and partial-failure tests.
- Modify `frontend/src/components/public/PublicLayout.tsx`: consume the shared product navigation and expose AI 选股 as a disabled “即将上线” product marker without inventing a route.
- Modify `frontend/src/components/portal/PortalLayout.tsx`: render `PortalNav`, make the logo target `/me`, and keep admin/logout behavior.
- Modify `frontend/src/lib/desktop.ts`: change the browser post-login target to `/me`.
- Modify `frontend/src/router.tsx`: register `/me`, redirect `/portal` and Desktop-only browser traffic to `/me`.
- Modify existing tests in `frontend/src/lib/__tests__/desktop.test.ts`, `frontend/src/pages/auth/__tests__/LoginPage.test.tsx`, `frontend/src/router/__tests__/DesktopOnly.test.tsx`, and `frontend/src/components/portal/__tests__/PortalLayout.test.tsx`.

---

### Task 1: Lock Browser and Desktop Routing Boundaries

**Files:**
- Modify: `frontend/src/lib/desktop.ts`
- Modify: `frontend/src/router.tsx`
- Test: `frontend/src/lib/__tests__/desktop.test.ts`
- Test: `frontend/src/pages/auth/__tests__/LoginPage.test.tsx`
- Test: `frontend/src/router/__tests__/DesktopOnly.test.tsx`

**Interfaces:**
- Consumes: `window.sigmxDesktop?.isDesktop: boolean | undefined`.
- Produces: `postLoginTarget(): "/app" | "/me"`; `DesktopOnly` redirect behavior; compatibility redirect `/portal -> /me`.

- [ ] **Step 1: Change the unit expectations before implementation**

Update the browser assertions to use `/me`:

```ts
expect(isDesktopMode()).toBe(false);
expect(postLoginTarget()).toBe("/me");
```

In `LoginPage.test.tsx`, replace the browser route fixture and assertion:

```tsx
<Route path="/me" element={<div>portal-home</div>} />
expect(await screen.findByText("portal-home")).toBeInTheDocument();
```

In `DesktopOnly.test.tsx`, use `/me` as the redirect target:

```tsx
<Route path="/me" element={<div>portal-redirect-target</div>} />
```

- [ ] **Step 2: Run the focused tests and verify the old `/portal` behavior fails**

Run:

```powershell
npm test -- --run src/lib/__tests__/desktop.test.ts src/pages/auth/__tests__/LoginPage.test.tsx src/router/__tests__/DesktopOnly.test.tsx
```

Expected: failures show browser navigation still targets `/portal`.

- [ ] **Step 3: Implement the minimal redirect change**

In `desktop.ts`:

```ts
export function postLoginTarget(): "/app" | "/me" {
  return isDesktopMode() ? "/app" : "/me";
}
```

In `DesktopOnly`:

```tsx
if (!isDesktopMode()) {
  return <Navigate to="/me" replace />;
}
```

In the route table, replace the compatibility alias:

```tsx
{ path: "/portal", element: <Navigate to="/me" replace /> },
```

- [ ] **Step 4: Run the focused tests**

Run the command from Step 2.

Expected: all focused tests pass.

- [ ] **Step 5: Commit the routing boundary**

```powershell
git add frontend/src/lib/desktop.ts frontend/src/router.tsx frontend/src/lib/__tests__/desktop.test.ts frontend/src/pages/auth/__tests__/LoginPage.test.tsx frontend/src/router/__tests__/DesktopOnly.test.tsx
git commit -m "feat(frontend): route browser users to product home"
```

---

### Task 2: Add Shared Three-Product Navigation

**Files:**
- Create: `frontend/src/components/navigation/productNavigation.ts`
- Create: `frontend/src/components/portal/PortalNav.tsx`
- Create: `frontend/src/components/portal/__tests__/PortalNav.test.tsx`
- Modify: `frontend/src/components/public/PublicLayout.tsx`
- Modify: `frontend/src/components/portal/PortalLayout.tsx`
- Modify: `frontend/src/components/portal/__tests__/PortalLayout.test.tsx`

**Interfaces:**
- Produces: `PUBLIC_PRODUCT_LINKS: readonly ProductNavigationItem[]` and `PortalNav(): JSX.Element`.
- `ProductNavigationItem` is `{ to: string; label: string; description: string }`.
- `PortalLayout` consumes `PortalNav` and continues to own admin and logout controls.

- [ ] **Step 1: Write failing portal navigation tests**

Create `PortalNav.test.tsx` with assertions for the product home, account center and public product links:

```tsx
render(
  <MemoryRouter initialEntries={["/me"]}>
    <PortalNav />
  </MemoryRouter>,
);

expect(screen.getByRole("link", { name: "我的 SigmX" })).toHaveAttribute("href", "/me");
expect(screen.getByRole("link", { name: "账户中心" })).toHaveAttribute("href", "/account");
expect(screen.getByRole("link", { name: "Data Hub" })).toHaveAttribute("href", "/product/data-hub");
expect(screen.getByRole("link", { name: "Desktop" })).toHaveAttribute("href", "/product/desktop");
```

Update `PortalLayout.test.tsx` so the logo and new navigation are expected:

```ts
expect(screen.getByRole("link", { name: "SigmX" })).toHaveAttribute("href", "/me");
expect(screen.getByRole("link", { name: "我的 SigmX" })).toBeInTheDocument();
```

- [ ] **Step 2: Run tests and verify missing modules/links fail**

Run:

```powershell
npm test -- --run src/components/portal/__tests__/PortalNav.test.tsx src/components/portal/__tests__/PortalLayout.test.tsx
```

Expected: fail because `PortalNav` and the `/me` logo target do not exist.

- [ ] **Step 3: Add the shared navigation model**

Create `productNavigation.ts`:

```ts
export interface ProductNavigationItem {
  to: string;
  label: string;
  description: string;
}

export const PUBLIC_PRODUCT_LINKS = [
  { to: "/product/desktop", label: "Desktop", description: "Financial Harness 专业工作台" },
  { to: "/product/data-hub", label: "Data Hub", description: "金融数据 API 与云数据" },
  { to: "/pricing", label: "套餐", description: "产品授权与用量额度" },
  { to: "/download", label: "下载", description: "获取 SigmX Desktop" },
] as const satisfies readonly ProductNavigationItem[];
```

- [ ] **Step 4: Implement `PortalNav`**

Render two authenticated entries and the public product entries with `NavLink`/`Link`. Use `aria-current="page"` through `NavLink` and mobile wrapping; do not add another logout or account state owner.

```tsx
const PRIVATE_LINKS = [
  { to: "/me", label: "我的 SigmX", end: true },
  { to: "/account", label: "账户中心", end: false },
] as const;
```

- [ ] **Step 5: Wire both layout shells to the shared model**

In `PublicLayout`, replace the private `NAV` constant with `PUBLIC_PRODUCT_LINKS`. Add a non-link label `AI 选股 · 即将上线` so the product direction is visible without registering a dead route.

In `PortalLayout`, change the logo target to `/me` and render `<PortalNav />` between the logo and account controls. Preserve admin visibility and logout behavior.

- [ ] **Step 6: Run component tests**

Run the command from Step 2.

Expected: all component tests pass, including regular-user, admin and logout behavior.

- [ ] **Step 7: Commit the navigation**

```powershell
git add frontend/src/components/navigation/productNavigation.ts frontend/src/components/portal/PortalNav.tsx frontend/src/components/portal/__tests__/PortalNav.test.tsx frontend/src/components/public/PublicLayout.tsx frontend/src/components/portal/PortalLayout.tsx frontend/src/components/portal/__tests__/PortalLayout.test.tsx
git commit -m "feat(frontend): add shared product navigation"
```

---

### Task 3: Build the Lightweight `/me` Product Home

**Files:**
- Create: `frontend/src/pages/portal/MePage.tsx`
- Create: `frontend/src/pages/portal/__tests__/MePage.test.tsx`
- Modify: `frontend/src/router.tsx`

**Interfaces:**
- Consumes: `getMyEntitlements(): Promise<EntitlementsResponse>`, `getMyCredits(): Promise<CreditsBalanceResponse>`, `getMyUsage(): Promise<UsageResponse>`, `listDevices(): Promise<DeviceItem[]>`.
- Produces: named export `MePage` and protected route `/me` under `PortalLayout`.
- Partial API failure produces an inline retryable warning while successful cards remain visible.

- [ ] **Step 1: Write failing success and action tests**

Mock `@/lib/productApi` and assert the page shows product status and clear boundaries:

```ts
vi.mock("@/lib/productApi", () => ({
  getMyEntitlements: vi.fn().mockResolvedValue({
    plan_code: "pro",
    valid_from: "2026-08-01",
    valid_until: "2026-11-01",
    entitlements: { "desktop.device_limit": 3, "datahub.daily_quota": 10000 },
  }),
  getMyCredits: vi.fn().mockResolvedValue({ available: 900, expiring_soon: 200 }),
  getMyUsage: vi.fn().mockResolvedValue({ metric: "datahub_requests", day: "2026-08-15", consumed: 120, quota_daily: 10000, remaining: 9880 }),
  listDevices: vi.fn().mockResolvedValue([{ id: "d1", name: "Research PC", created_at: "2026-08-01", revoked_at: null }]),
}));
```

Assertions:

```ts
expect(await screen.findByText("我的 SigmX")).toBeInTheDocument();
expect(screen.getByText("pro")).toBeInTheDocument();
expect(screen.getByText("900")).toBeInTheDocument();
expect(screen.getByText("120 / 10,000")).toBeInTheDocument();
expect(screen.getByRole("link", { name: /管理账户/ })).toHaveAttribute("href", "/account");
expect(screen.getByRole("link", { name: /下载 Desktop/ })).toHaveAttribute("href", "/download");
```

- [ ] **Step 2: Write the failing partial-failure test**

Make `getMyUsage` reject while the other calls resolve. Assert the page shows `部分产品状态暂时不可用` and still renders the plan and credit cards. This prevents one unavailable backend from blanking the entire portal home.

- [ ] **Step 3: Run the page test and verify it fails**

Run:

```powershell
npm test -- --run src/pages/portal/__tests__/MePage.test.tsx
```

Expected: fail because `MePage` does not exist.

- [ ] **Step 4: Implement the page with settled loading**

Use `Promise.allSettled` so each status loads independently. The page contains:

- heading and concise “Web 管理云资产，Desktop 完成深度研究” explanation;
- plan, research-credit, Data Hub usage and active-device cards;
- placeholders for `我的自选`、`保存的查询`、`我的报告`, clearly marked as later cross-device capabilities rather than fake data;
- links to `/account`, `/account/usage`, `/product/data-hub`, and `/download`;
- retry button that reruns the four requests;
- risk boundary footer text.

Use a local formatter:

```ts
function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}
```

Do not introduce a new state library or backend endpoint.

- [ ] **Step 5: Register the protected `/me` route**

Add the lazy import:

```tsx
const MePage = lazy(() =>
  import("@/pages/portal/MePage").then((m) => ({ default: m.MePage })),
);
```

Register `/me` as the first child under `AccountShell`; keep all `/account/*` routes under the same shell:

```tsx
{ path: "/me", element: wrap(MePage) },
```

- [ ] **Step 6: Run the page and routing tests**

Run:

```powershell
npm test -- --run src/pages/portal/__tests__/MePage.test.tsx src/router/__tests__/DesktopOnly.test.tsx src/pages/auth/__tests__/LoginPage.test.tsx
```

Expected: all tests pass.

- [ ] **Step 7: Commit the product home**

```powershell
git add frontend/src/pages/portal/MePage.tsx frontend/src/pages/portal/__tests__/MePage.test.tsx frontend/src/router.tsx
git commit -m "feat(frontend): add lightweight web product home"
```

---

### Task 4: Clarify Account Navigation and Compatibility

**Files:**
- Modify: `frontend/src/components/layout/AccountNav.tsx`
- Create: `frontend/src/components/layout/__tests__/AccountNav.test.tsx`
- Modify: `frontend/src/pages/Account.tsx`

**Interfaces:**
- `AccountNav` continues to render absolute `/account/*` links.
- `/account` becomes explicitly “账户与安全”; it does not become another product dashboard.
- Existing legacy credit redemption and password behavior remains functional until the later double-credit backend phase replaces it.

- [ ] **Step 1: Write the account-boundary test**

Create `AccountNav.test.tsx`:

```tsx
render(
  <MemoryRouter initialEntries={["/account"]}>
    <AccountNav />
  </MemoryRouter>,
);

expect(screen.getByRole("link", { name: "返回我的 SigmX" })).toHaveAttribute("href", "/me");
expect(screen.getByRole("link", { name: "账户与安全" })).toHaveAttribute("href", "/account");
expect(screen.getByRole("link", { name: "套餐与激活" })).toBeInTheDocument();
expect(screen.getByRole("link", { name: "用量" })).toBeInTheDocument();
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
npm test -- --run src/components/layout/__tests__/AccountNav.test.tsx
```

Expected: fail because the new boundary labels and `/me` return link are absent.

- [ ] **Step 3: Update account navigation and heading copy**

Set the first items to:

```ts
const ITEMS = [
  { to: "/me", label: "返回我的 SigmX", end: true },
  { to: "/account", label: "账户与安全", end: true },
  { to: "/account/subscription", label: "套餐与激活", end: false },
  { to: "/account/credits", label: "研究积分", end: false },
  { to: "/account/orders", label: "订单", end: false },
  { to: "/account/usage", label: "Data Hub 用量", end: false },
  { to: "/account/devices", label: "设备", end: false },
  { to: "/account/devices/authorize", label: "设备授权", end: false },
] as const;
```

In `Account.tsx`, change only the page title/description to make the boundary explicit. Preserve forms, API calls and legacy credit behavior.

- [ ] **Step 4: Run account and portal tests**

Run:

```powershell
npm test -- --run src/components/layout/__tests__/AccountNav.test.tsx src/components/portal/__tests__/PortalLayout.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit the account boundary**

```powershell
git add frontend/src/components/layout/AccountNav.tsx frontend/src/components/layout/__tests__/AccountNav.test.tsx frontend/src/pages/Account.tsx
git commit -m "refactor(frontend): separate account settings from product home"
```

---

### Task 5: Run Full Regression and Build Verification

**Files:**
- Modify only files required to fix regressions introduced by Tasks 1–4.

**Interfaces:**
- Verifies the complete frontend route and build contract.

- [ ] **Step 1: Run the complete frontend test suite**

Run:

```powershell
npm test -- --run
```

Expected: all Vitest suites pass with zero unhandled errors.

- [ ] **Step 2: Run the production build**

Run:

```powershell
npm run build
```

Expected: TypeScript and Vite build succeed with exit code 0.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and no unrelated files.

- [ ] **Step 4: Record the verified result**

If Tasks 1–4 already produced a clean build, do not create an empty commit. If verification finds a regression, return to the task that introduced the affected file, add a failing regression test there, apply the minimal fix, rerun that task's focused tests, and then repeat Steps 1–3 of this task.
