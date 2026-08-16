/**
 * Typed client for the product-closure APIs (Task 5: /api/catalog/*,
 * /api/entitlements/me, /api/credits/me, /api/orders/*, /api/devices/*,
 * /api/admin/activation-codes).
 *
 * Mirrors the request style of api.ts: shares authHeaders() + ApiError, never
 * hard-codes plan prices (the catalog is server-driven, design §4.1).
 */
import { ApiError } from "@/lib/api";
import { authHeaders } from "@/lib/apiAuth";

const BASE = "";

// ---- Types matching the Pydantic models in src/api/product_routes.py ----

export interface PlanEntitlements {
  [key: string]: number | boolean | string[];
}

export interface PlanView {
  code: string;
  name_zh: string;
  price_cny_fen: number;
  billing_period: string;
  monthly_credits: number;
  welcome_credits: number;
  description: string;
  entitlements: PlanEntitlements;
  sort_order: number;
}

export interface CatalogResponse {
  plans: PlanView[];
}

export interface StableRelease {
  version: string;
  notes: string;
  download_url: string;
}

export interface EntitlementsResponse {
  plan_code: string;
  valid_from: string | null;
  valid_until: string | null;
  entitlements: PlanEntitlements;
}

export interface CreditsBalanceResponse {
  available: number;
  expiring_soon: number;
}

export interface CreditLot {
  id: string;
  idempotency_key: string | null;
  amount_total: number;
  amount_remaining: number;
  source: string;
  expires_at: string | null;
  created_at: string;
}

export interface LedgerEntry {
  id: string;
  operation: string;
  delta: number;
  lot_id: string | null;
  idempotency_key: string | null;
  created_at: string;
}

export interface ActivateResult {
  order_id: string;
  plan_code: string;
  months: number;
  credits_granted: number;
  replayed: boolean;
}

export interface OrderItem {
  id: string;
  plan_code: string;
  status: string;
  channel: string;
  price_cny_fen: number;
  months: number;
  created_at: string;
  paid_at: string | null;
}

export interface BillingSummary {
  period_days: number;
  paid_orders: number;
  paid_cny_fen: number;
  research_credits_consumed: number;
  data_credits_consumed: number;
  daily: Array<{
    date: string;
    research_credits_consumed: number;
    data_credits_consumed: number;
    paid_cny_fen: number;
  }>;
}

export interface PersonalNotification {
  id: string;
  kind: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPreferences {
  budget_alerts: boolean;
  product_updates: boolean;
  cloud_tasks: boolean;
}

export interface SavedQuerySubscription {
  id: string;
  saved_query_id: string;
  query: string;
  frequency: "daily" | "weekly";
  next_run_at: string;
  last_run_at: string | null;
  created_at: string;
}

export interface CloudTaskItem {
  id: string; user_id: string; task_type: string; title: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  payload: Record<string, unknown>; reserved_credits: number; reservation_id: string;
  result_ref: string | null; error: string | null; created_at: string;
  started_at: string | null; finished_at: string | null;
}

export interface QueryExecutionItem {
  id: string; user_id: string; query: string; intent: string;
  conditions: Array<Record<string, unknown>>; condition_version: number;
  result_count: number; executed_at: string;
}

export interface AdminProductMetrics {
  period_days: number;
  active_entitled_users: number;
  plan_distribution: Record<string, number>;
  paid_orders: number;
  revenue_cny_fen: number;
  active_datahub_credentials: number;
  datahub_requests: number;
  datahub_success_rate: number;
  data_credits_charged: number;
  weekly_effective_research_users: number;
  personal_funnel: Record<string, number>;
}

export interface DeviceItem {
  id: string;
  name: string;
  created_at: string;
  revoked_at: string | null;
}

export interface CreatedCodeItem {
  plaintext: string;
  code_hash: string;
  plan_code: string;
  months: number;
}

// ---- Core fetch (auth-aware, throws ApiError on !ok) ----

async function productRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(options?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* keep HTTP status */
    }
    throw new ApiError(detail, res.status);
  }
  // 204 (e.g. device revoke) → no body.
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

// ---- Public catalog (no auth) ----

export async function getPlans(): Promise<PlanView[]> {
  const data = await productRequest<CatalogResponse>("/api/catalog/plans");
  return data.plans;
}

export async function getStableRelease(): Promise<StableRelease> {
  return productRequest<StableRelease>("/api/catalog/releases/stable");
}

// ---- Account (auth) ----

