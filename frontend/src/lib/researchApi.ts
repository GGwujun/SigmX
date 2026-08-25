import { authHeaders, clearAuth } from "./apiAuth";

export interface DiscoveryMetric { key: string; label: string; value: number | null; change: number | null; unit: string | null; quality: string; secondary_value: number | null }
export interface ResearchTemplate { id: string; label: string; description: string; prompt: string; data_domains: string[] }
export interface PublicDiscovery { as_of: string | null; source: string; is_delayed: boolean; market_status: string; metrics: DiscoveryMetric[]; templates: ResearchTemplate[] }
export interface ResearchStep { key: string; label: string; status: string }
export interface ResearchConditionAlternative { label: string; question: string }
export interface ResearchCondition { id: string; metric: string; label: string; operator: string | null; value: number | string | null; period: string | null; benchmark: string | null; status: "supported" | "degraded" | "unavailable"; reason: string | null; alternatives: ResearchConditionAlternative[] }
export interface ResearchDataset { key: string; name: string; status: "supported" | "degraded" | "unavailable"; as_of: string | null; coverage: string | null }
export interface ResearchPlan { id: string; question: string; template_id: string | null; scope: Record<string, unknown>; conditions: ResearchCondition[]; ranking: Record<string, unknown>[]; datasets: ResearchDataset[]; steps: ResearchStep[]; constraints: Record<string, unknown>[]; executable: boolean; suggested_question: string | null }
export interface CreateResearchPlanInput { question: string; template_id: string | null; scope: Record<string, unknown> }
export interface ResearchTask { id: string; user_id: string; question: string; template_id: string | null; scope: Record<string, unknown>; constraints: Record<string, unknown>[]; status: string; steps: ResearchStep[]; error: string | null; created_at: string; started_at: string | null; finished_at: string | null }
export interface ResearchEvidence { field: string; value: unknown; source: string; as_of: string | null }
export interface ResearchCandidate { code: string; name: string; industry: string | null; close: number | null; pe_ttm: number | null; pb: number | null; dividend_yield: number | null; total_market_value: number | null; reason: string; evidence: ResearchEvidence[] }
export interface ResearchResult { task_id: string; question: string; template_id: string | null; summary: string; source: string; as_of: string | null; scope: Record<string, unknown>; candidates: ResearchCandidate[]; risks: string[]; created_at: string }

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    if (response.status === 401) {
      clearAuth();
      throw new Error("登录已过期，请重新登录");
    }
    let detail = `请求失败（${response.status}）`;
    try { detail = (await response.json()).detail || detail; } catch { /* non-JSON error */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const getDiscovery = () => json<PublicDiscovery>("/api/public/discovery");

export const createResearchPlan = (input: CreateResearchPlanInput) =>
  json<ResearchPlan>("/api/research/plans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });

export const createResearchTask = (input: { question: string; template_id: string | null; scope: Record<string, unknown>; constraints: Record<string, unknown>[] }) =>
  json<ResearchTask>("/api/research/tasks", { method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() }, body: JSON.stringify({ ...input, idempotency_key: crypto.randomUUID() }) });

export const getResearchResult = (taskId: string) =>
  json<ResearchResult>(`/api/research/tasks/${encodeURIComponent(taskId)}/result`, { headers: authHeaders() });

export const listResearchTasks = (limit = 5) =>
  json<ResearchTask[]>(`/api/research/tasks?limit=${limit}`, { headers: authHeaders() });
