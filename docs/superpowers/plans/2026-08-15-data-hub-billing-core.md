# Data Hub Billing Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate Data Hub credit ledger, a versioned catalog for all 49 current `/api/v1/*` endpoints, new plan entitlements, and authenticated read APIs without wiring request charging yet.

**Architecture:** Extend `product.db` to schema version 2 with Data Hub-owned lots, reservations, allocations, ledger, and endpoint catalog tables. Keep research `CreditLedger` untouched; add `DataCreditLedger` and `DataHubEndpointCatalog` as focused services over the existing `ProductStore.transaction()` boundary. Replace the old Data Hub entitlement keys in the canonical plan catalog and expose only read-side account/catalog APIs in this batch.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, SQLite WAL, pytest.

## Global Constraints

- This is a breaking replacement: no runtime adapter for `datahub.daily_quota`, `datahub.basic`, `datahub.featured`, or `datahub.external_api`.
- Existing `sx_` API keys and request charging are removed only in the later credential/middleware batch; this batch must not create a half-wired charging path.
- Research credits and Data Hub credits use separate tables, balances, lots, reservations, and HTTP routes.
- Data Hub writes use `ProductStore.transaction()` and balances never become negative.
- Monthly plan Data Hub credits expire at the first UTC instant of the following natural month.
- Current 49 `/api/v1/*` GET routes all receive explicit version-1 catalog rows; uncataloged endpoints fail closed in the catalog service.
- No new dependency, organization model, new API key, frontend console, real payment, or trading behavior is introduced.
- Development proceeds directly on `main` because the user explicitly authorized it.

---

## File Map

- Modify `agent/src/product/store.py`: schema version 2, new Data Hub tables, destructive Data Hub entitlement migration, catalog seeding.
- Modify `agent/src/product/catalog.py`: canonical new Data Hub plan entitlements and list-valued entitlement typing.
- Modify `agent/src/product/models.py`: replace the four old stable entitlement keys.
- Create `agent/src/product/data_credits.py`: Data Hub grant, balance, authorize, settle, release, list, and monthly-grant service.
- Create `agent/src/product/datahub_catalog.py`: endpoint catalog DTO, validation, lookup, match, estimate, calculate, and 49-row seed.
- Modify `agent/src/product/__init__.py`: export the new public domain types.
- Modify `agent/src/api/product_routes.py`: lazy services and four new read routes.
- Create `agent/tests/test_product_data_credits.py`: isolated data-credit and reservation state-machine tests.
- Create `agent/tests/test_datahub_endpoint_catalog.py`: catalog coverage and pricing tests.
- Create `agent/tests/test_product_data_routes.py`: read API serialization and user isolation.
- Modify `agent/tests/test_product_store.py`: schema-v2 and new entitlement assertions.
- Modify `agent/tests/test_product_routes.py`: replace old Data Hub entitlement expectations; leave research-credit tests intact.

---

### Task 1: Replace Plan Data Hub Entitlements and Add Schema Version 2

**Files:**
- Modify: `agent/src/product/catalog.py`
- Modify: `agent/src/product/models.py`
- Modify: `agent/src/product/store.py`
- Modify: `agent/tests/test_product_store.py`

**Interfaces:**
- Produces `ProductStore` schema version 2 with `data_credit_lots`, `data_credit_reservations`, `data_credit_allocations`, `data_credit_ledger`, and `datahub_endpoint_catalog`.
- Produces plan entitlements keyed by `datahub.enabled`, `datahub.dataset_groups`, `datahub.monthly_credits`, `datahub.rate_limit_per_minute`, `datahub.concurrent_limit`, `datahub.max_rows_per_request`, `datahub.history_depth_days`, and `datahub.commercial_use`.

- [ ] **Step 1: Write failing store and migration tests**

Add these behaviors to `test_product_store.py`:

```python
OLD_DATAHUB_KEYS = {
    "datahub.daily_quota", "datahub.basic",
    "datahub.featured", "datahub.external_api",
}

def test_catalog_uses_data_credit_entitlements(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    plans = {row["code"]: row for row in store.list_plans()}
    assert plans["free"]["entitlements"]["datahub.monthly_credits"] == 1_000
    assert plans["advanced"]["entitlements"]["datahub.dataset_groups"] == ["basic.v1", "market.v1"]
    assert plans["pro"]["entitlements"]["datahub.monthly_credits"] == 150_000
    for plan in plans.values():
        assert OLD_DATAHUB_KEYS.isdisjoint(plan["entitlements"])

def test_schema_v2_tables_exist(tmp_path: Path) -> None:
    store = ProductStore(tmp_path / "product.db")
    names = {row[0] for row in store._get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"data_credit_lots", "data_credit_reservations", "data_credit_allocations",
            "data_credit_ledger", "datahub_endpoint_catalog"} <= names
    versions = {row[0] for row in store._get_conn().execute(
        "SELECT version FROM product_migrations"
    )}
    assert 2 in versions
```

