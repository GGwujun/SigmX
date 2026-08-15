import { authHeaders } from "@/lib/apiAuth";

export class PublicResearchError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export interface PublicSearchItem {
  code: string; name: string; industry: string | null; close: number | null;
  pe_ttm: number | null; pb: number | null; dividend_yield: number | null;
  total_market_value: number | null; as_of: string | null;
}

export interface PublicSearchResult {
  query: string; interpretation: string[]; items: PublicSearchItem[];
  source: string; is_delayed: boolean;
}

export interface PublicStockSummary extends PublicSearchItem {
  market: string | null; source: string; is_delayed: boolean;
}

export interface PublicFundSummary {
  code: string; name: string; fund_type: string | null; close: number | null;
  change_percent: number | null; as_of: string | null; source: string; is_delayed: boolean;
}

export interface CloudReport {
  id: string; slug: string; title: string; summary: string;
  created_at: string; revoked_at: string | null;
}

async function request<T>(path: string, authenticated = false, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(authenticated ? authHeaders() : {}), ...(options?.headers || {}) },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).detail || message; } catch { /* keep status */ }
    throw new PublicResearchError(message, response.status);
  }
  return response.json() as Promise<T>;
}

export const cloudResearchApi = {
  search: (query: string) => request<PublicSearchResult>(`/api/public/search?q=${encodeURIComponent(query)}`),
  stock: (code: string) => request<PublicStockSummary>(`/api/public/stocks/${encodeURIComponent(code)}`),
  fund: (code: string) => request<PublicFundSummary>(`/api/public/funds/${encodeURIComponent(code)}`),
  publicReport: (slug: string) => request<CloudReport>(`/api/public/reports/${encodeURIComponent(slug)}`),
  saveQuery: (query: string, resultSummary: Record<string, unknown>) => request("/api/cloud/queries", true, { method: "POST", body: JSON.stringify({ query, result_summary: resultSummary }) }),
};
