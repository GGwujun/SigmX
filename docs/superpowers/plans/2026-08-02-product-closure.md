# SigmX Product Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first operable loop across the public website, unified account/commerce, Data Hub entitlements, and the local desktop client without refining the existing investment features.

**Architecture:** Keep the current FastAPI, React, Electron, and SQLite stack, but introduce a bounded `src.product` domain with its own `product.db`. Public web pages and account APIs use this domain; Data Hub accepts either legacy `sx_` API keys or short-lived product access tokens; the desktop keeps local research data local and links to the cloud account through a device-code flow.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, SQLite/WAL, PyJWT, bcrypt, React 19, TypeScript 5.7, React Router 7, Electron 33, Vitest, pytest.

## Global Constraints

- Preserve all existing `sx_` Data Hub API keys and convert existing credit balances into non-expiring product credit lots.
- Keep Standalone desktop functionality available without a cloud account or Data Hub connection.
- Never upload positions, watchlists, broker credentials, local reports, or local files without an explicit later feature.
- Use stable entitlement keys; business code must not branch on Chinese plan labels.
- Plan prices and quotas come from server responses; frontend code must not hard-code them.
- Activation-code requests, payment events, credit reservations, refunds, and monthly grants must be idempotent.
- Before editing any existing function, class, or method, run `node .gitnexus/run.cjs impact <symbol> --direction upstream`; warn before HIGH or CRITICAL edits.
- Before every commit, run `node .gitnexus/run.cjs detect-changes --scope staged` and verify only the expected scope is staged.
- Existing uncommitted changes in `agent/api_server.py`, Data Hub routes, related tests, and `docker/start-server.sh` belong to the user; reconcile rather than overwrite them.

---

## File Structure

### New backend product domain

- `agent/src/product/models.py`: product DTOs and stable enums.
- `agent/src/product/catalog.py`: default plan catalog and entitlement keys.
- `agent/src/product/store.py`: `product.db` schema, migrations, and transaction boundary.
- `agent/src/product/credits.py`: expiring credit lots, ledger, reservation, and refund rules.
- `agent/src/product/commerce.py`: activation-code order state machine and entitlement grants.
- `agent/src/product/devices.py`: device-code authorization, refresh-token hashes, and device limits.
- `agent/src/product/tokens.py`: short-lived product access tokens and claims validation.
- `agent/src/product/payment.py`: payment provider protocol and activation-code provider.
- `agent/src/api/product_routes.py`: catalog, subscription, credits, orders, usage, devices, and admin APIs.

### New frontend product surfaces

- `frontend/src/components/public/PublicLayout.tsx`: public header/footer and calls to action.
- `frontend/src/pages/public/LandingPage.tsx`: public acquisition homepage.
- `frontend/src/pages/public/PricingPage.tsx`: server-driven plan comparison.
- `frontend/src/pages/public/DataHubProductPage.tsx`: Data Hub product boundary.
- `frontend/src/pages/public/DesktopProductPage.tsx`: desktop product boundary.
- `frontend/src/pages/public/DownloadPage.tsx`: server-driven stable release information.
- `frontend/src/pages/public/SampleReportPage.tsx`: bundled, sanitized sample report.
- `frontend/src/pages/account/SubscriptionPage.tsx`: plan, activation, expiry, and upgrade state.
- `frontend/src/pages/account/CreditsPage.tsx`: lot expiry and immutable ledger.
- `frontend/src/pages/account/UsagePage.tsx`: Data Hub and cloud AI usage.
- `frontend/src/pages/account/DevicesPage.tsx`: linked devices and revocation.
- `frontend/src/pages/account/OrdersPage.tsx`: order history.
- `frontend/src/pages/admin/OperationsPage.tsx`: activation codes, adjustments, and audit.
- `frontend/src/lib/productApi.ts`: typed cloud product API client.
- `frontend/src/lib/cloudAccount.ts`: desktop-linked cloud credentials and refresh.
- `frontend/src/components/layout/ProductStatus.tsx`: plan, credit, quota, and connection summary.

### Desktop integration

- `desktop/main.js`: encrypted cloud credential storage and external authorization browser.
- `desktop/preload.js`: narrow IPC bridge for cloud account linkage.