Add a migration test that creates a `ProductStore`, overwrites the advanced plan with the four old Data Hub keys, removes migration version 2, reopens the store, and asserts the old keys are gone while `desktop.device_limit` remains unchanged.

- [ ] **Step 2: Run the failing store tests**

Run:

```powershell
python -m pytest agent/tests/test_product_store.py -q
```

Expected: failures report missing new entitlements, tables, or version 2.

- [ ] **Step 3: Replace canonical catalog entitlements**

Allow list values in `PlanSeed.entitlements` and set exact values:

```python
EntitlementValue = int | bool | list[str]

DATAHUB = {
    "free": dict(enabled=True, groups=["basic.v1"], credits=1_000, rate=30, concurrency=1, rows=1_000, history=365, commercial=False),
    "advanced": dict(enabled=True, groups=["basic.v1", "market.v1"], credits=30_000, rate=120, concurrency=3, rows=10_000, history=1_825, commercial=False),
    "pro": dict(enabled=True, groups=["basic.v1", "market.v1", "finance.v1", "pro.v1"], credits=150_000, rate=600, concurrency=10, rows=100_000, history=7_300, commercial=False),
    "enterprise": dict(enabled=True, groups=[], credits=0, rate=0, concurrency=0, rows=0, history=0, commercial=True),
}
```

Flatten those values into the eight stable entitlement keys in each existing plan while preserving non-Data-Hub entitlements.

- [ ] **Step 4: Add schema-v2 tables and migration**

Set `_SCHEMA_VERSION = 2`, add the exact tables and constraints from the approved spec, and implement `_migrate_v2_datahub_entitlements(conn)`:

```python
if conn.execute("SELECT 1 FROM product_migrations WHERE version = 2").fetchone() is None:
    for seed in DEFAULT_CATALOG:
        row = conn.execute("SELECT entitlements_json FROM plans WHERE code = ?", (seed["code"],)).fetchone()
        current = json.loads(row["entitlements_json"]) if row else {}
        for key in OLD_DATAHUB_ENTITLEMENT_KEYS:
            current.pop(key, None)
        current.update({k: v for k, v in seed["entitlements"].items() if k.startswith("datahub.")})
        encoded = json.dumps(current, sort_keys=True, ensure_ascii=False)
        conn.execute("UPDATE plans SET entitlements_json = ? WHERE code = ?", (encoded, seed["code"]))
```

Call the migration after seeding and before stamping version 2. Keep migration idempotent.

- [ ] **Step 5: Run store and existing catalog tests**

Run:

```powershell
python -m pytest agent/tests/test_product_store.py agent/tests/test_product_routes.py::test_catalog_endpoint_serializes_all_four_plans -q
```

Expected: store tests pass; the old route assertion fails until Step 6 updates it.

- [ ] **Step 6: Update route catalog assertions**

In `test_product_routes.py`, assert:

```python
assert advanced.entitlements["datahub.monthly_credits"] == 30_000
assert advanced.entitlements["datahub.dataset_groups"] == ["basic.v1", "market.v1"]
```

- [ ] **Step 7: Re-run and commit**

Run the Step 5 command; expected all pass. Then:

```powershell
git add agent/src/product/catalog.py agent/src/product/models.py agent/src/product/store.py agent/tests/test_product_store.py agent/tests/test_product_routes.py
git commit -m "feat(data-hub): add data credit schema and entitlements"
```

---

### Task 2: Implement Data Credit Grants, Balance, and Monthly Lots

**Files:**
- Create: `agent/src/product/data_credits.py`
- Create: `agent/tests/test_product_data_credits.py`
- Modify: `agent/src/product/__init__.py`

**Interfaces:**
- Produces `DataCreditLedger(store: ProductStore, now: Callable[[], str] = _now_iso)`.
- Produces `grant(owner_id, amount, *, source, expires_at, idempotency_key) -> DataGrantResult`.
- Produces `balance(owner_id) -> DataCreditBalance`, `list_lots(owner_id)`, `list_entries(owner_id, limit=100)`.
- Produces `grant_monthly_data_credits(ledger, owner_id, plan_code, period: date) -> DataGrantResult | None`.

