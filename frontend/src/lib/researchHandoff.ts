import { cloudResearchApi } from "@/lib/cloudResearchApi";
import { getDesktopCloudAccessToken } from "@/lib/desktopConnectedSession";

export interface ConsumedResearchTask {
  kind: string;
  payload: Record<string, string>;
}

let pendingTask: ConsumedResearchTask | null = null;

export async function consumePendingResearchHandoff(): Promise<boolean> {
  const token = await window.sigmxDesktop?.researchHandoffTake?.();
  const accessToken = getDesktopCloudAccessToken();
  if (!token || !accessToken) return false;
  const consumed = await cloudResearchApi.consumeHandoff(token, accessToken);
  pendingTask = { kind: consumed.kind, payload: consumed.payload };
  return true;
}

export function takeConsumedResearchHandoff(): ConsumedResearchTask | null {
  const value = pendingTask;
  pendingTask = null;
  return value;
}

export async function activatePendingResearchHandoff(): Promise<void> {
  if (!await consumePendingResearchHandoff()) return;
  window.history.pushState({}, "", "/agent?handoff=1");
  window.dispatchEvent(new PopStateEvent("popstate"));
}