---

### Task 1: Product database and server-driven catalog

**Files:**
- Create: `agent/src/product/__init__.py`
- Create: `agent/src/product/models.py`
- Create: `agent/src/product/catalog.py`
- Create: `agent/src/product/store.py`
- Test: `agent/tests/test_product_store.py`

**Interfaces:**
- Produces: `ProductStore(db_path: Path)`, `ProductStore.transaction()`, `ProductStore.list_plans()`, `ProductStore.get_plan(code: str)`.
- Produces: `PlanCode`, `OrderStatus`, `EntitlementGrant`, and `PlanView` models used by all later tasks.

- [x] **Step 1: Run impact checks for reused store patterns**

Run: `node .gitnexus/run.cjs context UserStore`

> **Done note (2026-08-13):** `.gitnexus/` is not present in this repo, so impact analysis was skipped (non-blocking — Task 1 creates new files only and edits no existing symbol). The WAL store pattern was read directly from `src/auth/store.py`.

Expected: exact context for the existing SQLite/WAL store; no source file is edited in this task.

- [x] **Step 2: Write failing catalog and schema tests**

```python
def test_catalog_is_seeded_and_server_driven(tmp_path):
    store = ProductStore(tmp_path / "product.db")
    plans = {plan["code"]: plan for plan in store.list_plans()}
    assert plans["free"]["price_cny_fen"] == 0
    assert plans["advanced"]["price_cny_fen"] == 26800
    assert plans["pro"]["price_cny_fen"] == 51800
    assert plans["advanced"]["entitlements"]["datahub.daily_quota"] == 1000
    assert plans["pro"]["entitlements"]["desktop.device_limit"] == 3
```

- [x] **Step 3: Run the tests and verify the missing module failure**

Run: `python -m pytest agent/tests/test_product_store.py -v`

Expected: FAIL because `src.product.store` does not exist.

- [x] **Step 4: Implement the schema and idempotent catalog seed**

Create tables `plans`, `orders`, `entitlement_grants`, `credit_lots`, `credit_ledger`, `activation_codes`, `devices`, `device_codes`, `refresh_tokens`, `usage_daily`, `audit_log`, and `product_migrations`. Store plan entitlements as canonical JSON and seed `free`, `advanced`, `pro`, and `enterprise` in one transaction.

- [x] **Step 5: Verify catalog and migration idempotency**

Run: `python -m pytest agent/tests/test_product_store.py -v`

Expected: PASS when the store is opened twice against the same database.

- [x] **Step 6: Stage, inspect, and commit**

Run: `git add agent/src/product agent/tests/test_product_store.py && node .gitnexus/run.cjs detect-changes --scope staged`

> **Done note (2026-08-13):** `.gitnexus` not present — `detect-changes` skipped. Scope verified manually via `git status`: only new files under `agent/src/product/` plus `agent/tests/test_product_store.py` and this plan doc; no existing production symbol edited.

Expected: only new product-domain symbols.

Commit: `git commit -m "feat(product): add product catalog and store"`

### Task 2: Expiring credit lots and legacy balance migration

**Files:**
- Create: `agent/src/product/credits.py`
- Create: `agent/tests/test_product_credits.py`
- Modify: `agent/src/credits/store.py`
- Modify: `agent/src/api/credits_routes.py`
- Test: `agent/tests/test_product_credit_compatibility.py`

**Interfaces:**
- Consumes: `ProductStore.transaction()` from Task 1.
- Produces: `CreditLedger.grant()`, `reserve()`, `settle()`, `refund()`, `balance()`, `list_lots()`, and `list_entries()`.
- Preserves: existing `CreditStore.consume()` and `CreditStore.refund()` call signatures during migration.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact CreditStore --direction upstream`

Expected: callers in AlphaForge, fund analysis, credits routes, redeem administration, and scripts; record the risk before editing.

- [ ] **Step 2: Write failing lot-order and idempotency tests**

```python
def test_reserve_uses_expiring_lot_before_permanent(store, clock):
    ledger = CreditLedger(store, now=clock.now)
    ledger.grant("u1", 100, source="purchase", expires_at=None, idempotency_key="p1")
    ledger.grant("u1", 30, source="monthly", expires_at=clock.month_end, idempotency_key="m1")
    reservation = ledger.reserve("u1", 50, operation="alpha", idempotency_key="run-1")
    assert reservation.allocations == [("m1", 30), ("p1", 20)]
    assert ledger.balance("u1").available == 80