- [ ] **Step 1: Write failing grant and balance tests**

Create tests proving isolation and expiry:

```python
def test_data_grant_does_not_change_research_balance(store: ProductStore) -> None:
    research = CreditLedger(store)
    data = DataCreditLedger(store)
    research.grant("u1", 50, source="research", expires_at=None, idempotency_key="r1")
    data.grant("u1", 1_000, source="data_purchase", expires_at=None, idempotency_key="d1")
    assert research.balance("u1").available == 50
    assert data.balance("u1").available == 1_000

def test_data_grant_is_idempotent(store: ProductStore) -> None:
    ledger = DataCreditLedger(store)
    first = ledger.grant("u1", 100, source="monthly", expires_at=None, idempotency_key="d1")
    second = ledger.grant("u1", 100, source="monthly", expires_at=None, idempotency_key="d1")
    assert second.lot_id == first.lot_id
    assert second.idempotent_replay is True
    assert ledger.balance("u1").available == 100
```

Also test expired lots are excluded, seven-day expiry is counted, non-positive grants raise `ValueError`, and different owners cannot see each other's lots or entries.

- [ ] **Step 2: Run the new tests and verify import failure**

Run:

```powershell
python -m pytest agent/tests/test_product_data_credits.py -q
```

Expected: import failure because `data_credits.py` does not exist.

- [ ] **Step 3: Implement minimal grant and read service**

Define frozen DTOs `DataGrantResult`, `DataCreditBalance`, `DataCreditAuthorization`, and the declared exception types. Implement grant and reads with the same expiring-first semantics as research credits, but query only `data_credit_*` tables.

- [ ] **Step 4: Add monthly grant tests and implementation**

Test exact key and expiry:

```python
result = grant_monthly_data_credits(ledger, "u1", "advanced", date(2026, 8, 15))
assert ledger.balance("u1").available == 30_000
lot = ledger.list_lots("u1")[0]
assert lot["idempotency_key"] == "data-plan-month:u1:advanced:2026-08"
assert lot["expires_at"] == "2026-09-01T00:00:00+00:00"
```

The helper reads `datahub.monthly_credits` from `store.get_plan(plan_code)`, returns `None` for a zero-credit plan, and is idempotent within the month.

- [ ] **Step 5: Run tests and export public types**

Run the Task 2 tests; expected all pass. Export `DataCreditLedger`, DTOs, exceptions, and `grant_monthly_data_credits` from `src.product.__init__`.

- [ ] **Step 6: Commit**

```powershell
git add agent/src/product/data_credits.py agent/src/product/__init__.py agent/tests/test_product_data_credits.py
git commit -m "feat(data-hub): add isolated data credit ledger"
```

---

### Task 3: Implement Authorization, Partial Settlement, Release, and Concurrency Safety

**Files:**
- Modify: `agent/src/product/data_credits.py`
- Modify: `agent/tests/test_product_data_credits.py`

**Interfaces:**
- Produces `authorize(owner_id, endpoint_code, max_cost, idempotency_key) -> DataCreditAuthorization`.
- Produces `settle(reservation_id, actual_cost, idempotency_key) -> DataCreditSettlement`.
- Produces `release(reservation_id, idempotency_key) -> DataCreditSettlement`.
- Exceptions: `InsufficientDataCredits`, `UnknownDataCreditReservation`, `InvalidDataCreditSettlement`.

- [ ] **Step 1: Write failing authorization tests**

Add tests for expiring-first allocation, insufficient-balance rollback, and idempotent replay:

```python
auth = ledger.authorize("u1", "stocks.daily", 50, "req-1")
assert auth.amount_authorized == 50
assert ledger.balance("u1").available == 80
assert ledger.authorize("u1", "stocks.daily", 50, "req-1").reservation_id == auth.reservation_id
```

Query `data_credit_allocations` to assert the expiring lot supplied 30 and the permanent lot supplied 20.

- [ ] **Step 2: Run and verify failure, then implement authorization**

Run the focused authorization tests. Implement the operation inside one `BEGIN IMMEDIATE` transaction, inserting reservation and allocation rows and one negative `authorize` ledger row per lot.

- [ ] **Step 3: Write failing settlement/release tests**

Cover:

```python
auth = ledger.authorize("u1", "stocks.daily", 100, "req-1")
settled = ledger.settle(auth.reservation_id, 35, "settle-1")
assert settled.amount_settled == 35
assert settled.amount_released == 65
assert ledger.balance("u1").available == 65
```

