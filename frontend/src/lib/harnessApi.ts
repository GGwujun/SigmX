import { ApiError } from "@/lib/api";
import { authHeaders } from "@/lib/apiAuth";

export interface HarnessStatus {
  runtime_available: boolean;
  cloud_connected: boolean;
  local_data_available: boolean;
  data_hub_available: boolean;
  research_credits: number;
  data_credits: number;
  governance_ceiling: string;
  degradations: string[];
}

export interface HarnessRun {
  run_id: string;
  run_type: string;
  title: string;
  goal: string;
  status: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  context_manifest: Record<string, unknown>;
  steps: Array<{ id: string; title: string; status: string; created_at: string }>;
  tool_calls: Array<{ id: string; tool_id: string; status: string; duration_ms: number; output_ref: string | null }>;
  evidence: Array<{ id: string; kind: string; title: string; ref: string; source: string; data_version: string | null }>;
  artifacts: Array<{ id: string; kind: string; name: string; ref: string }>;
  costs: Record<string, number>;
  degradations: Array<{ id: string; code: string; message: string }>;
  governance_events: Array<{ id: string; level: string; decision: string; reason: string }>;
  result_ref: string | null;
  error: string | null;
}

export interface LocalAsset {
  id: string; kind: string; name: string; extension: string; size_bytes: number;
  modified_at: string; version: string | null; local_only: boolean;
}

export interface LocalAssetsResponse {
  items: LocalAsset[];
  summary: { counts: Record<string, number>; total_size_bytes: number; latest_modified_at: string | null };
}

async function harnessRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...authHeaders(), ...init.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail || `Harness request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export function getHarnessStatus(): Promise<HarnessStatus> {
  return harnessRequest("/api/harness/status");
}

export async function getHarnessRuns(limit = 5, filters: { runType?: string; status?: string } = {}): Promise<HarnessRun[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (filters.runType) params.set("run_type", filters.runType);
  if (filters.status) params.set("status", filters.status);
  const response = await harnessRequest<{ items: HarnessRun[] }>(`/api/harness/runs?${params}`);
  return response.items;
}

export function createHarnessRun(input: { run_type: string; title: string; goal: string; context_manifest: Record<string, unknown> }): Promise<HarnessRun> {
  return harnessRequest("/api/harness/runs", { method: "POST", body: JSON.stringify(input) });
}

export function getHarnessRun(runId: string): Promise<HarnessRun> {
  return harnessRequest(`/api/harness/runs/${encodeURIComponent(runId)}`);
}

export function cancelHarnessRun(runId: string): Promise<HarnessRun> {
  return harnessRequest(`/api/harness/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
}

export function getHarnessAssets(filters: { kind?: string; query?: string } = {}): Promise<LocalAssetsResponse> {
  const params = new URLSearchParams();
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.query) params.set("query", filters.query);
  const suffix = params.size ? `?${params}` : "";
  return harnessRequest(`/api/harness/assets${suffix}`);
}
