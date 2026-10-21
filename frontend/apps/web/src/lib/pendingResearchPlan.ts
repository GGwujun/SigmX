import type { ResearchPlan } from "./researchApi";

const KEY = "sigmx.pendingResearchPlan.v1";

export interface PendingResearchPlan {
  question: string;
  templateId: string | null;
  plan: ResearchPlan;
}

function valid(value: unknown): value is PendingResearchPlan {
  if (!value || typeof value !== "object") return false;
  const pending = value as Partial<PendingResearchPlan>;
  return typeof pending.question === "string"
    && (pending.templateId === null || typeof pending.templateId === "string")
    && !!pending.plan
    && typeof pending.plan === "object"
    && typeof pending.plan.id === "string"
    && pending.plan.question === pending.question
    && Array.isArray(pending.plan.conditions)
    && Array.isArray(pending.plan.constraints)
    && typeof pending.plan.executable === "boolean";
}

export function savePendingResearchPlan(pending: PendingResearchPlan): void {
  window.sessionStorage.setItem(KEY, JSON.stringify(pending));
}

export function loadPendingResearchPlan(): PendingResearchPlan | null {
  const raw = window.sessionStorage.getItem(KEY);
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (valid(value)) return value;
  } catch {
    // Invalid state is removed below so it cannot repeatedly break restoration.
  }
  window.sessionStorage.removeItem(KEY);
  return null;
}

export function clearPendingResearchPlan(): void {
  window.sessionStorage.removeItem(KEY);
}