```

- [ ] **Step 3: Implement credit lots and immutable ledger**

Use `BEGIN IMMEDIATE` for grants and reservations. A reservation creates negative ledger entries and allocation rows; refund restores exactly those allocations once. Expired lots are excluded from availability without deleting their history.

- [ ] **Step 4: Add one-time legacy migration**

Read each existing `credits_balance` row and create a non-expiring lot with idempotency key `legacy-credit-balance:<user_id>`. Leave `credits.db` intact for rollback. Route compatibility methods to the new ledger after migration.

- [ ] **Step 5: Run focused compatibility tests**

Run: `python -m pytest agent/tests/test_product_credits.py agent/tests/test_product_credit_compatibility.py -v`

Expected: PASS, including failure refund exactly once and unchanged AlphaForge/Fund call signatures.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add agent/src/product/credits.py agent/src/credits/store.py agent/src/api/credits_routes.py agent/tests/test_product_credits.py agent/tests/test_product_credit_compatibility.py && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(product): add expiring credit ledger"`

### Task 3: Activation orders, entitlements, and payment adapter boundary

**Files:**
- Create: `agent/src/product/payment.py`
- Create: `agent/src/product/commerce.py`
- Create: `agent/tests/test_product_activation.py`
- Modify: `agent/src/api/admin_redeem_routes.py`

**Interfaces:**
- Consumes: plans and credit ledger from Tasks 1-2.
- Produces: `CommerceService.activate_code(user_id, plaintext_code, idempotency_key) -> ActivationResult`.
- Produces: `CommerceService.current_entitlements(user_id, at) -> EntitlementSnapshot`.
- Produces: `PaymentProvider` protocol with `create_checkout`, `verify_webhook`, `parse_event`, `query_payment`, and `refund`.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact register_admin_redeem_routes --direction upstream`

Expected: API server registration and redeem-code administration tests.

- [ ] **Step 2: Write failing atomic activation tests**

```python
def test_activation_is_atomic_and_idempotent(product):
    code = product.admin.create_activation_code(plan="advanced", months=3)
    first = product.commerce.activate_code("u1", code.plaintext, "request-1")
    second = product.commerce.activate_code("u1", code.plaintext, "request-1")
    assert second.order_id == first.order_id
    assert product.store.count_orders("u1") == 1
    assert product.credits.balance("u1").available == 300
    assert product.entitlements.current("u1").plan_code == "advanced"
```

- [ ] **Step 3: Implement the activation-code payment provider**

Hash codes with SHA-256, show plaintext once, and perform code redemption, paid zero-value order creation, entitlement grant, current-month credit grant, and audit entry in one database transaction.

- [ ] **Step 4: Map old redeem administration to two explicit code types**

Preserve existing credit-only codes as `credit` codes. Add `plan` activation codes carrying `plan_code` and `months`; never infer a plan from a credit amount.

- [ ] **Step 5: Run activation and legacy-code tests**

Run: `python -m pytest agent/tests/test_product_activation.py agent/tests/test_product_credit_compatibility.py -v`

Expected: PASS for duplicate requests, used codes, expired codes, upgrades, and extensions.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add agent/src/product agent/src/api/admin_redeem_routes.py agent/tests/test_product_activation.py && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(product): activate plans through idempotent orders"`

### Task 4: Device-code authorization and product tokens

**Files:**
- Create: `agent/src/product/tokens.py`
- Create: `agent/src/product/devices.py`
- Create: `agent/tests/test_product_devices.py`
- Modify: `agent/src/auth/jwt_utils.py`