Also cover zero-cost settlement, full settlement, full release, repeated settlement/release, actual cost above authorization, released-then-settle, settled-then-release, and unknown reservation.

- [ ] **Step 4: Implement settlement state machine**

Restore unused allocations in reverse allocation order so the effective consumed amount still respects expiry-first selection. Write positive `release` rows for restored amounts and a zero-delta `settle` row with `metadata_json={"actual_cost": N}`. State transitions are `authorized -> settled` or `authorized -> released` only.

- [ ] **Step 5: Add deterministic concurrency test**

Use two `DataCreditLedger` instances backed by two `ProductStore` instances pointing at the same database, synchronize two threads with `threading.Barrier`, and attempt two 80-credit authorizations against a 100-credit balance. Assert exactly one succeeds, one raises `InsufficientDataCredits`, and final balance is 20.

- [ ] **Step 6: Run and commit**

Run:

```powershell
python -m pytest agent/tests/test_product_data_credits.py -q
```

Expected: all data-credit tests pass. Then:

```powershell
git add agent/src/product/data_credits.py agent/tests/test_product_data_credits.py
git commit -m "feat(data-hub): add transactional data credit settlement"
```

---

### Task 4: Add the Complete Versioned Endpoint Catalog

**Files:**
- Create: `agent/src/product/datahub_catalog.py`
- Create: `agent/tests/test_datahub_endpoint_catalog.py`
- Modify: `agent/src/product/store.py`
- Modify: `agent/src/product/__init__.py`

**Interfaces:**
- Produces `EndpointPricing`, `DataHubEndpointCatalog`, `UnknownDataHubEndpoint`, `InvalidPricingRule`.
- Produces `get(endpoint_code, version=None)`, `match(method, path, version=None)`, `list(version=None, enabled_only=True)`, `estimate(endpoint, requested_units)`, and `calculate(endpoint, actual_units)`.

- [ ] **Step 1: Write failing pricing tests**

Test literal prices:

```python
assert catalog.calculate(catalog.get("health"), 0) == 0
assert catalog.calculate(catalog.get("stocks.metadata"), 1) == 1
assert catalog.calculate(catalog.get("stocks.daily"), 1) == 2
assert catalog.calculate(catalog.get("stocks.daily"), 1_001) == 12
assert catalog.estimate(catalog.get("stocks.daily"), 50_000) == 100
```

Test unknown endpoint, disabled endpoint, negative units, invalid per-unit fields, exact method/path matching, and latest enabled version selection.

- [ ] **Step 2: Write failing route coverage test**

Parse `sigmx_routes.py` with the Python `ast` module, collect every literal router GET decorator whose path starts with `/api/v1/`, and assert equality with the catalog seed's `(method, path_pattern)` set. Assert the count is exactly 49.

- [ ] **Step 3: Add the explicit 49-row seed**

Create `ENDPOINT_CATALOG_V1` from this complete route map. Each tuple is `(endpoint_code, path, dataset_group, pricing_mode, base_cost)`; `per_unit` rows additionally use `unit_name="rows"`, `unit_size=1000`, `unit_cost=10`, and `max_cost=100`:

