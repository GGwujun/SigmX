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
  [key: string]: number | boolean;
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
  months: number;
  created_at: string;
  paid_at: string | null;
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

// ---- Admin ----

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