**Interfaces:**
- Produces: `DeviceService.start(device_name, fingerprint_hash)`, `approve(user_id, user_code)`, `poll(device_code)`, `refresh(refresh_token)`, and `revoke(user_id, device_id)`.
- Produces: access-token claims `sub`, `aud`, `device_id`, `plan`, `entitlements`, `exp`, and `jti`.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact create_token --direction upstream`

If the exact JWT creation symbol has another name, run `node .gitnexus/run.cjs context jwt_utils.py`, select the exact symbol, then run impact before editing.

- [ ] **Step 2: Write failing device-flow tests**

```python
def test_device_limit_and_revocation(product):
    product.entitlements.grant("u1", "free", months=1, source="test")
    first = authorize_device(product, "u1", "desktop-a")
    with pytest.raises(DeviceLimitReached):
        authorize_device(product, "u1", "desktop-b")
    product.devices.revoke("u1", first.device_id)
    assert product.devices.refresh(first.refresh_token).status == "revoked"
```

- [ ] **Step 3: Implement RFC-style device authorization semantics**

Generate a high-entropy `device_code`, a short human `user_code`, ten-minute expiry, five-second poll interval, and one-time approval. Hash refresh tokens at rest and rotate them on every successful refresh.

- [ ] **Step 4: Sign short-lived product access tokens**

Use a distinct audience `sigmx-product`, fifteen-minute expiry, current entitlements snapshot, and device identifier. Keep existing web JWT validation compatible.

- [ ] **Step 5: Run security tests**

Run: `python -m pytest agent/tests/test_product_devices.py agent/tests/test_security_auth_api.py -v`

Expected: PASS for pending, expired, approved, limit reached, rotation, revocation, wrong audience, and tampered tokens.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add agent/src/product/tokens.py agent/src/product/devices.py agent/src/auth/jwt_utils.py agent/tests/test_product_devices.py && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(product): add desktop device authorization"`

### Task 5: Product and operations API surface

**Files:**
- Create: `agent/src/api/product_routes.py`
- Create: `agent/tests/test_product_routes.py`
- Modify: `agent/api_server.py`

**Interfaces:**
- Produces public `GET /api/catalog/plans`, `GET /api/catalog/releases/stable`, and sample-report metadata.
- Produces authenticated subscription, credits, usage, orders, and device APIs.
- Produces admin activation-code, credit-adjustment, user-status, and audit APIs.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact app --direction upstream`

Also run impact on the exact route-registration block or registration function identified by `node .gitnexus/run.cjs context api_server.py` before editing `agent/api_server.py`.

- [ ] **Step 2: Write failing route contract tests**

```python
def test_new_user_receives_free_plan_once(client, product_store):
    auth = client.post("/auth/register", json={"email": "new@example.com", "password": "secret1", "agree": True})
    token = auth.json()["token"]
    first = client.get("/api/entitlements/me", headers=bearer(token)).json()
    second = client.get("/api/entitlements/me", headers=bearer(token)).json()
    assert first["plan_code"] == "free"
    assert first["credits"]["available"] == 50
    assert second["credits"]["available"] == 50
```

- [ ] **Step 3: Implement route registration and DTOs**

Register product routes after auth routes. Public catalog endpoints require no token; account endpoints require user JWT; admin operations require `require_admin`; device polling uses the device code rather than a user JWT.

- [ ] **Step 4: Add registration bootstrap**

After `UserStore.create_user()` succeeds, idempotently create the free entitlement and the one-time 50-credit lot with key `registration-welcome:<user_id>`.

- [ ] **Step 5: Run API tests**

Run: `python -m pytest agent/tests/test_product_routes.py agent/tests/test_security_auth_api.py -v`

Expected: PASS with stable response models and no admin data exposed to ordinary users.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add agent/src/api/product_routes.py agent/api_server.py agent/tests/test_product_routes.py && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(api): expose product lifecycle APIs"`

### Task 6: Data Hub dual authentication and entitlement quotas

**Files:**
- Modify: `agent/src/api/sigmx_routes.py`
- Modify: `agent/src/data/subscription_store.py`
- Test: `agent/tests/test_data_hub_auth.py`
- Create: `agent/tests/test_data_hub_entitlements.py`

**Interfaces:**
- Consumes: `sigmx-product` access tokens and legacy `sx_` API keys.
- Produces: one normalized `DataHubPrincipal(subject, source, plan, quota_daily, featured)` for route authorization.