```python
V1_ENDPOINTS = [
    ("health", "/api/v1/health", "basic.v1", "free", 0),
    ("market.latest_trade_date", "/api/v1/market/latest-trade-date", "basic.v1", "free", 0),
    ("market.overview", "/api/v1/market/overview", "basic.v1", "fixed", 1),
    ("market.breadth", "/api/v1/market/breadth", "basic.v1", "fixed", 1),
    ("market.fund_summary", "/api/v1/market/fund-summary", "basic.v1", "fixed", 1),
    ("stocks.metadata", "/api/v1/stocks/metadata", "basic.v1", "fixed", 1),
    ("boards.members", "/api/v1/boards/members", "basic.v1", "fixed", 1),
    ("stocks.unusual_types", "/api/v1/stocks/unusual/types", "basic.v1", "fixed", 1),
    ("hot_money.list", "/api/v1/hot-money/list", "basic.v1", "fixed", 1),
    ("news.finance_rss_summary", "/api/v1/news/finance/rss-summary", "basic.v1", "fixed", 1),
    ("indices.daily", "/api/v1/indices/daily", "market.v1", "per_unit", 2),
    ("stocks.daily", "/api/v1/stocks/daily", "market.v1", "per_unit", 2),
    ("stocks.daily_basic", "/api/v1/stocks/daily-basic", "market.v1", "per_unit", 2),
    ("etf.daily", "/api/v1/etf/daily", "market.v1", "per_unit", 2),
    ("fund.daily", "/api/v1/fund/daily", "market.v1", "per_unit", 2),
    ("boards.daily", "/api/v1/boards/daily", "market.v1", "per_unit", 2),
    ("stocks.financial_statement", "/api/v1/stocks/financial-statement", "finance.v1", "per_unit", 2),
    ("stocks.fq_factors", "/api/v1/stocks/fq-factors", "market.v1", "per_unit", 2),
    ("stocks.minute", "/api/v1/stocks/minute", "pro.v1", "per_unit", 2),
    ("stocks.ticks", "/api/v1/stocks/ticks", "pro.v1", "per_unit", 2),
    ("sectors.fund_flow", "/api/v1/sectors/fund-flow", "pro.v1", "fixed", 5),
    ("sectors.fund_flow_intraday", "/api/v1/sectors/fund-flow/intraday", "pro.v1", "fixed", 5),
    ("stocks.hot_pool", "/api/v1/stocks/hot-pool", "market.v1", "fixed", 2),
    ("quotes.realtime", "/api/v1/quotes/realtime", "pro.v1", "fixed", 5),
    ("stocks.fund_flow", "/api/v1/stocks/fund-flow", "pro.v1", "fixed", 5),
    ("stocks.capital_flow", "/api/v1/stocks/capital-flow", "pro.v1", "fixed", 5),
    ("stocks.capital_rank", "/api/v1/stocks/capital-rank", "pro.v1", "fixed", 5),
    ("northbound.flow", "/api/v1/northbound/flow", "pro.v1", "fixed", 5),
    ("stocks.limit_pool", "/api/v1/stocks/limit-pool", "pro.v1", "fixed", 5),
    ("dragon_tiger", "/api/v1/dragon-tiger", "pro.v1", "fixed", 5),
    ("hot_list", "/api/v1/hot-list", "pro.v1", "fixed", 5),
    ("market.regime", "/api/v1/market/regime", "market.v1", "fixed", 2),
    ("stocks.financial_snapshot", "/api/v1/stocks/financial-snapshot", "finance.v1", "fixed", 3),
    ("stocks.eps_forecast", "/api/v1/stocks/eps-forecast", "finance.v1", "fixed", 3),
    ("stocks.margin", "/api/v1/stocks/margin", "finance.v1", "fixed", 3),
    ("stocks.block_trade", "/api/v1/stocks/block-trade", "finance.v1", "fixed", 3),
    ("stocks.holder_num", "/api/v1/stocks/holder-num", "finance.v1", "fixed", 3),
    ("stocks.dividends", "/api/v1/stocks/dividends", "finance.v1", "fixed", 3),
    ("funds.premium", "/api/v1/funds/premium", "pro.v1", "fixed", 5),
    ("funds.arbitrage_signals", "/api/v1/funds/arbitrage-signals", "pro.v1", "fixed", 5),
    ("etf.share_size", "/api/v1/etf/share-size", "market.v1", "fixed", 2),
    ("option_chain", "/api/v1/option-chain", "pro.v1", "fixed", 5),
    ("market.stage_snapshot", "/api/v1/market/stage-snapshot", "market.v1", "fixed", 2),
    ("stocks.quote5", "/api/v1/stocks/quote5", "pro.v1", "fixed", 5),
    ("stocks.unusual", "/api/v1/stocks/unusual", "pro.v1", "fixed", 5),
    ("stocks.call_auction", "/api/v1/stocks/call-auction", "pro.v1", "fixed", 5),
    ("hot_money.daily", "/api/v1/hot-money/daily", "pro.v1", "fixed", 5),
    ("stocks.hot_history", "/api/v1/stocks/hot-history", "pro.v1", "fixed", 5),
    ("content.morning_briefing_triptych", "/api/v1/content/morning-briefing-triptych", "pro.v1", "fixed", 5),
]
```

- [ ] **Step 4: Implement catalog validation and lookup**

Validate at construction: free has zero cost and no unit fields; fixed has non-negative base and no unit fields; per-unit has positive unit size/cost/max and max not below base. Use integer ceiling division for units.

- [ ] **Step 5: Seed catalog through ProductStore**

Add `seed_endpoint_catalog(conn)` after schema creation. Insert `ENDPOINT_CATALOG_V1` with `INSERT OR IGNORE`, preserving historical versions. Add `list_datahub_endpoints()` only if the catalog service needs a focused store read helper; do not expose generic SQL from route code.

