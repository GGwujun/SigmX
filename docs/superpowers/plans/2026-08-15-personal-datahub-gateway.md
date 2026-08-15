# Personal Data Hub Credential Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every legacy Data Hub credential/quota path with personal `sxd_live_` credentials and a credit-metered gateway for all 49 `/api/v1/*` routes, plus a Web personal console.

**Architecture:** `ProductStore` owns credential, limiter, lease, and usage persistence. Focused services handle credentials, request contracts, and user-level runtime limits. A custom `APIRoute` delegates to `DataHubRequestGateway` for authentication, entitlement checks, credit authorization, handler execution, response counting, settlement/release, usage audit, and billing headers.

**Tech Stack:** Python 3.12, FastAPI/Starlette, Pydantic, SQLite WAL, pytest, React 19, TypeScript, TanStack Query, Vitest.

## Global Constraints

- Personal users only; every new record is keyed directly by `user_id`.
- Keys are `sxd_live_` plus 48 hex characters and plaintext is returned once.
- Only `Authorization: Bearer sxd_live_...` authenticates Data Hub requests.
- Delete support for `sx_`, `X-API-Key`, query `api_key`, Desktop tokens, and daily request quota.
- All 49 current `/api/v1/*` GET routes pass through one fail-closed gateway.
- Research credits and Data Credits remain separate.
- Enterprise cannot use this personal flow; zero limits never mean unlimited.
- TDD is mandatory: observe focused failure before implementation.
- Work directly on `main`, explicitly authorized by the user.

## File Map

- `agent/src/product/store.py`: schema v3 and durable state.
- `agent/src/product/datahub_credentials.py`: personal Key lifecycle.
- `agent/src/product/datahub_limits.py`: user-level rate/concurrency enforcement.
- `agent/src/product/datahub_contracts.py`: strict request/response billing contracts.
- `agent/src/product/datahub_gateway.py`: unified orchestration and route wrapper.
- `agent/src/product/datahub_catalog.py`: version-2 contracts for all routes.
- `agent/src/product/commerce.py`: monthly Data Credit activation grant.
- `agent/src/api/sigmx_routes.py`: gateway installation and legacy removal.
- `agent/src/api/product_routes.py`: console APIs and old usage deletion.
- `frontend/src/pages/account/DataHubConsolePage.tsx`: personal console.

---

### Task 1: Schema v3 and Personal Credential Lifecycle

**Files:** create `agent/src/product/datahub_credentials.py`, create `agent/tests/test_datahub_credentials.py`, modify `agent/src/product/store.py`, `agent/src/product/__init__.py`, and `agent/tests/test_product_store.py`.

**Interfaces:** `DataHubCredentialService.create(user_id, name, scopes, ip_allowlist, expires_at) -> CreatedCredential`; `list(user_id)`; `authenticate(plaintext, remote_ip, now=None) -> CredentialPrincipal`; `revoke(user_id, credential_id)`; `rotate(...)`.

- [ ] Write failing tests for schema v3 tables, `^sxd_live_[0-9a-f]{48}$`, no stored/listed plaintext or hashes, owner isolation, active maximum 10, validated name/scope/IP/CIDR/UTC expiry, revoke, expiry, and atomic rotation.
- [ ] Run `python -m pytest agent/tests/test_datahub_credentials.py agent/tests/test_product_store.py -q`; verify import/schema failure.
- [ ] Add `datahub_credentials`, `datahub_rate_buckets`, `datahub_concurrency_leases`, and `datahub_request_usage` exactly as the approved spec, including usage indexes and idempotent version 3 stamp.
- [ ] Implement with `secrets.token_hex(24)`, SHA-256, `hmac.compare_digest`, `ipaddress`, canonical JSON, and `ProductStore.transaction()`. Authentication raises distinct malformed/unknown/revoked/expired/IP exceptions.
- [ ] Run the focused tests green.
- [ ] Commit with `feat(data-hub): add personal credential lifecycle`.

### Task 2: Monthly Data Credit Activation

**Files:** modify `agent/src/product/commerce.py`, `agent/src/api/product_routes.py`, and activation tests; create `agent/tests/test_datahub_monthly_grants.py`.