- [ ] **Step 1: Run required impact analysis and warn on risk**

Run: `node .gitnexus/run.cjs impact _data_hub_auth --direction upstream`

Run: `node .gitnexus/run.cjs impact SubscriptionStore --direction upstream`

Expected: Data Hub API routes, existing auth tests, admin subscription routes, and connected clients. Stop and warn if HIGH or CRITICAL.

- [ ] **Step 2: Extend failing auth matrix tests**

Add cases for valid free/advanced/pro product tokens, expired entitlement, revoked device, feature-data denial, exhausted quota, and unchanged legacy API-key behavior.

- [ ] **Step 3: Normalize both credentials**

Accept `Authorization: Bearer <product-token>` first and `X-API-Key: sx_...` second. Map product quotas from `datahub.daily_quota`; retain `SubscriptionStore.acquire_quota()` for legacy principals.

- [ ] **Step 4: Add featured-data guard without changing basic routes**

Expose a reusable `require_datahub_entitlement("datahub.featured")` dependency for future featured endpoints. Basic `/api/v1/*` routes continue to require only `datahub.basic`.

- [ ] **Step 5: Run Data Hub regression tests**

Run: `python -m pytest agent/tests/test_data_hub_auth.py agent/tests/test_data_hub_entitlements.py agent/tests/test_data_hub_settings.py agent/tests/test_data_hub_startup_contract.py -v`

Expected: PASS for both authentication families and atomic quota enforcement.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add agent/src/api/sigmx_routes.py agent/src/data/subscription_store.py agent/tests/test_data_hub_auth.py agent/tests/test_data_hub_entitlements.py && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(data-hub): enforce unified product entitlements"`

### Task 7: Public acquisition website

**Files:**
- Create: `frontend/src/components/public/PublicLayout.tsx`
- Create: all six files under `frontend/src/pages/public/` listed in File Structure
- Create: `frontend/src/lib/productApi.ts`
- Create: `frontend/src/pages/public/__tests__/PricingPage.test.tsx`
- Modify: `frontend/src/router.tsx`

**Interfaces:**
- Consumes: `GET /api/catalog/plans` and stable release metadata from Task 5.
- Produces: public `/`, `/product/data-hub`, `/product/desktop`, `/pricing`, `/download`, and `/reports/sample/:slug` routes; moves the protected dashboard to `/app`.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact router --direction upstream`

If the exported router symbol is indexed by UID, use the exact UID returned by `node .gitnexus/run.cjs context router`.

- [ ] **Step 2: Write failing pricing-page tests**

```tsx
it("renders prices and quotas from the server catalog", async () => {
  server.use(http.get("/api/catalog/plans", () => HttpResponse.json(planFixture)));
  render(<PricingPage />);
  expect(await screen.findByText("268 元/季")).toBeInTheDocument();
  expect(screen.getByText("1,000 请求/日")).toBeInTheDocument();
});
```

- [ ] **Step 3: Implement the public route tree**

Keep login and registration public. Make `/` the acquisition homepage and `/app` the existing authenticated `Home`. Preserve all existing deep links and add a temporary authenticated redirect from `/workspace` to `/app` only if tests identify an existing consumer.

- [ ] **Step 4: Implement server-driven product pages**

Use one catalog query cache for pricing and calls to action. Every page must have a primary action (`注册体验`, `下载客户端`, or `查看套餐`) and describe the website/Data Hub/desktop boundary consistently.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm --prefix frontend run test:run -- PricingPage.test.tsx`

Run: `npm --prefix frontend run build`

Expected: both succeed and unauthenticated `/` no longer redirects to `/login`.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add frontend/src/components/public frontend/src/pages/public frontend/src/lib/productApi.ts frontend/src/router.tsx && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(web): add public SigmX product site"`

### Task 8: Account commercial center and operator console

