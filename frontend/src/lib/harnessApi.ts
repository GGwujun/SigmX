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
  status: string;
  started_at: string | null;
  finished_at: string | null;
  context_manifest: Record<string, unknown>;
  tool_calls: string[];
  evidence_refs: string[];
  costs: Record<string, number>;
  degradations: string[];
  result_ref: string | null;
}

async function harnessRequest<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { ...authHeaders() } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(body.detail || `Harness request failed (${response.status})`, response.status);
  }
  return response.json() as Promise<T>;
}

export function getHarnessStatus(): Promise<HarnessStatus> {
  return harnessRequest("/api/harness/status");
}

export async function getHarnessRuns(limit = 5): Promise<HarnessRun[]> {
  const response = await harnessRequest<{ items: HarnessRun[] }>(`/api/harness/runs?limit=${limit}`);
  return response.items;
}