**Interfaces:** `CommerceService.ensure_monthly_data_grant(user_id, plan_code, period) -> DataGrantResult | None`; Advanced/Pro activation grants the current month's Data Credits once; Enterprise personal activation is rejected.

- [ ] Write failing tests: Advanced 30,000, Pro 150,000, next-UTC-month expiry, activation replay and same-month reactivation idempotency, next-month new lot, Free console contact 1,000, Enterprise rejected before order creation.
- [ ] Run `python -m pytest agent/tests/test_datahub_monthly_grants.py agent/tests/test_product_activation.py -q`; verify failure.
- [ ] Add a transaction-aware grant helper so order, entitlement, research credit, and Data Credit state cannot diverge. Keep idempotency key `data-plan-month:{user_id}:{plan}:{YYYY-MM}`.
- [ ] Invoke the helper before `/api/data-credits/me`; public catalog reads never grant.
- [ ] Run monthly, activation, and product-data route tests green.
- [ ] Commit with `feat(data-hub): grant monthly personal data credits`.

### Task 3: User-Level Rate and Concurrency Limits

**Files:** create `agent/src/product/datahub_limits.py` and `agent/tests/test_datahub_limits.py`; modify product exports.

**Interfaces:** `DataHubLimitService.acquire(user_id, credential_id, request_id, rate_limit, concurrent_limit, now=None) -> LimitLease`; `release(lease_id)`; exceptions `RateLimitExceeded`, `ConcurrentLimitExceeded`, `DataHubLimitNotConfigured`.

- [ ] Write failing tests proving two Keys share one user's minute/concurrency totals, users are isolated, exact limit succeeds, next fails, release is idempotent, 120-second leases expire, and two SQLite connections cannot exceed limits concurrently.
- [ ] Run `python -m pytest agent/tests/test_datahub_limits.py -q`; verify failure.
- [ ] In `BEGIN IMMEDIATE`, delete expired leases, check user lease count, insert lease, then conditionally upsert the `(user_id, minute)` bucket; roll back everything on limit failure.
- [ ] Run tests green and commit with `feat(data-hub): enforce personal runtime limits`.

### Task 4: Strict Request and Response Billing Contracts

**Files:** modify `agent/src/product/datahub_catalog.py` and `agent/src/product/store.py`; create `agent/src/product/datahub_contracts.py` and `agent/tests/test_datahub_contracts.py`; modify catalog tests.

**Interfaces:** extend `EndpointPricing` with `request_limit_params`, `date_params`, and `result_path`; produce `RequestContract.evaluate(endpoint, query_params, plan) -> RequestedUsage` and `ResponseContract.count(endpoint, response_json) -> int`.

- [ ] Write failing tests proving all per-unit endpoints have explicit request parameters and response paths, all 49 v2 entries validate, aliases/defaults/multiple symbols work, maximum rows/history are enforced, and missing/wrong paths fail closed.
- [ ] Run `python -m pytest agent/tests/test_datahub_contracts.py agent/tests/test_datahub_endpoint_catalog.py -q`; verify failure.
- [ ] Seed version 2 for all 49 endpoints with persisted JSON contract fields; preserve v1 history and make default lookup return v2.
- [ ] Implement configured-only parsing; never recursively guess record paths. Raise `BillingContractError`, `RequestRowsExceeded`, or `HistoryDepthExceeded` as appropriate.
- [ ] Run contract/catalog/store tests green and commit with `feat(data-hub): define strict endpoint billing contracts`.

### Task 5: Unified Billing Route and Destructive Cutover

**Files:** create `agent/src/product/datahub_gateway.py` and `agent/tests/test_datahub_gateway.py`; modify `agent/src/api/sigmx_routes.py` and relevant Data Hub route tests; delete `agent/src/product/datahub_auth.py` after callers are removed.

**Interfaces:** `DataHubRequestGateway.prepare(request, route_path) -> PreparedDataHubRequest`; `settle(prepared, response) -> Response`; `release(prepared, error_code)`; `DataHubBillingRoute(APIRoute)`.