**Files:**
- Create: account and admin pages listed in File Structure
- Create: `frontend/src/components/layout/ProductStatus.tsx`
- Create: `frontend/src/pages/account/__tests__/SubscriptionPage.test.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/layout/Layout.tsx`
- Modify: `frontend/src/pages/Account.tsx`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: Task 5 product APIs.
- Produces: subscription, credits, usage, devices, orders, and operations UI.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact Account --direction upstream`

Run: `node .gitnexus/run.cjs impact Layout --direction upstream`

- [ ] **Step 2: Write failing activation UI test**

```tsx
it("refreshes all product state after activation", async () => {
  render(<SubscriptionPage />);
  await user.type(await screen.findByLabelText("套餐激活码"), "SX-ADV-1234");
  await user.click(screen.getByRole("button", { name: "激活套餐" }));
  expect(await screen.findByText("进阶版")).toBeInTheDocument();
  expect(screen.getByText("300 积分")).toBeInTheDocument();
});
```

- [ ] **Step 3: Implement account navigation and status summary**

Keep password and logout in `/account`; move credit redemption and ledger to `/account/credits`. Add visible plan, expiration, expiring credits, Data Hub usage, and device count to `ProductStatus`.

- [ ] **Step 4: Implement operations console**

Admin actions require confirmation, a reason, and server-side audit. Never display activation-code hashes or refresh-token hashes.

- [ ] **Step 5: Run UI tests and build**

Run: `npm --prefix frontend run test:run -- SubscriptionPage.test.tsx`

Run: `npm --prefix frontend run build`

Expected: PASS with ordinary users unable to load `/admin/operations`.

- [ ] **Step 6: Stage, detect, and commit**

Run: `git add frontend/src/pages/account frontend/src/pages/admin frontend/src/components/layout frontend/src/pages/Account.tsx frontend/src/lib/api.ts frontend/src/router.tsx && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(web): add subscription and operations center"`

### Task 9: Desktop cloud-account link and product status

**Files:**
- Create: `frontend/src/lib/cloudAccount.ts`
- Create: `frontend/src/pages/CloudAccount.tsx`
- Create: `frontend/src/pages/__tests__/CloudAccount.test.tsx`
- Modify: `desktop/main.js`
- Modify: `desktop/preload.js`
- Modify: `frontend/src/hooks/useAuthState.ts`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/pages/Settings.tsx`

**Interfaces:**
- Consumes: Task 4 device flow and Task 5 APIs.
- Produces Electron IPC `cloud-account:load`, `cloud-account:save`, `cloud-account:clear`, and `cloud-account:open-authorization`.
- Preserves local desktop session for local APIs; cloud account is a separate commercial identity used only for product/Data Hub APIs.

- [ ] **Step 1: Run required impact analysis**

Run: `node .gitnexus/run.cjs impact useAuthState --direction upstream`

For JavaScript functions in `desktop/main.js`, run impact on `createWindow` and each edited IPC registration symbol before changes.

- [ ] **Step 2: Write failing desktop-link UI tests**

Test pending authorization, approval, token refresh, cancellation, expired code, device limit, unlink, and Standalone operation with no cloud account.

- [ ] **Step 3: Add encrypted credential IPC**

Use Electron `safeStorage` when available. Persist only encrypted refresh token, device ID, account email, and expiry under `~/.vibe-trading/cloud-account.json`; renderer code never receives filesystem access.

- [ ] **Step 4: Implement browser approval and polling**

Start the device flow, open the verification URL in the system browser, poll at the server-provided interval, save the rotated refresh token through IPC, and refresh product/Data Hub access tokens before expiry.

- [ ] **Step 5: Remove automatic cloud identity assumptions**

Keep the existing loopback desktop session solely for local API access. Do not treat the seeded local admin as a paid cloud user. Settings must clearly show `本地账户` and `SigmX 云账户` as separate security contexts.

- [ ] **Step 6: Run frontend, Electron syntax, and build checks**

Run: `npm --prefix frontend run test:run -- CloudAccount.test.tsx`

Run: `node --check desktop/main.js && node --check desktop/preload.js`

Run: `npm --prefix frontend run build`

Expected: PASS; unlinking the cloud account leaves Standalone features usable.

- [ ] **Step 7: Stage, detect, and commit**

Run: `git add desktop/main.js desktop/preload.js frontend/src/lib/cloudAccount.ts frontend/src/pages/CloudAccount.tsx frontend/src/pages/__tests__/CloudAccount.test.tsx frontend/src/hooks/useAuthState.ts frontend/src/router.tsx frontend/src/pages/Settings.tsx && node .gitnexus/run.cjs detect-changes --scope staged`

Commit: `git commit -m "feat(desktop): link cloud membership by device code"`

### Task 10: End-to-end closure, migration, and recovery verification

**Files:**
- Create: `agent/tests/test_product_closure_e2e.py`
- Create: `agent/tests/test_product_migration.py`
- Create: `frontend/src/tests/productClosure.test.tsx`
- Modify: `README.md`
- Modify: `desktop/README.md`
- Modify: `docs/data-hub-routing-audit.md`

**Interfaces:**
- Verifies the complete public-site → account → activation → desktop → Data Hub → metered AI loop.

- [ ] **Step 1: Run impact analysis for documentation-adjacent code only if code changes are needed**

Do not edit production symbols in this task unless a failing closure test proves a defect. For any such symbol, run its upstream impact analysis first.

- [ ] **Step 2: Write the end-to-end API test**

```python
def test_new_user_product_closure(app, admin_client, clock):
    code = admin_client.post("/api/admin/activation-codes", json={"plan_code": "advanced", "months": 3, "count": 1}).json()["codes"][0]
    user = register(app, "closure@example.com")
    activation = user.post("/api/orders/activate", json={"code": code, "idempotency_key": "e2e-1"})
    assert activation.json()["subscription"]["plan_code"] == "advanced"
    device = authorize_device_through_api(app, user, "Windows desktop")
    hub = app.get("/api/v1/health", headers={"Authorization": f"Bearer {device.access_token}"})
    assert hub.status_code == 200
    assert user.get("/api/credits/me").json()["available"] == 300