- [ ] **Step 6: Run and commit**

Run:

```powershell
python -m pytest agent/tests/test_datahub_endpoint_catalog.py agent/tests/test_product_store.py -q
```

Expected: all pass. Then:

```powershell
git add agent/src/product/datahub_catalog.py agent/src/product/store.py agent/src/product/__init__.py agent/tests/test_datahub_endpoint_catalog.py agent/tests/test_product_store.py
git commit -m "feat(data-hub): add versioned endpoint pricing catalog"
```

---

### Task 5: Expose Data Credit and Endpoint Catalog Read APIs

**Files:**
- Modify: `agent/src/api/product_routes.py`
- Create: `agent/tests/test_product_data_routes.py`

**Interfaces:**
- Produces `GET /api/data-credits/me`, `/api/data-credits/lots`, `/api/data-credits/ledger`, and `/api/datahub/catalog`.
- All data-credit routes use `Depends(require_user)` and owner ID from the authenticated user.
- Catalog route is public and returns only enabled latest-version entries.

- [ ] **Step 1: Write failing route serialization tests**

Isolate `_data_ledger` and `_endpoint_catalog` alongside existing route singletons. Grant data credits to `u1` and `u2`, then assert `my_data_credits(user={"id": "u1"})`, `my_data_credit_lots`, and `my_data_credit_ledger` contain only `u1` data. Assert `datahub_catalog()` contains 49 enabled entries with no duplicated endpoint codes.

- [ ] **Step 2: Run and verify missing handlers**

Run:

```powershell
python -m pytest agent/tests/test_product_data_routes.py -q
```

Expected: failure because the new lazy services, models, and handlers do not exist.

- [ ] **Step 3: Add response models and handlers**

Add separate Pydantic models:

```python
class DataCreditsBalanceResponse(BaseModel):
    available: int
    expiring_soon: int

class DataCreditLotItem(BaseModel):
    id: str
    amount_total: int
    amount_remaining: int
    source: str
    expires_at: str | None
    created_at: str

class DataCreditLedgerItem(BaseModel):
    id: str
    operation: str
    delta: int
    lot_id: str | None
    reservation_id: str | None
    created_at: str
```

The endpoint view includes all pricing fields, group, enabled flag, and catalog version. Do not reuse research-credit response names.

- [ ] **Step 4: Run focused route and product regressions**

Run:

```powershell
python -m pytest agent/tests/test_product_data_routes.py agent/tests/test_product_routes.py agent/tests/test_product_activation.py agent/tests/test_product_credits.py agent/tests/test_product_devices.py -q
```

Expected: all pass. Old `/api/usage/me` tests may still exist because request middleware is not switched in this batch; do not rewrite that endpoint here.

- [ ] **Step 5: Commit**

```powershell
git add agent/src/api/product_routes.py agent/tests/test_product_data_routes.py
git commit -m "feat(data-hub): expose data credit and pricing reads"
```

---

### Task 6: Full Regression and Completion Verification

**Files:**
- Modify only files implicated by a failing regression test from Tasks 1–5.

**Interfaces:**
- Verifies schema migration, domain isolation, catalog coverage, route serialization, and repository regression safety.

- [ ] **Step 1: Run all product-domain tests**

Run:

```powershell
python -m pytest agent/tests/test_product_store.py agent/tests/test_product_credits.py agent/tests/test_product_data_credits.py agent/tests/test_datahub_endpoint_catalog.py agent/tests/test_product_activation.py agent/tests/test_product_devices.py agent/tests/test_product_routes.py agent/tests/test_product_data_routes.py agent/tests/test_product_closure_e2e.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run the full Python suite**

Run:

```powershell
python -m pytest agent/tests -q
```

Expected: zero failures. If an unrelated pre-existing failure appears, record its exact test and prove it also fails at the pre-feature commit before classifying it as baseline.

- [ ] **Step 3: Run frontend regression**

Use the bundled Node runtime already required by this workspace:

```powershell
$env:Path = 'C:\Users\Lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:Path
Set-Location frontend
node node_modules/vitest/vitest.mjs run --reporter=dot
npm run build
```

Expected: all frontend tests and the production build pass.

- [ ] **Step 4: Inspect final state**

Run:

```powershell
git diff --check
git status --short
git log -6 --oneline
```

Expected: no whitespace errors, no uncommitted implementation files, and five focused feature commits after the plan commit.