- [ ] Write failing cutover tests: `sx_`, `X-API-Key`, query `api_key`, Desktop Bearer, missing/revoked Key, and uncataloged route fail; only `Authorization: Bearer sxd_live_...` succeeds; all 49 routes use `DataHubBillingRoute`.
- [ ] Write failing billing tests for dataset/scope/IP/rows/history/credits, fixed and partial settlement, empty result, handler/4xx/5xx release, broken result path release, UUID request idempotency, limit headers, redacted usage audit, and lease cleanup.
- [ ] Run gateway/auth/entitlement tests and observe failures.
- [ ] Implement gateway using Tasks 1–4. Free endpoints skip zero-cost reservations. Buffer JSON only for configured per-unit endpoints and reconstruct the response without changing body/status/content-type.
- [ ] Replace the router with `APIRouter(tags=["sigmx"], route_class=DataHubBillingRoute)` and remove `_data_hub_auth`, loopback bypass, legacy stores, header/query dependencies, and product-token quota.
- [ ] Delete `datahub_auth.py`, rewrite old tests to assert removal, run gateway and SigmX route suites green.
- [ ] Commit with `feat(data-hub): cut over routes to credit billing gateway`.

### Task 6: Personal Credential and Usage APIs

**Files:** modify `agent/src/api/product_routes.py`; create `agent/tests/test_product_datahub_console_routes.py`; modify product route tests.

**Interfaces:** authenticated create/list/rotate/revoke endpoints, `GET /api/datahub/usage`, and deletion of `GET /api/usage/me`.

- [ ] Write failing tests for one-time plaintext, no secret/hash listing, ownership, validation, rotation/revocation, usage date filters and endpoint aggregation, and absence of `/api/usage/me`.
- [ ] Run console/product route tests and verify failure.
- [ ] Implement Pydantic handlers using `Depends(require_user)` and authenticated `user["id"]` only. Map domain failures to stable 400/404/409 errors.
- [ ] Remove `UsageResponse`, `my_usage`, and all daily-quota lookup code.
- [ ] Run console/product/data route tests green and commit with `feat(data-hub): expose personal credential console APIs`.

### Task 7: Web Personal Data Hub Console

**Files:** modify `frontend/src/services/productApi.ts`; create `frontend/src/pages/account/DataHubConsolePage.tsx` and its test; modify discovered account navigation/router files.

**Interfaces:** `/account/data-hub` displays balance, lots, ledger, catalog, credentials, and usage; plaintext secret remains only in local dialog state.

- [ ] Write failing Vitest coverage for balance/usage, create validation, one-time warning/copy, clearing secret on close, prefix-only list, confirmed rotate/revoke, scope/IP serialization, and actionable errors.
- [ ] Run the new test and verify import/render failure.
- [ ] Add typed service functions and implement the page with existing account components. Never store plaintext in localStorage, query cache, URL, or logs.
- [ ] Add account navigation and lazy route; remove legacy usage/subscription links representing request quota or `sx_` Keys.
- [ ] Run all 239+ frontend tests and `npm run build` green.
- [ ] Commit with `feat(web): add personal Data Hub credential console`.

### Task 8: Legacy Removal and Total Architecture Audit

**Files:** modify/delete only files found by explicit legacy scans; update stale product documentation.

**Interfaces:** no active old credential/quota path and evidence that Web, Desktop, and separately metered Data Hub match the total architecture.

- [ ] Run `rg "sx_|X-API-Key|api_key.*Query|datahub\.daily_quota|datahub\.featured|datahub\.basic|acquire_product_quota|SubscriptionStore|/api/usage/me" agent/src frontend/src docs -n`; delete Data Hub compatibility results while retaining unrelated broker/LLM API-key code.
- [ ] Run focused backend acceptance covering store, credits, credentials, limits, contracts, catalog, gateway, console APIs, product routes, and closure E2E.
- [ ] Run broader Data Hub suites: auth, entitlements, SigmX routes, B/C datasets.
- [ ] Run all frontend tests and production build.
- [ ] Verify Web remains funnel/light research/personal assets/account console, Desktop remains Financial Harness, and Data Hub is independently authorized/metered.
- [ ] Run `git diff --check`, `git status --short`, and inspect commits. Record unrelated full-suite baseline failures without claiming they pass.
- [ ] Commit cleanup with `refactor(data-hub): remove legacy credential quota paths`.