```

- [ ] **Step 3: Add migration and failure-recovery coverage**

Cover legacy balance migration, legacy `sx_` keys, duplicate activation, interrupted transaction rollback, expired monthly lots, refund idempotency, revoked devices, Data Hub outage, and Connected-to-Standalone fallback messaging.

- [ ] **Step 4: Run complete focused backend and frontend suites**

Run: `python -m pytest agent/tests/test_product_*.py agent/tests/test_data_hub_*.py agent/tests/test_security_auth_api.py -v`

Run: `npm --prefix frontend run test:run`

Run: `npm --prefix frontend run build`

Run: `node --check desktop/main.js && node --check desktop/preload.js`

Expected: all pass.

- [ ] **Step 5: Run repository-wide regression gates**

Run: `python -m pytest agent/tests -q`

Expected: all tests pass; network-marked integration tests may be explicitly excluded only with the existing project marker command documented in the test output.

- [ ] **Step 6: Update operating documentation**

Document the public route, account activation, device link, Standalone/Connected behavior, Data Hub dual auth, initial plan catalog, backup requirements for `product.db`, and rollback procedure.

- [ ] **Step 7: Final staged change audit and commit**

Run: `git add agent/tests frontend/src/tests README.md desktop/README.md docs/data-hub-routing-audit.md && node .gitnexus/run.cjs detect-changes --scope staged`

Expected: only closure tests and operating documentation, unless separately audited production fixes were necessary.

Commit: `git commit -m "test(product): verify end-to-end product closure"`

---

## Plan Self-Review Results

- **Spec coverage:** All product-boundary, catalog, credits, activation, device, Data Hub, public web, account center, desktop, operations, migration, and acceptance requirements map to Tasks 1-10.
- **Scope control:** Natural-language screening, strategy marketplace, community, indicator expansion, local-data cloud sync, and trading optimization are absent.
- **Compatibility:** Existing web JWTs, local desktop sessions, credit call signatures, `sx_` API keys, Standalone mode, and private local data are explicitly preserved.
- **Type consistency:** `PlanCode`, `EntitlementSnapshot`, `CreditLedger`, `CommerceService`, `DeviceService`, and `DataHubPrincipal` are defined once and consumed by named later tasks.
- **Rollback:** Existing databases remain intact during migration; the product database is additive and activation transactions are atomic.