export async function getMyEntitlements(): Promise<EntitlementsResponse> {
  return productRequest<EntitlementsResponse>("/api/entitlements/me");
}

export async function getMyCredits(): Promise<CreditsBalanceResponse> {
  return productRequest<CreditsBalanceResponse>("/api/credits/me");
}

export async function getMyLots(): Promise<CreditLot[]> {
  const data = await productRequest<{ lots: CreditLot[] }>("/api/credits/lots");
  return data.lots;
}

export async function getMyLedger(): Promise<LedgerEntry[]> {
  const data = await productRequest<{ entries: LedgerEntry[] }>("/api/credits/ledger");
  return data.entries;
}

export interface DataCreditBalance {
  available: number;
  expiring_soon: number;
}

export interface DataCreditPack {
  code: string;
  name_zh: string;
  credits: number;
  price_cny_fen: number;
  valid_days: number;
  enabled: boolean;
  sort_order: number;
}

export interface DataCreditLot {
  id: string;
  amount_total: number;
  amount_remaining: number;
  source: string;
  expires_at: string | null;
  created_at: string;
}

export interface DataCreditLedgerEntry {
  id: string;
  operation: string;
  delta: number;
  lot_id: string | null;
  reservation_id: string | null;
  created_at: string;
}

export interface DataHubCredential {
  id: string;
  key_prefix: string;
  name: string;
  scopes: string[];
  ip_allowlist: string[];
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface CreatedDataHubCredential extends DataHubCredential {
  plaintext: string;
}

export interface DataHubEndpoint {
  endpoint_code: string;
  catalog_version: number;
  http_method: string;
  path_pattern: string;
  dataset_group: string;
  pricing_mode: "free" | "fixed" | "per_unit";
  base_cost: number;
  unit_name: string | null;
  unit_size: number | null;
  unit_cost: number | null;
  max_cost: number | null;
  enabled: boolean;
}

export interface DataHubUsage {
  total_requests: number;
  successful_requests: number;
  credits_charged: number;
  by_endpoint: Array<{
    endpoint_code: string;
    requests: number;
    successful_requests: number;
    credits_charged: number;
  }>;
}

export interface DataHubRequestLog {
  request_id: string; credential_id: string; credential_name: string; key_prefix: string;
  endpoint_code: string; status_code: number; requested_units: number; actual_units: number;
  credits_authorized: number; credits_charged: number; duration_ms: number;
  error_code: string | null; created_at: string;
}

export interface DataHubBudget {
  credential_id: string; daily_limit: number; spent_today: number;
  remaining_today: number; utc_date: string;
}

export interface DataHubBudgetAlert {
  credential_id: string; credential_name: string; utc_date: string;
  threshold_percent: number; spent: number; daily_limit: number; created_at: string;
}

export async function getDataCreditBalance(): Promise<DataCreditBalance> {
  return productRequest<DataCreditBalance>("/api/data-credits/me");
}

export async function getDataCreditPacks(): Promise<DataCreditPack[]> {
  const data = await productRequest<{ items: DataCreditPack[] }>("/api/catalog/data-credit-packs");
  return data.items;
}

export async function redeemDataCreditPack(code: string, idempotencyKey: string): Promise<ActivateResult> {
  return productRequest<ActivateResult>("/api/data-credits/redeem", {
    method: "POST", body: JSON.stringify({ code, idempotency_key: idempotencyKey }),
  });
}

export async function getDataCreditLots(): Promise<DataCreditLot[]> {
  const data = await productRequest<{ lots: DataCreditLot[] }>("/api/data-credits/lots");
  return data.lots;
}

export async function getDataCreditLedger(): Promise<DataCreditLedgerEntry[]> {
  const data = await productRequest<{ entries: DataCreditLedgerEntry[] }>("/api/data-credits/ledger");
  return data.entries;
}

export async function listDataHubCredentials(): Promise<DataHubCredential[]> {
  const data = await productRequest<{ items: DataHubCredential[] }>("/api/datahub/credentials");
  return data.items;
}

export async function createDataHubCredential(input: {
  name: string;
  scopes: string[];
  ip_allowlist: string[];
  expires_at: string | null;
}): Promise<CreatedDataHubCredential> {
  return productRequest<CreatedDataHubCredential>("/api/datahub/credentials", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function rotateDataHubCredential(id: string): Promise<CreatedDataHubCredential> {
  return productRequest<CreatedDataHubCredential>(`/api/datahub/credentials/${id}/rotate`, {
    method: "POST",
  });
}

export async function revokeDataHubCredential(id: string): Promise<void> {
  await productRequest(`/api/datahub/credentials/${id}`, { method: "DELETE" });
}

export async function getDataHubUsage(): Promise<DataHubUsage> {
  return productRequest<DataHubUsage>("/api/datahub/usage");
}

export async function getDataHubCatalog(): Promise<DataHubEndpoint[]> {
  const data = await productRequest<{ items: DataHubEndpoint[] }>("/api/datahub/catalog");
  return data.items;
}

export async function getDataHubLogs(errorsOnly = false): Promise<DataHubRequestLog[]> {
  const data = await productRequest<{ items: DataHubRequestLog[] }>(`/api/datahub/logs?limit=50&errors_only=${errorsOnly}`);
  return data.items;
}

export async function setDataHubBudget(id: string, dailyLimit: number | null): Promise<DataHubBudget | null> {
  return productRequest<DataHubBudget | null>(`/api/datahub/credentials/${id}/budget`, {
    method: "PUT", body: JSON.stringify({ daily_limit: dailyLimit }),
  });
}

export async function getDataHubBudgets(): Promise<DataHubBudget[]> {
  const data = await productRequest<{ items: DataHubBudget[] }>("/api/datahub/budgets");
  return data.items;
}

export async function getDataHubBudgetAlerts(): Promise<DataHubBudgetAlert[]> {
  const data = await productRequest<{ items: DataHubBudgetAlert[] }>("/api/datahub/budget-alerts?limit=100");
  return data.items;
}

export async function activateCode(code: string, idempotencyKey: string): Promise<ActivateResult> {
  return productRequest<ActivateResult>("/api/orders/activate", {
    method: "POST",
    body: JSON.stringify({ code, idempotency_key: idempotencyKey }),
  });
}

export async function listOrders(): Promise<OrderItem[]> {
  const data = await productRequest<{ items: OrderItem[] }>("/api/orders");
  return data.items;
}

export async function getBillingSummary(days = 30): Promise<BillingSummary> {
  return productRequest<BillingSummary>(`/api/billing/summary?days=${days}`);
}

export async function listNotifications(): Promise<PersonalNotification[]> {
  const data = await productRequest<{ items: PersonalNotification[] }>("/api/notifications?limit=100");
  return data.items;
}

export async function markNotificationRead(id: string): Promise<void> {
  await productRequest(`/api/notifications/${encodeURIComponent(id)}/read`, { method: "POST" });
}

export async function getNotificationPreferences(): Promise<NotificationPreferences> {
  return productRequest<NotificationPreferences>("/api/notification-preferences");
}

export async function putNotificationPreferences(
  preferences: NotificationPreferences,
): Promise<NotificationPreferences> {
  return productRequest<NotificationPreferences>("/api/notification-preferences", {
    method: "PUT", body: JSON.stringify(preferences),
  });
}

export async function listSavedQuerySubscriptions(): Promise<SavedQuerySubscription[]> {
  const data = await productRequest<{ items: SavedQuerySubscription[] }>("/api/cloud/query-subscriptions");
  return data.items;
}

export async function putSavedQuerySubscription(
  savedQueryId: string,
  frequency: SavedQuerySubscription["frequency"],
): Promise<SavedQuerySubscription> {
  return productRequest<SavedQuerySubscription>("/api/cloud/query-subscriptions", {
    method: "PUT",
    body: JSON.stringify({ saved_query_id: savedQueryId, frequency }),
  });
}

export async function deleteSavedQuerySubscription(id: string): Promise<void> {
  await productRequest(`/api/cloud/query-subscriptions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function listCloudTasks(): Promise<CloudTaskItem[]> {
  return (await productRequest<{ items: CloudTaskItem[] }>("/api/cloud/tasks?limit=100")).items;
}

export async function cancelCloudTask(id: string): Promise<CloudTaskItem> {
  return productRequest<CloudTaskItem>(`/api/cloud/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export async function listQueryExecutions(): Promise<QueryExecutionItem[]> {
  return (await productRequest<{ items: QueryExecutionItem[] }>("/api/cloud/query-executions?limit=100")).items;
}

export async function recordQueryExecution(input: {
  query: string; intent: string; conditions: Array<Record<string, unknown>>;
  result_count: number; idempotency_key: string;
}): Promise<QueryExecutionItem> {
  return productRequest<QueryExecutionItem>("/api/cloud/query-executions", { method: "POST", body: JSON.stringify(input) });
}

export async function listDevices(): Promise<DeviceItem[]> {
  const data = await productRequest<{ items: DeviceItem[] }>("/api/devices");
  return data.items;
}

export async function revokeDevice(deviceId: string): Promise<void> {
  await productRequest<void>("/api/devices/revoke", {
    method: "POST",
    body: JSON.stringify({ device_id: deviceId }),
  });
}

// ---- Device authorization flow (Task 9) ----

export interface DeviceAuthorizeStart {
  device_code: string;
  user_code: string;
  verification_url: string;
  interval_seconds: number;
  expires_in_seconds: number;
}

export type DevicePollStatus = "pending" | "approved" | "expired";

export interface DeviceAuthorizePoll {
  status: DevicePollStatus;
  access_token: string | null;
  refresh_token: string | null;
  device_id: string | null;
  interval_seconds: number;
}

export async function createDesktopDataHubSession(
  deviceId: string,
  accessToken: string,
): Promise<CreatedDataHubCredential> {
  return productRequest<CreatedDataHubCredential>("/api/datahub/desktop-session", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ device_id: deviceId }),
  });
}

export type DeviceRefreshStatus = "ok" | "revoked";

export interface DeviceTokenRefresh {
  status: DeviceRefreshStatus;
  access_token: string | null;
  refresh_token: string | null;
}

export async function startDeviceAuthorize(
  deviceName: string,
  fingerprintHash: string,
): Promise<DeviceAuthorizeStart> {
  return productRequest<DeviceAuthorizeStart>("/api/devices/authorize/start", {
    method: "POST",
    body: JSON.stringify({ device_name: deviceName, fingerprint_hash: fingerprintHash }),
  });
}

export async function approveDeviceAuthorize(userCode: string): Promise<void> {
  await productRequest<{ ok: boolean }>("/api/devices/authorize/approve", {
    method: "POST",
    body: JSON.stringify({ user_code: userCode }),
  });
}

export async function pollDeviceAuthorize(deviceCode: string): Promise<DeviceAuthorizePoll> {
  return productRequest<DeviceAuthorizePoll>("/api/devices/authorize/poll", {
    method: "POST",
    body: JSON.stringify({ device_code: deviceCode }),
  });
}

export async function refreshDeviceToken(refreshToken: string): Promise<DeviceTokenRefresh> {
  return productRequest<DeviceTokenRefresh>("/api/devices/token/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

// ---- Admin ----

export async function getAdminProductMetrics(days = 30): Promise<AdminProductMetrics> {
  return productRequest<AdminProductMetrics>(`/api/admin/product-metrics?days=${days}`);
}

export async function compensatePersonalCredits(userId: string, ledger: "research" | "data", amount: number, reason: string): Promise<{ operation_id: string }> {
  return productRequest("/api/admin/personal-support/credits", { method: "POST", body: JSON.stringify({ user_id: userId, ledger, amount, reason }) });
}

export async function revokePersonalSecurityTarget(userId: string, target: "devices" | "credentials", targetId: string, reason: string): Promise<void> {
  await productRequest(`/api/admin/personal-support/${target}/revoke`, { method: "POST", body: JSON.stringify({ user_id: userId, target_id: targetId, reason }) });
}

export async function createActivationCodes(
  planCode: string,
  months: number,
  count = 1,
): Promise<CreatedCodeItem[]> {
  const data = await productRequest<{ codes: CreatedCodeItem[] }>(
    "/api/admin/activation-codes",
    { method: "POST", body: JSON.stringify({ plan_code: planCode, months, count }) },
  );
  return data.codes;
}

export async function createDataCreditCodes(
  packCode: string,
  count = 1,
): Promise<CreatedCodeItem[]> {
  const data = await productRequest<{ codes: CreatedCodeItem[] }>(
    "/api/admin/data-credit-codes",
    { method: "POST", body: JSON.stringify({ pack_code: packCode, count }) },
  );
  return data.codes;
}

// ---- Helpers (frontend must not hard-code prices — derive from catalog) ----

/** Format a plan's price in CNY, or 合同报价 for contract-priced plans. */
export function formatPlanPrice(plan: PlanView): string {
  if (plan.price_cny_fen === 0 && plan.code !== "free") {
    return "合同报价";
  }
  if (plan.price_cny_fen === 0) {
    return "免费";
  }
  const yuan = (plan.price_cny_fen / 100).toFixed(plan.price_cny_fen % 100 === 0 ? 0 : 2);
  const period = plan.billing_period === "quarter" ? "/季" : plan.billing_period === "month" ? "/月" : "";
  return `¥${yuan}${period}`;
}
